"""Fiyat seviyeleri (stop/destek/hedef) testleri — ağ gerektirmez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.signals.levels import price_levels


def _df(n=80):
    rng = np.random.default_rng(11)
    close = 100 + np.cumsum(rng.normal(0.2, 1.0, n))
    idx = pd.bdate_range("2023-01-01", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 2, "low": close - 2, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, n)},
        index=idx,
    )


def test_levels_basic_ordering():
    df = _df()
    entry = float(df["close"].iloc[-1])
    lv = price_levels(df, entry)
    # Stop girişin altında, hedefler girişin üstünde
    assert lv["stop"] < entry
    assert lv["target1"] > entry
    assert lv["target2"] >= lv["target1"]
    assert lv["support"] < entry


def test_stop_respects_max_loss_cap():
    df = _df()
    entry = float(df["close"].iloc[-1])
    lv = price_levels(df, entry, max_loss_pct=20.0)
    # Stop, girişten en fazla %20 aşağıda olabilir
    assert lv["stop"] >= entry * 0.80 - 0.01


def test_insufficient_data_returns_empty():
    df = _df(n=10)
    assert price_levels(df, 100.0) == {}
    assert price_levels(None, 100.0) == {}
