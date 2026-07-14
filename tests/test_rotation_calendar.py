"""Rotasyon ritmi testleri (Görev C.1) — tatil/hafta sonu kayması dahil.

Takvim gerçek işlem günlerinden kurulur; ritim ona uyar. Bu testler ağ
gerektirmez: sentetik işlem-günü takvimleri kurulur.
"""
from __future__ import annotations

import pandas as pd

from bot.rotation.calendar import is_rotation_day, rotation_days


def _cal(start, end):
    """İki tarih arası İŞ GÜNÜ (hafta sonu hariç) takvimi — normalize Timestamp."""
    return list(pd.bdate_range(start, end))


def test_monthly_picks_first_trading_day_each_month():
    cal = _cal("2021-01-01", "2021-03-31")
    days = rotation_days(cal, "monthly")
    # 2021-01-01 Cuma ama ayın ilk İŞ günü; Şubat ilk iş günü 02-01 (Pzt);
    # Mart ilk iş günü 03-01 (Pzt).
    assert pd.Timestamp("2021-01-01") in days
    assert pd.Timestamp("2021-02-01") in days
    assert pd.Timestamp("2021-03-01") in days
    # Yalnız 3 rotasyon günü (aylık, 3 ay).
    assert len(days) == 3


def test_weekend_shift_first_trading_day_is_monday():
    # 2021-05-01 CUMARTESİ → mayısın ilk işlem günü 05-03 (Pazartesi).
    cal = _cal("2021-05-01", "2021-05-31")
    days = rotation_days(cal, "monthly")
    assert pd.Timestamp("2021-05-03") in days
    assert pd.Timestamp("2021-05-01") not in days   # cumartesi zaten takvimde yok


def test_holiday_shift_uses_next_available_trading_day():
    # Tatili simüle et: ayın ilk iş gününü takvimden çıkar → ikinci gün rotasyon olur.
    cal = _cal("2021-06-01", "2021-06-30")
    first = cal[0]                       # 2021-06-01 (Salı)
    cal_holiday = cal[1:]               # 06-01 tatil kabul; ilk işlem günü 06-02
    days = rotation_days(cal_holiday, "monthly")
    assert first not in days
    assert cal_holiday[0] in days
    assert cal_holiday[0] == pd.Timestamp("2021-06-02")


def test_biweekly_adds_second_window_after_15th():
    cal = _cal("2021-06-01", "2021-06-30")
    days = rotation_days(cal, "biweekly")
    # İlk işlem günü + 15'inden sonraki ilk işlem günü. 2021-06-15 Salı (iş günü).
    assert pd.Timestamp("2021-06-01") in days
    assert pd.Timestamp("2021-06-15") in days
    assert len(days) == 2


def test_biweekly_second_window_shifts_when_15th_is_weekend():
    # 2021-08-15 PAZAR → 15-sonrası ilk işlem günü 08-16 (Pazartesi).
    cal = _cal("2021-08-01", "2021-08-31")
    days = rotation_days(cal, "biweekly")
    assert pd.Timestamp("2021-08-16") in days
    assert pd.Timestamp("2021-08-15") not in days


def test_is_rotation_day_true_only_on_rotation_days():
    cal = _cal("2021-06-01", "2021-06-30")
    assert is_rotation_day("2021-06-01", cal, "biweekly") is True
    assert is_rotation_day("2021-06-15", cal, "biweekly") is True
    # Ayın ortasındaki (15 öncesi) sıradan bir gün rotasyon değil.
    assert is_rotation_day("2021-06-08", cal, "biweekly") is False
    # Aylık ritimde 15-sonrası gün rotasyon değil.
    assert is_rotation_day("2021-06-15", cal, "monthly") is False


def test_accepts_date_and_timestamp_inputs():
    import datetime as _dt
    cal = _cal("2021-06-01", "2021-06-30")
    assert is_rotation_day(_dt.date(2021, 6, 1), cal, "monthly") is True
    assert is_rotation_day(pd.Timestamp("2021-06-01"), cal, "monthly") is True
