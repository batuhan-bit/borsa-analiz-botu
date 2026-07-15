"""Cooldown kalıcılığı testleri (Görev C.1) — ağ/Sheets gerektirmez.

Tarih-çıpalı depo, çekilen geçmiş penceresinden BAĞIMSIZ olmalı: aynı uyarı
tarihi + aynı "bugün", takvim ne kadar geriye giderse gitsin aynı blok kararını
vermeli. AlertCooldown backtest ile aynı sınıftır (birebir desen).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from bot.config import Secrets, Strategy
from bot.logging.sheets import COOLDOWN_HEADERS, SheetsLogger
from bot.rotation.cooldown_store import (
    InMemoryCooldownStore,
    SheetsCooldownStore,
    active_cooldown_dates,
    reconstruct_cooldown,
)


def _strat() -> Strategy:
    return Strategy.load()   # slot_refill_cooldown_days = 5 (config)


def _cal(start, end):
    return list(pd.bdate_range(start, end))


def _idx(cal, day):
    return {pd.Timestamp(d).normalize(): i for i, d in enumerate(cal)}[pd.Timestamp(day)]


# ---------------------------------------------------------------------------
#  reconstruct_cooldown
# ---------------------------------------------------------------------------
def test_reconstruct_blocks_within_window_and_frees_after():
    strat = _strat()                       # cd = 5 işlem günü
    cal = _cal("2021-01-04", "2021-01-29")
    stored = {"AAA": date(2021, 1, 7)}     # cal indeksi 3
    cd = reconstruct_cooldown(strat, stored, cal)
    alert_i = _idx(cal, "2021-01-07")
    assert cd.is_blocked("AAA", alert_i)          # aynı gün bloklu
    assert cd.is_blocked("AAA", alert_i + 4)      # 4 işlem günü sonra hâlâ bloklu
    assert not cd.is_blocked("AAA", alert_i + 5)  # 5. işlem günü serbest


def test_reconstruct_skips_dates_before_calendar_start():
    strat = _strat()
    cal = _cal("2021-06-01", "2021-06-30")
    stored = {"OLD": date(2019, 1, 1)}     # takvim başından çok önce -> süresi dolmuş
    cd = reconstruct_cooldown(strat, stored, cal)
    assert cd.blocked(0) == set()          # hiç kayıt kurulmadı


def test_window_independence_same_decision_regardless_of_history_length():
    strat = _strat()
    stored = {"AAA": date(2021, 1, 7)}
    short = _cal("2021-01-04", "2021-01-29")
    long = _cal("2019-01-01", "2021-01-29")   # çok daha geniş pencere, farklı indeksler
    for cal in (short, long):
        cd = reconstruct_cooldown(strat, stored, cal)
        # 2021-01-13 = uyarıdan 4 işlem günü sonra -> bloklu (her iki pencerede de)
        assert cd.is_blocked("AAA", _idx(cal, "2021-01-13"))
        # 2021-01-14 = 5 işlem günü sonra -> serbest (her iki pencerede de)
        assert not cd.is_blocked("AAA", _idx(cal, "2021-01-14"))


# ---------------------------------------------------------------------------
#  active_cooldown_dates (kaydedilecek durum)
# ---------------------------------------------------------------------------
def test_active_dates_keeps_blocked_drops_expired_adds_new():
    strat = _strat()
    cal = _cal("2021-01-04", "2021-01-29")
    # ESKI: 2021-01-05 uyarısı -> release index 1+5=6; bugün index 8 -> süresi dolmuş
    # HALA: 2021-01-11 uyarısı (index 5) -> release 10; bugün 8 -> bloklu
    stored = {"OLD": date(2021, 1, 5), "HELD": date(2021, 1, 11)}
    cd = reconstruct_cooldown(strat, stored, cal)
    today = date(2021, 1, 14)
    today_i = _idx(cal, "2021-01-14")      # 8
    # bugün YENİ kapanan bir sembol de cooldown'a girsin
    cd.register("NEW", today_i)
    out = active_cooldown_dates(cd, stored, newly_cooled_today={"NEW"},
                                today=today, today_index=today_i)
    assert "OLD" not in out                 # süresi doldu -> düştü
    assert out["HELD"] == date(2021, 1, 11) # orijinal uyarı tarihi korunur
    assert out["NEW"] == today              # yeni kapanan bugünle işaretlendi


# ---------------------------------------------------------------------------
#  Depo arka uçları
# ---------------------------------------------------------------------------
def test_inmemory_store_roundtrip():
    store = InMemoryCooldownStore({"AAA": date(2021, 1, 7)})
    assert store.load() == {"AAA": date(2021, 1, 7)}
    store.save({"BBB": date(2021, 2, 2)})
    assert store.load() == {"BBB": date(2021, 2, 2)}


class _FakeWS:
    def __init__(self, records=None):
        self._records = list(records or [])
        self.appended: list = []
        self.cleared = False

    def get_all_records(self):
        return list(self._records)

    def clear(self):
        self.cleared = True
        self._records = []

    def append_rows(self, rows, value_input_option=None):
        self.appended.extend(rows)


def _logger_with_ws(ws) -> SheetsLogger:
    logger = SheetsLogger(Secrets.load(strict=False))
    logger._worksheet = lambda title, headers: ws   # type: ignore[assignment]
    return logger


def test_sheets_store_write_then_read_via_fake_worksheet():
    ws = _FakeWS()
    logger = _logger_with_ws(ws)
    store = SheetsCooldownStore(logger, cooldown_days=5)
    store.save({"AAA": date(2021, 1, 7), "BBB": date(2021, 2, 2)})
    assert ws.cleared
    assert ws.appended[0] == COOLDOWN_HEADERS
    assert ["AAA", "2021-01-07", 5] in ws.appended
    # Yazılanı geri okumak için kayıtları taklit et
    ws._records = [
        {"Sembol": "AAA", "Uyarı Tarihi": "2021-01-07", "Bekleme (işlem günü)": 5},
        {"Sembol": "BBB", "Uyarı Tarihi": "2021-02-02", "Bekleme (işlem günü)": 5},
    ]
    assert store.load() == {"AAA": date(2021, 1, 7), "BBB": date(2021, 2, 2)}


def test_sheets_store_disabled_logger_is_graceful():
    logger = SheetsLogger(Secrets.load(strict=False))   # kimlik yok -> devre dışı
    store = SheetsCooldownStore(logger, cooldown_days=5)
    assert store.load() == {}          # boş
    store.save({"AAA": date(2021, 1, 7)})   # çökmemeli (no-op)
