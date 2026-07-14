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
    rank_now: Optional[int], *, top_n: int | None = None,
    multiple: int | None = None, cutoff: int | None = None,
) -> Optional[SellTrigger]:
    """Hisse güncel sırada eşiğin (cutoff) dışına düştüyse sıralama çöküşü.

    Eşik iki yoldan gelebilir:
      - `cutoff` doğrudan verilir (taban-hizalı çağrı; bkz. collapse_cutoff), veya
      - `multiple`×`top_n` ile hesaplanır (küresel klasik davranış).
    rank_now None ise (sıralama üretilemedi/veri yok) tetiklenmez — yanlış alarmı
    önlemek için sıra bilinmiyorsa değerlendirme yapılmaz.
    """
    if rank_now is None:
        return None
    if cutoff is None:
        if top_n is None or multiple is None:
            return None
        cutoff = multiple * top_n
    if rank_now > cutoff:
        return SellTrigger(
            TriggerType.RANKING,
            f"Sıralama #{rank_now} — ilk {cutoff} dışına düştü (ay sonu beklenmez)",
        )
    return None


# ---------------------------------------------------------------------------
#  Taban hizalama — çöküş testi tutma kuralıyla AYNI sıralama tabanına oturur
# ---------------------------------------------------------------------------
def collapse_cutoff(strategy) -> int:
    """Sıralama-çöküşü eşiği (seçim moduna göre TABAN hizalı).

    per_basket   : ranking_collapse_multiple × positions_per_basket (sepet-içi taban).
                   Portföy her sepetten `positions_per_basket` hisse tutar; çöküş de
                   bu sepet-içi sıraya göre ölçülür (varsayılan 2×2 = 4).
    global_top_n : ranking_collapse_multiple × top_n (küresel taban; klasik davranış).

    Taban hizalama olmadan (eski küresel eşik) per_basket'te meşru tutulan bir
    pozisyon, evren genelindeki sırası düşük diye her gün 'çökmüş' sayılabiliyordu
    (teşhis: results/diag_1923_trades.md — churn'ün %92'si).
    """
    mult = int(strategy.raw.get("sell_alerts", {}).get("ranking_collapse_multiple", 2))
    rot = strategy.rotation
    if rot.get("selection") == "global_top_n":
        return mult * int(rot.get("top_n", 6))
    per_basket = int(strategy.portfolio.get("positions_per_basket", 2))
    return mult * per_basket


def collapse_rank_map(strategy, ranking) -> dict[str, int]:
    """Çöküş testinde kullanılacak sıra haritası (seçim moduna göre taban).

    ranking : küresel AZALAN (symbol, skor) listesi (bir Ranker'dan).
    per_basket   : her sembolün SEPET-İÇİ sırası (1 = sepetin en yükseği).
    global_top_n : küresel sıra (1 = evrenin en yükseği).
    slot_candidates de aynı tabanı kullanır (per_basket'te sepet-içi en yüksek
    uygun adayı önerir) — böylece seçme ve çıkarma ölçüsü tutarlıdır.
    """
    if strategy.rotation.get("selection") == "global_top_n":
        return {sym: i for i, (sym, _) in enumerate(ranking, start=1)}
    counts: dict[str | None, int] = {}
    out: dict[str, int] = {}
    for sym, _score in ranking:
        b = strategy.basket_of(sym)
        counts[b] = counts.get(b, 0) + 1
        out[sym] = counts[b]
    return out


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


# ---------------------------------------------------------------------------
#  Kalıcılık şartı — çöküş ancak art arda N işlem günü sürerse tetiklenir
# ---------------------------------------------------------------------------
class RankingCollapseTracker:
    """Sıralama-çöküşü için TABAN-HİZALI + KALICILIK-ŞARTLI durum takibi.

    (1) Taban hizalama: eşik/sıra seçim moduna göre (collapse_cutoff/collapse_rank_map).
    (2) Kalıcılık: bir pozisyon eşiği ancak `persist_days` art arda işlem günü
        aşarsa 'çökmüş' sayılır — tek/çift günlük sıralama gürültüsü satış üretmez.

    Teknik acil tetik bu şarttan MUAF'tır: o ani fiyat olayları için ayrı yolda
    (check_technical_emergency) değerlendirilir ve ilk günden tetikleyebilir.

    DURUMLUDUR: her işlem günü bir kez update() ile beslenir. Portföyden çıkan
    sembolün sayacı düşürülür; yeniden girişte sıfırdan başlar (aç-kapa koruması).
    Backtest ve (Faz C) canlı akış AYNI sınıfı kullanır — davranış tektir.
    """

    def __init__(self, strategy, *, persist_days: int | None = None) -> None:
        self._strategy = strategy
        sa = strategy.raw.get("sell_alerts", {})
        self._persist = int(
            persist_days if persist_days is not None
            else sa.get("ranking_collapse_persist_days", 3)
        )
        self._streak: dict[str, int] = {}

    @property
    def persist_days(self) -> int:
        return self._persist

    def update(self, ranking, holdings) -> set[str]:
        """Bugünkü sıralamayla sayaçları güncelle; kalıcılığı dolan sembolleri döndür.

        ranking : küresel azalan (symbol, skor) listesi.
        holdings: bugünkü açık pozisyon sembolleri.
        Dönüş   : bu gün itibarıyla `persist_days` art arda eşik dışı kalan semboller.
        """
        held = {s for s in holdings}
        cutoff = collapse_cutoff(self._strategy)
        rank_map = collapse_rank_map(self._strategy, ranking)
        # Artık tutulmayan sembollerin durumunu düşür (yeniden girişte temiz başlangıç)
        for sym in list(self._streak):
            if sym not in held:
                del self._streak[sym]
        collapsed: set[str] = set()
        for sym in held:
            r = rank_map.get(sym)
            if r is not None and r > cutoff:
                self._streak[sym] = self._streak.get(sym, 0) + 1
            else:
                # eşik içi VEYA sıra bilinmiyor -> seri kırılır (gürültü birikmez)
                self._streak[sym] = 0
            if self._persist > 0 and self._streak[sym] >= self._persist:
                collapsed.add(sym)
        return collapsed

    def drop(self, symbol: str) -> None:
        """Bir sembolün çöküş sayacını sıfırla (satıştan sonra elle temizleme)."""
        self._streak.pop(symbol, None)


# ---------------------------------------------------------------------------
#  Yeniden-giriş bekleme süresi — aç-kapa döngüsünü yapısal olarak imkânsız kılar
# ---------------------------------------------------------------------------
class AlertCooldown:
    """Uyarıyla kapanan sembol için YENİDEN-GİRİŞ bekleme süresi (aç-kapa koruması).

    Bir sembol bir satış-uyarısıyla kapandığında `cooldown_days` işlem günü boyunca
    slot adayı olamaz (slot_candidates bu kümeyi dışlar). Gelecekte başka bir tetik
    hatası olsa bile günlük aç-kapa döngüsü yapısal olarak kurulamaz.

    İşlem-günü sayacı (day_index) dışarıdan monoton artan bir tam sayıyla verilir:
    backtest'te takvim konumu, canlı akışta günlük artan sayaç. Aynı sınıf her iki
    yolda da kullanılır.
    """

    def __init__(self, strategy=None, *, cooldown_days: int | None = None) -> None:
        if cooldown_days is None:
            sa = strategy.raw.get("sell_alerts", {}) if strategy is not None else {}
            cooldown_days = sa.get("slot_refill_cooldown_days", 5)
        self._cd = int(cooldown_days)
        self._release: dict[str, int] = {}

    @property
    def cooldown_days(self) -> int:
        return self._cd

    def register(self, symbol: str, day_index: int) -> None:
        """Sembolü `day_index`'te kapandı işaretle (serbest kalış = day_index + cooldown_days)."""
        self._release[symbol.strip().upper()] = day_index + self._cd

    def is_blocked(self, symbol: str, day_index: int) -> bool:
        """Bu işlem gününde sembol hâlâ bekleme süresinde mi?"""
        return day_index < self._release.get(symbol.strip().upper(), -1)

    def blocked(self, day_index: int) -> set[str]:
        """Bu işlem gününde aday olamayan (bekleme süresindeki) tüm semboller."""
        return {s for s, r in self._release.items() if day_index < r}


class SellAlertEngine:
    """Bir pozisyon için üç tetiği değerlendirir; ledger ile spam korur.

    Sıralama-çöküşü eşiği TABAN-HİZALIDIR (collapse_cutoff): per_basket modunda
    sepet-içi, global_top_n modunda küresel. Çağıran taban-hizalı `rank_now`
    geçirmelidir (per_basket'te sepet-içi sıra; bkz. collapse_rank_map).
    """

    def __init__(self, strategy) -> None:
        self._cfg = strategy.raw.get("sell_alerts", {})
        self._cutoff = collapse_cutoff(strategy)
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

        t2 = check_ranking_collapse(rank_now, cutoff=self._cutoff)
        if t2:
            triggers.append(t2)

        triggers.extend(check_fundamental_red_flags(fundamental or {}, cfg.get("fundamental", {})))

        fresh = self._ledger.take_new(day or date.today(), symbol, triggers)
        if not fresh:
            return None
        return SellAlert(symbol=symbol, triggers=fresh, current_rank=rank_now)
