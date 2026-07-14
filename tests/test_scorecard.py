"""Karne (Görev C.2) testleri — ağ/Sheets gerektirmez.

İleri getiri elle müdahalesiz dolar (pencere kapandıkça); sistem/sistem-dışı
ayrımı önerilerle mutabakatlanır.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from bot.logging.sheets import KARNE_HEADERS
from bot.reporting import scorecard as sc
from bot.reporting import (
    build_scorecard_entries,
    entry_to_row,
    fill_forward_returns,
    forward_return,
    monthly_summary,
    reconcile_positions,
    update_karne,
)
from bot.rotation.alerts import SellAlert, SellTrigger, TriggerType
from bot.rotation.live import BuySuggestion, LiveDecision

IDX = pd.bdate_range(end="2022-03-31", periods=90)


def _linear_bars(start=100.0, step=1.0):
    close = pd.Series([start + step * i for i in range(len(IDX))], index=IDX)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1e6}, index=IDX)


def _decision():
    d = LiveDecision(as_of=date(2022, 2, 1), frequency="biweekly", is_rotation_day=True)
    d.rotation_entries = [BuySuggestion("SPY", "low_volatility", "broad_market",
                                        0.2, 150.0, 2, 300.0, 1, "yeni giren")]
    d.slot_fills = []
    d.sell_alerts = [SellAlert("NVDA", [SellTrigger(TriggerType.RANKING, "çöküş")], 7)]
    d.prices = {"SPY": 150.0, "NVDA": 200.0}
    return d


def test_columns_match_sheet_headers():
    assert sc.COLUMNS == KARNE_HEADERS


def test_build_entries_from_decision():
    entries = build_scorecard_entries(_decision())
    kinds = {(e.symbol, e.kind) for e in entries}
    assert ("SPY", sc.KIND_ROTATION_ENTRY) in kinds
    assert ("NVDA", sc.KIND_SELL_ALERT) in kinds
    spy = next(e for e in entries if e.symbol == "SPY")
    assert spy.price == 150.0 and spy.source == sc.SOURCE_SYSTEM
    assert spy.ret_5 is None and spy.ret_20 is None    # getiriler başta boş


def test_forward_return_window_elapsed_vs_open():
    bars = {"SPY": _linear_bars(100.0, 1.0)}
    d0 = IDX[0].date().isoformat()
    # 5 gün sonra: close 105 / 100 - 1 = %5
    assert forward_return(bars, "SPY", d0, 5) == 5.0
    # pencere kapanmadı: son günden 5 gün sonrası yok -> None
    last = IDX[-1].date().isoformat()
    assert forward_return(bars, "SPY", last, 5) is None
    # bilinmeyen sembol -> None
    assert forward_return(bars, "ZZZ", d0, 5) is None


def test_fill_forward_returns_only_when_elapsed():
    bars = {"SPY": _linear_bars(100.0, 1.0)}
    # signal iki gün önce -> 5g/20g/60g pencereleri kapanmamış
    e_recent = sc.ScorecardEntry(IDX[-2].date().isoformat(), "SPY", sc.KIND_ROTATION_ENTRY,
                                 sc.SOURCE_SYSTEM, 100.0)
    # signal en başta -> 5g/20g/60g hepsi kapanmış
    e_old = sc.ScorecardEntry(IDX[0].date().isoformat(), "SPY", sc.KIND_ROTATION_ENTRY,
                              sc.SOURCE_SYSTEM, 100.0)
    filled = fill_forward_returns([e_recent, e_old], bars)
    assert e_recent.ret_5 is None                      # kapanmadı
    assert e_old.ret_5 == 5.0 and e_old.ret_20 == 20.0 and e_old.ret_60 == 60.0
    assert filled == 3


def test_reconcile_positions_system_vs_manual():
    history = [sc.ScorecardEntry("2022-01-01", "SPY", sc.KIND_ROTATION_ENTRY,
                                 sc.SOURCE_SYSTEM, 100.0)]
    holdings = [{"symbol": "SPY", "shares": 2}, {"symbol": "GME", "shares": 5}]
    labels = reconcile_positions(holdings, history)
    assert labels["SPY"] == sc.SOURCE_SYSTEM       # sistem önerdi
    assert labels["GME"] == sc.SOURCE_MANUAL       # sistem hiç önermedi -> sistem-dışı


def test_update_karne_adds_manual_position_row_and_dedupes():
    bars = {"SPY": _linear_bars(100.0, 1.0)}
    holdings = [{"symbol": "GME", "shares": 5, "entry_price": 20.0,
                 "entry_date": "2022-01-03"}]
    d = _decision()
    # 1. koşu
    entries = update_karne([], d, bars, holdings)
    manual = [e for e in entries if e.kind == sc.KIND_MANUAL_POSITION]
    assert len(manual) == 1 and manual[0].symbol == "GME" and manual[0].source == sc.SOURCE_MANUAL
    # 2. koşu aynı girdiyle -> tekrar eklenmemeli (dedupe)
    rows = [dict(zip(sc.COLUMNS, entry_to_row(e))) for e in entries]
    entries2 = update_karne(rows, d, bars, holdings)
    assert len(entries2) == len(entries)


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


def test_sheets_karne_write_then_read(monkeypatch):
    from bot.config import Secrets
    from bot.logging.sheets import SheetsLogger
    ws = _FakeWS()
    logger = SheetsLogger(Secrets.load(strict=False))
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: ws)
    e = sc.ScorecardEntry("2022-02-01", "SPY", sc.KIND_ROTATION_ENTRY, sc.SOURCE_SYSTEM,
                          150.0, ret_5=5.0)
    logger.write_karne([entry_to_row(e)])
    assert ws.cleared and ws.appended[0] == KARNE_HEADERS
    assert ["2022-02-01", "SPY", sc.KIND_ROTATION_ENTRY, sc.SOURCE_SYSTEM, 150.0, 5.0, "", ""] in ws.appended
    # geri okuma
    ws._records = [dict(zip(KARNE_HEADERS,
                            ["2022-02-01", "SPY", sc.KIND_ROTATION_ENTRY, sc.SOURCE_SYSTEM,
                             150.0, 5.0, "", ""]))]
    back = sc.row_to_entry(logger.read_karne()[0])
    assert back.symbol == "SPY" and back.ret_5 == 5.0 and back.ret_20 is None


def test_monthly_summary_portfolio_spy_universe():
    # SPY %+10 (100->110 over 21g step .5? use 21g), portföy 2xSPY -> aynı %
    bars = {
        "SPY": _linear_bars(100.0, 1.0),
        "AAA": _linear_bars(100.0, 2.0),
    }
    holdings = [{"symbol": "SPY", "shares": 2}]
    s = monthly_summary(bars, holdings, ["SPY", "AAA"], IDX[-1], lookback_days=21)
    assert s["spy_pct"] is not None and s["portfolio_pct"] == s["spy_pct"]
    # evren ortalaması iki sembolün getirisinin ortalaması
    assert s["universe_pct"] > s["spy_pct"]         # AAA daha dik -> ortalama SPY'den yüksek
