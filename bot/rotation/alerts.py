"""Kural-bazlı satış uyarıları (Görev A.3) — rotasyon dışı çıkışlar.

Stop EMRİ yoktur; kullanıcıya vurgulu bir SATIŞ UYARISI verilir. Amaç karar anını
duygudan arındırmaktır — karar her zaman kullanıcınındır. Portföydeki her pozisyon
için üç bağımsız tetik:

  1. Teknik acil durum : fiyat girişten `atr_exit_multiple` × ATR aşağıda.
  2. Sıralama çöküşü   : hisse güncel sırada ilk `ranking_collapse_multiple` × top_n
                         dışına düştü.
  3. Temel kırmızı bayrak: v1 temel katmanı skora DEĞİL yalnız uyarıya bağlanır —
                         kazanç çöküşü, zarar + gelir daralması birlikteliği, yoğun
                         içeriden satış (asimetrik: alım > satım), iki haber
                         kaynağının birlikte belirgin negatifliği.

Eşikler strategy.yaml `sell_alerts` bloğundadır. Aynı pozisyon için aynı tetik
günde bir kez bildirilir (AlertLedger — spam koruması). Fonksiyonlar saftır ve
ağ/anahtar gerektirmez; canlı akışa bağlama (Slack, Sheets) Faz C'dedir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Mapping, Optional

import pandas as pd

from ..signals.fundamental import _AV_SENTIMENT_SCALE
from ..signals.levels import _atr


class TriggerType(str, Enum):
    TECHNICAL = "technical_emergency"
    RANKING = "ranking_collapse"
    FUNDAMENTAL = "fundamental_red_flag"


@dataclass(frozen=True)
class SellTrigger:
    type: TriggerType
    reason: str


@dataclass(frozen=True)
class SellAlert:
    symbol: str
    triggers: list[SellTrigger]
    current_rank: Optional[int] = None


def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """OHLC barlarından ATR (oynaklık) — levels modülüyle aynı hesap."""
    return _atr(df, period)


# ---------------------------------------------------------------------------
#  Tekil tetikler (her biri ayrı test edilir)
# ---------------------------------------------------------------------------
def check_technical_emergency(
    entry_price: float, current_price: float, atr: float, *, multiple: float
) -> Optional[SellTrigger]:
    """Fiyat girişten `multiple`×ATR aşağı düştüyse teknik acil durum tetiği."""
    if not entry_price or entry_price <= 0 or not atr or atr <= 0:
        return None
    threshold = entry_price - multiple * atr
    if current_price <= threshold:
        return SellTrigger(
            TriggerType.TECHNICAL,
            f"Fiyat ${current_price:,.2f}, girişten ({entry_price:,.2f}) "
            f"{multiple:g}×ATR aşağıda — pozisyon tezini kaybetti",
        )
    return None


def check_ranking_collapse(
    rank_now: Optional[int], *, top_n: int, multiple: int
) -> Optional[SellTrigger]:
    """Hisse güncel sırada ilk `multiple`×top_n dışına düştüyse sıralama çöküşü.

    rank_now None ise (sıralama üretilemedi/veri yok) tetiklenmez — yanlış alarmı
    önlemek için sıra bilinmiyorsa değerlendirme yapılmaz.
    """
    if rank_now is None:
        return None
    cutoff = multiple * top_n
    if rank_now > cutoff:
        return SellTrigger(
            TriggerType.RANKING,
            f"Sıralama #{rank_now} — ilk {cutoff} dışına düştü (ay sonu beklenmez)",
        )
    return None


def check_fundamental_red_flags(
    fdata: Mapping[str, Any], cfg: Mapping[str, Any]
) -> list[SellTrigger]:
    """Temel kırmızı bayrakları uyarıya çevir (skora DEĞİL). Boşsa [] döner."""
    if not fdata:
        return []
    flags: list[SellTrigger] = []

    # 1) Kazanç çöküşü
    es = fdata.get("earnings_surprise_pct")
    es_min = cfg.get("earnings_surprise_min_pct", -15)
    if es is not None and es <= es_min:
        flags.append(SellTrigger(TriggerType.FUNDAMENTAL, f"Kazanç sürprizi %{es:+.1f} (çöküş)"))

    # 2) Zarar + gelir daralması BİRLİKTE
    pm = fdata.get("profit_margin")
    rg = fdata.get("revenue_growth_yoy")
    rg_max = cfg.get("revenue_growth_max", 0.0)
    if pm is not None and pm < 0 and rg is not None and rg < rg_max:
        flags.append(SellTrigger(
            TriggerType.FUNDAMENTAL,
            f"Zarar (marj %{pm * 100:.0f}) + gelir daralması (%{rg * 100:+.0f} YoY) birlikte",
        ))

    # 3) Yoğun içeriden satış (asimetrik: alım > satım normal sayılır)
    buys = fdata.get("insider_buys")
    sells = fdata.get("insider_sells")
    ratio_min = cfg.get("insider_sell_ratio_min", 3.0)
    count_min = cfg.get("insider_sell_min_count", 3)
    if sells is not None and sells >= count_min:
        # Alımlar satışları asimetrik olarak dengeler: satış, alımın ratio katından
        # fazlaysa (ya da hiç alım yoksa) yoğun satış sayılır.
        if buys in (None, 0) or sells >= ratio_min * buys:
            flags.append(SellTrigger(
                TriggerType.FUNDAMENTAL,
                f"Yoğun içeriden satış (satış {int(sells)} / alım {int(buys or 0)})",
            ))

    # 4) İki haber kaynağı da belirgin negatif
    ns = fdata.get("news_sentiment_score")
    ws = fdata.get("web_sentiment_score")
    neg = cfg.get("news_negative_max", -0.30)
    if ns is not None and ws is not None:
        ns_norm = max(-1.0, min(1.0, ns / _AV_SENTIMENT_SCALE))   # AV ölçeğini [-1,1]'e getir
        if ns_norm <= neg and ws <= neg:
            flags.append(SellTrigger(
                TriggerType.FUNDAMENTAL,
                f"İki haber kaynağı da belirgin negatif (AV {ns_norm:+.2f}, web {ws:+.2f})",
            ))

    return flags


# ---------------------------------------------------------------------------
#  Spam koruması: aynı pozisyon + aynı tetik türü günde bir kez
# ---------------------------------------------------------------------------
class AlertLedger:
    """Aynı gün içinde (sembol, tetik türü) çiftini bir kez geçirir."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str]] = set()

    def take_new(self, day: date, symbol: str, triggers: list[SellTrigger]) -> list[SellTrigger]:
        """Bugün bu sembol için henüz bildirilmemiş tetikleri döndür ve işaretle."""
        fresh: list[SellTrigger] = []
        for t in triggers:
            key = (day.isoformat(), symbol.upper(), t.type.value)
            if key in self._seen:
                continue
            self._seen.add(key)
            fresh.append(t)
        return fresh


class SellAlertEngine:
    """Bir pozisyon için üç tetiği değerlendirir; ledger ile spam korur."""

    def __init__(self, strategy) -> None:
        self._cfg = strategy.raw.get("sell_alerts", {})
        self._top_n = int(strategy.rotation.get("top_n", 6))
        self._ledger = AlertLedger()

    def evaluate(
        self,
        symbol: str,
        *,
        entry_price: float,
        current_price: float,
        atr: float,
        rank_now: Optional[int] = None,
        fundamental: Optional[Mapping[str, Any]] = None,
        day: Optional[date] = None,
    ) -> Optional[SellAlert]:
        """Pozisyon için tetikleri topla (spam korumalı). Yeni tetik yoksa None."""
        cfg = self._cfg
        triggers: list[SellTrigger] = []

        t1 = check_technical_emergency(
            entry_price, current_price, atr, multiple=cfg.get("atr_exit_multiple", 3.0)
        )
        if t1:
            triggers.append(t1)

        t2 = check_ranking_collapse(
            rank_now, top_n=self._top_n, multiple=cfg.get("ranking_collapse_multiple", 2)
        )
        if t2:
            triggers.append(t2)

        triggers.extend(check_fundamental_red_flags(fundamental or {}, cfg.get("fundamental", {})))

        fresh = self._ledger.take_new(day or date.today(), symbol, triggers)
        if not fresh:
            return None
        return SellAlert(symbol=symbol, triggers=fresh, current_rank=rank_now)
