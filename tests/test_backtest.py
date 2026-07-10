"""Backtest birim testleri — ağ/anahtar gerektirmez."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backtest.backtest import Trade, _build_signal_frame, _metrics
from bot.config import Strategy

TECH_CFG = Strategy.load().technical


def _synthetic_df(n: int = 260, drift: float = 0.3) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    idx = pd.bdate_range("2022-01-01", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, n)},
        index=idx,
    )


def test_build_signal_frame_contract():
    sf = _build_signal_frame(_synthetic_df(), TECH_CFG, buy=0.30, sell=-0.30)
    assert list(sf.columns) == ["close", "score", "decision"]
    assert len(sf) == 260
    assert set(sf["decision"].unique()) <= {"BUY", "SELL", "HOLD"}
    assert sf["score"].between(-1, 1).all()


def test_metrics_computes_returns_and_winrate():
    # 90 günde 1000 -> 1150 (=%15) doğrusal özsermaye eğrisi
    dates = pd.bdate_range("2024-01-01", periods=90)
    equity = pd.Series(np.linspace(1000, 1150, 90), index=dates)
    trades = [
        Trade("A", "low_volatility", "2024-01-02", "2024-01-10", 10, 11, 5, 5.0, 10.0, "signal_sell"),
        Trade("B", "high_volatility", "2024-02-02", "2024-02-10", 20, 19, 5, -5.0, -5.0, "signal_sell"),
    ]
    r = _metrics(equity, trades, initial=1000.0, years=3, sig_frames={})
    assert r.total_return_pct == pytest.approx(15.0, abs=0.1)
    assert r.num_trades == 2
    assert r.win_rate_pct == pytest.approx(50.0)
    assert r.max_drawdown_pct == pytest.approx(0.0)   # sürekli artan eğri
    assert r.benchmark_return_pct is None             # SPY verilmedi


def test_metrics_drawdown_detected():
    dates = pd.bdate_range("2024-01-01", periods=5)
    equity = pd.Series([1000, 1200, 900, 950, 1100], index=dates)  # 1200 -> 900 = -%25
    r = _metrics(equity, [], initial=1000.0, years=1, sig_frames={})
    assert r.max_drawdown_pct == pytest.approx(-25.0, abs=0.1)
