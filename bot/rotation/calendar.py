"""Rotasyon ritmi — hangi işlem günleri rotasyon günüdür (Görev C.1).

Backtest ve canlı akış AYNI kuralı paylaşır (tek doğruluk kaynağı): rotasyon
sinyali yalnız belirli işlem günlerinde üretilir, diğer günler yalnız izleme
(satış-uyarısı taraması + slot doldurma + gözlem).

  monthly  : her ayın İLK işlem günü.
  biweekly : her ayın ilk işlem günü + o ayda 15'inden sonraki İLK işlem günü.

Tatil/hafta sonu kayması "bedava" doğru çalışır: takvim GERÇEK işlem günlerinden
(fiyat barlarının indeksinden) kurulur, bu yüzden ayın 1'i cumartesiyse ilk
işlem günü otomatik olarak pazartesi olur; 15'i pazarsa 15-sonrası ilk işlem
günü 16'sı (pazartesi) olur. Takvim ne verirse ritim ona uyar.

Fonksiyonlar saftır (takvim dışarıdan gelir) — ağ/veri kaynağı bilmez, testlenir.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import pandas as pd

MONTHLY = "monthly"
BIWEEKLY = "biweekly"

# İki haftalık ritimde ayın ikinci rotasyon penceresinin başladığı gün.
_BIWEEKLY_SECOND_HALF_DAY = 15


def _as_timestamps(calendar: Iterable) -> list[pd.Timestamp]:
    """Takvimi sıralı pd.Timestamp listesine normalize et (yinelenenler tekilleşir)."""
    seen: set[pd.Timestamp] = set()
    out: list[pd.Timestamp] = []
    for d in calendar:
        ts = pd.Timestamp(d).normalize()
        if ts not in seen:
            seen.add(ts)
            out.append(ts)
    out.sort()
    return out


def rotation_days(calendar: Sequence, frequency: str = MONTHLY) -> set[pd.Timestamp]:
    """Verilen işlem-günü takviminde rotasyon günlerini (normalize Timestamp) döndür.

    calendar : işlem günleri (herhangi sırada; date/Timestamp kabul eder).
    frequency: monthly | biweekly. Bilinmeyen değer monthly gibi ele alınır.
    """
    days: set[pd.Timestamp] = set()
    seen_month: set[tuple[int, int]] = set()
    seen_half: set[tuple[int, int]] = set()
    for d in _as_timestamps(calendar):
        key = (d.year, d.month)
        if key not in seen_month:
            seen_month.add(key)
            days.add(d)
        if (frequency == BIWEEKLY and d.day >= _BIWEEKLY_SECOND_HALF_DAY
                and key not in seen_half):
            seen_half.add(key)
            days.add(d)
    return days


def is_rotation_day(day, calendar: Sequence, frequency: str = MONTHLY) -> bool:
    """`day`, verilen takvimde bir rotasyon günü mü?

    Canlı akış bunu günlük tetikte çağırır: `day` = bugünün (son) işlem günü,
    `calendar` = fiyat barlarından kurulan gerçek işlem-günü takvimi. Rotasyon
    günü değilse akış yalnız-izleme moduna geçer.
    """
    return pd.Timestamp(day).normalize() in rotation_days(calendar, frequency)
