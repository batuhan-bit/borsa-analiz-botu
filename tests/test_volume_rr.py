"""Yönlü hacim + R/R kapısı testleri — ağ gerektirmez."""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.config import Settings, Strategy
from bot.models import SignalType
from bot.signals import SignalEngine
from bot.signals.technical import indicator_frame

TECH_CFG = Strategy.load().technical


def _series_df(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-01", periods=len(closes))
    close = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": pd.Series(volumes, index=idx, dtype=float)},
        index=idx,
    )


def test_vol_direction_accumulation():
    # Sürekli yükseliş -> tüm hacim yükseliş günlerinde -> vol_direction ≈ +1
    n = 40
    df = _series_df([100 + i for i in range(n)], [1_000_000] * n)
    f = indicator_frame(df, TECH_CFG)
    assert f["vol_direction"].iloc[-1] > 0.8


def test_vol_direction_distribution():
    # Sürekli düşüş -> tüm hacim düşüş günlerinde -> vol_direction ≈ -1
    n = 40
    df = _series_df([200 - i for i in range(n)], [1_000_000] * n)
    f = indicator_frame(df, TECH_CFG)
    assert f["vol_direction"].iloc[-1] < -0.8


def _uptrend_df(n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    close = 50 + np.cumsum(np.abs(rng.normal(0.4, 0.5, n)))  # istikrarlı yukarı
    idx = pd.bdate_range("2022-01-01", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, n)},
        index=idx,
    )


def test_rr_gate_downgrades_low_risk_reward(monkeypatch):
    """R/R eşiğin altındaysa BUY -> HOLD; üstündeyse BUY kalır."""
    import bot.signals.levels as levels_mod

    s = Settings.load(strict=False)
    for _n, cfg in s.strategy.baskets.items():
        cfg["universe"] = cfg["universe"][:1]
    s.strategy.raw["signals"]["min_risk_reward"] = 1.0

    eng = SignalEngine(s)
    eng._av = None
    eng._marketaux = None
    eng._insider = None
    monkeypatch.setattr(eng, "_get_bars", lambda symbol, *, years=1.0: _uptrend_df())
    monkeypatch.setattr(eng, "_decide", lambda final: SignalType.BUY)   # daima BUY karar

    def _levels(rr):
        return lambda d, price, **k: {
            "stop": 1, "support": 1, "resistance": 1,
            "target1": 1, "target2": 1, "risk_reward": rr,
        }

    # R/R 0.5 < 1.0 -> HOLD'a çevrilir
    monkeypatch.setattr(levels_mod, "price_levels", _levels(0.5))
    assert all(x.signal is not SignalType.BUY for x in eng.run())

    # R/R 2.0 >= 1.0 -> BUY kalır
    monkeypatch.setattr(levels_mod, "price_levels", _levels(2.0))
    assert any(x.signal is SignalType.BUY for x in eng.run())
