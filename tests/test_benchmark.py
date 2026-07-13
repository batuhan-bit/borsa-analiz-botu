"""Benchmark (al-ve-tut) ve ortak metrik birim testleri — ağ gerektirmez."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.benchmark import benchmark_suite, buy_and_hold
from backtest.metrics import (
    cagr_pct,
    calmar_ratio,
    max_drawdown_pct,
    sharpe_ratio,
    total_return_pct,
)


def _bars(start: str, closes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 1_000_000},
        index=idx,
    )


def test_buy_and_hold_equal_weight_two_symbols():
    # A: 100 -> 120 (%20), B: 50 -> 45 (-%10); eşit ağırlık -> ortalama %5
    bars = {
        "A": _bars("2024-01-01", list(np.linspace(100, 120, 60))),
        "B": _bars("2024-01-01", list(np.linspace(50, 45, 60))),
    }
    r = buy_and_hold(bars, {"A": 1.0, "B": 1.0}, 1000.0, "test")
    assert r.n_symbols == 2
    assert r.total_return_pct == pytest.approx(5.0, abs=0.01)
    assert r.final_equity == pytest.approx(1050.0, abs=0.1)
    assert r.late_joiners == {}


def test_buy_and_hold_late_joiner_waits_in_cash():
    # B dönem ortasında listeleniyor; öncesinde payı nakitte (değer sabit)
    bars = {
        "A": _bars("2024-01-01", [100.0] * 60),           # yatay
        "B": _bars("2024-02-19", list(np.linspace(10, 12, 25))),  # geç katılan, +%20
    }
    r = buy_and_hold(bars, {"A": 1.0, "B": 1.0}, 1000.0, "test")
    assert "B" in r.late_joiners
    # A yatay (%0), B +%20, eşit sermaye -> toplam +%10
    assert r.total_return_pct == pytest.approx(10.0, abs=0.05)
    # B listelenmeden önce eğri tam 1000 (nakit + A sabit)
    assert r.equity_curve.iloc[0] == pytest.approx(1000.0, abs=0.01)


def test_buy_and_hold_drops_missing_symbols_and_renormalizes():
    bars = {"A": _bars("2024-01-01", list(np.linspace(100, 110, 30))), "YOK": pd.DataFrame()}
    r = buy_and_hold(bars, {"A": 1.0, "YOK": 1.0}, 1000.0, "test")
    assert r.n_symbols == 1
    assert r.total_return_pct == pytest.approx(10.0, abs=0.01)


def test_benchmark_suite_produces_three_lines():
    closes = list(np.linspace(100, 130, 90))
    baskets = {
        "low_volatility": {"allocation_pct": 40, "universe": ["SPY", "KO"]},
        "high_volatility": {"allocation_pct": 35, "universe": ["NVDA"]},
        "under_radar": {"allocation_pct": 25, "universe": ["IONQ"]},
    }
    bars = {s: _bars("2024-01-01", closes) for s in ["SPY", "KO", "NVDA", "IONQ"]}
    results = benchmark_suite(bars, baskets, 3000.0)
    assert [r.name for r in results] == [
        "Eşit-ağırlık evren (al-tut)",
        "Sepet-ağırlıklı evren (al-tut)",
        "SPY (al-tut)",
    ]
    # Tüm semboller aynı seriyi izliyor -> üç çizgi de aynı getiriyi vermeli
    for r in results:
        assert r.total_return_pct == pytest.approx(30.0, abs=0.01)


def test_metrics_sharpe_and_calmar():
    idx = pd.bdate_range("2024-01-01", periods=252)
    up = pd.Series(np.linspace(1000, 1200, 252), index=idx)
    assert total_return_pct(up) == pytest.approx(20.0, abs=0.01)
    assert sharpe_ratio(up) > 0
    assert max_drawdown_pct(up) == pytest.approx(0.0)
    assert calmar_ratio(up) is None  # düşüş yok -> tanımsız

    dipped = pd.Series([1000, 1100, 880, 990, 1210], index=pd.bdate_range("2024-01-01", periods=5))
    assert max_drawdown_pct(dipped) == pytest.approx(-20.0, abs=0.01)
    calmar = calmar_ratio(dipped)
    assert calmar is not None and calmar == pytest.approx(cagr_pct(dipped) / 20.0, rel=1e-6)
