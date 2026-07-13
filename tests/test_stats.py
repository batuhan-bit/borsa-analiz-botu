"""Görev 1.3 testleri: bootstrap güven aralığı ve örneklem gürültüsü uyarısı."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.backtest import BacktestResult, Trade, _metrics, sample_noise_warning
from backtest.metrics import bootstrap_total_return_ci, ci_overlap


def test_bootstrap_ci_deterministic_and_sane():
    pnls = [50.0, -20.0, 30.0, 10.0, -40.0, 80.0, 5.0, -10.0]
    ci1 = bootstrap_total_return_ci(pnls, 1000.0, samples=2000)
    ci2 = bootstrap_total_return_ci(pnls, 1000.0, samples=2000)
    assert ci1 == ci2                       # sabit seed -> tekrarlanabilir
    lo, hi = ci1
    assert lo < hi
    point = sum(pnls) / 1000.0 * 100.0      # nokta tahmini aralığın içinde
    assert lo <= point <= hi


def test_bootstrap_ci_all_positive_trades_gives_positive_interval():
    ci = bootstrap_total_return_ci([10.0, 20.0, 15.0, 5.0], 1000.0, samples=1000)
    assert ci[0] > 0


def test_bootstrap_ci_needs_at_least_two_trades():
    assert bootstrap_total_return_ci([10.0], 1000.0) is None
    assert bootstrap_total_return_ci([], 1000.0) is None


def test_ci_overlap():
    assert ci_overlap((0.0, 10.0), (5.0, 15.0)) is True
    assert ci_overlap((0.0, 10.0), (11.0, 15.0)) is False
    assert ci_overlap(None, (0.0, 1.0)) is None


def test_metrics_includes_trade_stats_and_ci():
    dates = pd.bdate_range("2024-01-01", periods=60)
    equity = pd.Series(np.linspace(1000, 1100, 60), index=dates)
    trades = [
        Trade("A", "low_volatility", "2024-01-02", "2024-01-10", 10, 11, 5, 5.0, 10.0, "signal_sell"),
        Trade("B", "high_volatility", "2024-02-02", "2024-02-10", 20, 19, 5, -5.0, -5.0, "signal_sell"),
        Trade("C", "under_radar", "2024-02-12", "2024-02-20", 30, 33, 5, 15.0, 10.0, "signal_sell"),
    ]
    r = _metrics(equity, trades, initial=1000.0, years=1, sig_frames={}, bootstrap_samples=1000)
    assert r.num_closed_trades == 3
    assert r.avg_trade_return_pct == pytest.approx(5.0, abs=0.01)
    assert r.ci_low_pct is not None and r.ci_high_pct is not None
    assert r.ci_low_pct <= r.ci_high_pct


def _result(label: str, lo, hi) -> BacktestResult:
    return BacktestResult(
        initial_capital=1000, final_equity=1100, total_return_pct=10.0,
        annualized_return_pct=10.0, max_drawdown_pct=-5.0, win_rate_pct=50.0,
        num_trades=10, start="2024-01-01", end="2024-12-31",
        ci_low_pct=lo, ci_high_pct=hi, label=label,
    )


def test_sample_noise_warning_on_overlap():
    a, b = _result("A", 0.0, 20.0), _result("B", 10.0, 30.0)
    msg = sample_noise_warning(a, b)
    assert msg is not None and "örneklem gürültüsü" in msg

    c = _result("C", 25.0, 40.0)
    assert sample_noise_warning(a, c) is None  # ayrık aralıklar -> uyarı yok

    d = _result("D", None, None)
    assert "yorumlanamaz" in sample_noise_warning(a, d)
