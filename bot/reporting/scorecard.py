"""Karne (Görev C.2) — sinyal takibi + sistem-dışı ayrımı + aylık özet.

Karne, her rotasyon önerisini ve satış uyarısını sinyal tarihi/fiyatıyla kaydeder;
5/20/60 işlem günü sonrası getiriyi ELLE MÜDAHALE OLMADAN doldurur (pencere
kapandıkça sonraki koşularda hesaplanır). Ayrıca Pozisyonlar'daki elle işlemler
sistemin önerileriyle mutabakatlanır: öneriyle eşleşmeyenler `sistem-dışı`
etiketlenir ve karnede AYRI izlenir — 12. ayda sistemin ve elin katkısı ayrışsın.

Bu modül SAFTIR (bars/holdings/kayıtlar dışarıdan gelir). Sheets I/O bot.logging
.sheets'te; sunum bot.notify.slack'te. Böylece ağsız test edilir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import pandas as pd

# Karne satır türleri
KIND_ROTATION_ENTRY = "rotation_entry"
KIND_SLOT_FILL = "slot_fill"
KIND_SELL_ALERT = "sell_alert"
KIND_MANUAL_POSITION = "manuel_pozisyon"   # sistem-dışı elle alınmış pozisyon

# Sistemin ürettiği (önerdiği) alım türleri — mutabakatta "sistem" sayılır.
_SYSTEM_BUY_KINDS = {KIND_ROTATION_ENTRY, KIND_SLOT_FILL}

# Karne kolon adları — bot.logging.sheets.KARNE_HEADERS ile AYNI sırada olmalı
# (test_scorecard.py bunu doğrular).
COLUMNS = ["Sinyal Tarihi", "Sembol", "Tür", "Kaynak", "Sinyal Fiyatı",
           "5g Getiri %", "20g Getiri %", "60g Getiri %"]

SOURCE_SYSTEM = "sistem"
SOURCE_MANUAL = "sistem-dışı"

DEFAULT_HORIZONS = (5, 20, 60)


@dataclass
class ScorecardEntry:
    signal_date: str          # ISO (YYYY-MM-DD)
    symbol: str
    kind: str                 # rotation_entry | slot_fill | sell_alert
    source: str               # sistem | sistem-dışı
    price: float              # sinyal-günü kapanış fiyatı
    ret_5: Optional[float] = None
    ret_20: Optional[float] = None
    ret_60: Optional[float] = None

    def horizon_value(self, h: int) -> Optional[float]:
        return getattr(self, f"ret_{h}", None)

    def set_horizon(self, h: int, value: float) -> None:
        setattr(self, f"ret_{h}", value)


# ---------------------------------------------------------------------------
#  Karne satırı üretimi (bir günün kararından)
# ---------------------------------------------------------------------------
def build_scorecard_entries(decision, *, source: str = SOURCE_SYSTEM) -> list[ScorecardEntry]:
    """LiveDecision'dan yeni karne satırları üret (getiriler başta boş).

    Rotasyon girişleri + slot doldurma adayları + satış uyarıları kaydedilir.
    Fiyat, decision.prices'tan (sinyal-günü kapanışı) alınır.
    """
    day = decision.as_of.isoformat()
    prices = getattr(decision, "prices", {}) or {}
    out: list[ScorecardEntry] = []
    for b in decision.rotation_entries:
        out.append(ScorecardEntry(day, b.symbol, KIND_ROTATION_ENTRY, source,
                                   float(prices.get(b.symbol, b.price))))
    for b in decision.slot_fills:
        out.append(ScorecardEntry(day, b.symbol, KIND_SLOT_FILL, source,
                                   float(prices.get(b.symbol, b.price))))
    for a in decision.sell_alerts:
        out.append(ScorecardEntry(day, a.symbol, KIND_SELL_ALERT, source,
                                   float(prices.get(a.symbol, 0.0))))
    return out


# ---------------------------------------------------------------------------
#  İleri getiri (5/20/60 işlem günü) — pencere kapandıkça doldurulur
# ---------------------------------------------------------------------------
def forward_return(bars: Mapping[str, pd.DataFrame], symbol: str, signal_date: str,
                   horizon: int) -> Optional[float]:
    """Sinyal gününden `horizon` işlem günü sonrasına getiri (%). Pencere henüz
    kapanmadıysa (yeterli bar yok) veya veri yoksa None.
    """
    df = bars.get(symbol)
    if df is None or df.empty:
        return None
    ts = pd.Timestamp(signal_date).normalize()
    idx = df.index
    pos = idx.searchsorted(ts)
    if pos >= len(idx) or pd.Timestamp(idx[pos]).normalize() != ts:
        return None                    # sinyal günü bu sembolün barlarında yok
    if pos + horizon >= len(idx):
        return None                    # pencere henüz kapanmadı
    p0 = float(df["close"].iloc[pos])
    p1 = float(df["close"].iloc[pos + horizon])
    if p0 <= 0:
        return None
    return round((p1 / p0 - 1.0) * 100.0, 2)


def fill_forward_returns(entries: Sequence[ScorecardEntry], bars: Mapping[str, pd.DataFrame],
                         *, horizons: Sequence[int] = DEFAULT_HORIZONS) -> int:
    """Eksik (None) ve penceresi kapanmış getirileri hesaplayıp entries'e yaz.

    Döndürür: doldurulan hücre sayısı (kaç yeni getiri hesaplandı). Satırları
    YERİNDE günceller (elle müdahale gerekmez — her koşu tekrar dener).
    """
    filled = 0
    for e in entries:
        for h in horizons:
            if e.horizon_value(h) is not None:
                continue
            val = forward_return(bars, e.symbol, e.signal_date, h)
            if val is not None:
                e.set_horizon(h, val)
                filled += 1
    return filled


# ---------------------------------------------------------------------------
#  Sistem-dışı mutabakatı
# ---------------------------------------------------------------------------
def recommended_symbols(history: Sequence[ScorecardEntry]) -> set[str]:
    """Sistemin ALIM olarak önerdiği tüm semboller (rotasyon girişi + slot doldurma)."""
    return {e.symbol.strip().upper() for e in history if e.kind in _SYSTEM_BUY_KINDS}


def reconcile_positions(holdings: Sequence[Mapping], history: Sequence[ScorecardEntry]
                        ) -> dict[str, str]:
    """Her açık pozisyonu sistem/sistem-dışı olarak etiketle.

    Sistemin önerdiği (karnede rotation_entry/slot_fill olarak geçen) sembol
    `sistem`; hiç önerilmemiş elle alınmış pozisyon `sistem-dışı`. 12. ay
    değerlendirmesinde el/sistem katkısı bu ayrımla ayrıştırılır.
    """
    recommended = recommended_symbols(history)
    labels: dict[str, str] = {}
    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        if not sym:
            continue
        labels[sym] = SOURCE_SYSTEM if sym in recommended else SOURCE_MANUAL
    return labels


# ---------------------------------------------------------------------------
#  Aylık özet — portföy vs SPY vs evren al-tut
# ---------------------------------------------------------------------------
def _return_over(df: Optional[pd.DataFrame], as_of: pd.Timestamp, lookback: int
                 ) -> Optional[float]:
    if df is None or df.empty:
        return None
    s = df["close"].loc[:as_of]
    if len(s) <= lookback:
        return None
    p0 = float(s.iloc[-(lookback + 1)])
    p1 = float(s.iloc[-1])
    return (p1 / p0 - 1.0) if p0 > 0 else None


def monthly_summary(bars: Mapping[str, pd.DataFrame], holdings: Sequence[Mapping],
                    universe: Sequence[str], as_of, *, lookback_days: int = 21,
                    benchmark: str = "SPY") -> dict:
    """Portföy / SPY / evren al-tut getirisini son `lookback_days` işlem gününde
    hesapla (%). Değer üretilemeyen bileşen None döner.
    """
    ts = pd.Timestamp(as_of).normalize()

    # Portföy: shares sabit; değer değişimi
    v0 = v1 = 0.0
    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        shares = float(h.get("shares") or 0.0)
        df = bars.get(sym)
        if df is None or df.empty or not shares:
            continue
        s = df["close"].loc[:ts]
        if len(s) <= lookback_days:
            continue
        v0 += shares * float(s.iloc[-(lookback_days + 1)])
        v1 += shares * float(s.iloc[-1])
    portfolio = ((v1 / v0 - 1.0) * 100.0) if v0 > 0 else None

    spy = _return_over(bars.get(benchmark), ts, lookback_days)
    spy_pct = spy * 100.0 if spy is not None else None

    # Evren al-tut: eşit ağırlık, getirisi hesaplanabilen semboller
    rets = [_return_over(bars.get(s), ts, lookback_days) for s in universe]
    rets = [r for r in rets if r is not None]
    universe_pct = (sum(rets) / len(rets) * 100.0) if rets else None

    return {
        "as_of": ts.date().isoformat(),
        "lookback_days": lookback_days,
        "portfolio_pct": round(portfolio, 2) if portfolio is not None else None,
        "spy_pct": round(spy_pct, 2) if spy_pct is not None else None,
        "universe_pct": round(universe_pct, 2) if universe_pct is not None else None,
    }


# ---------------------------------------------------------------------------
#  Satır (de)serileştirme + birleştirme + tek-adım güncelleme (main entegrasyonu)
# ---------------------------------------------------------------------------
def _num(v) -> Optional[float]:
    if v in ("", None):
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def entry_to_row(e: ScorecardEntry) -> list:
    """ScorecardEntry → COLUMNS sırasında Sheets satırı (None → boş hücre)."""
    def cell(v):
        return "" if v is None else v
    return [e.signal_date, e.symbol, e.kind, e.source, e.price,
            cell(e.ret_5), cell(e.ret_20), cell(e.ret_60)]


def row_to_entry(d: Mapping) -> ScorecardEntry:
    """Sheets ham kaydı (dict) → ScorecardEntry."""
    return ScorecardEntry(
        signal_date=str(d.get("Sinyal Tarihi", "")).strip()[:10],
        symbol=str(d.get("Sembol", "")).strip().upper(),
        kind=str(d.get("Tür", "")).strip(),
        source=str(d.get("Kaynak", "")).strip() or SOURCE_SYSTEM,
        price=_num(d.get("Sinyal Fiyatı")) or 0.0,
        ret_5=_num(d.get("5g Getiri %")),
        ret_20=_num(d.get("20g Getiri %")),
        ret_60=_num(d.get("60g Getiri %")),
    )


def _key(e: ScorecardEntry) -> tuple:
    return (e.signal_date, e.symbol.strip().upper(), e.kind)


def merge_entries(existing: Sequence[ScorecardEntry], new: Sequence[ScorecardEntry]
                  ) -> list[ScorecardEntry]:
    """Yeni satırları ekle; (tarih, sembol, tür) çifti zaten varsa tekrar ekleme."""
    seen = {_key(e) for e in existing}
    out = list(existing)
    for e in new:
        if _key(e) not in seen:
            out.append(e)
            seen.add(_key(e))
    return out


def manual_position_entries(holdings: Sequence[Mapping], history: Sequence[ScorecardEntry]
                            ) -> list[ScorecardEntry]:
    """Sistemin hiç önermediği açık pozisyonları sistem-dışı karne satırına çevir."""
    labels = reconcile_positions(holdings, history)
    out: list[ScorecardEntry] = []
    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        if labels.get(sym) != SOURCE_MANUAL:
            continue
        out.append(ScorecardEntry(
            signal_date=str(h.get("entry_date") or "")[:10],
            symbol=sym, kind=KIND_MANUAL_POSITION, source=SOURCE_MANUAL,
            price=float(h.get("entry_price") or 0.0)))
    return out


def update_karne(existing_rows: Sequence[Mapping], decision, bars: Mapping[str, pd.DataFrame],
                 holdings: Sequence[Mapping] = (), *, source: str = SOURCE_SYSTEM
                 ) -> list[ScorecardEntry]:
    """Tek adımda karneyi güncelle: kayıtları oku → bugünün satırlarını + sistem-dışı
    pozisyonları ekle → penceresi kapanan ileri getirileri doldur.

    main bu sonucu entry_to_row ile Sheets'e geri yazar. Elle müdahale gerekmez.
    """
    existing = [row_to_entry(d) for d in existing_rows]
    new = build_scorecard_entries(decision, source=source)
    merged = merge_entries(existing, new)
    merged = merge_entries(merged, manual_position_entries(holdings, merged))
    fill_forward_returns(merged, bars)
    return merged
