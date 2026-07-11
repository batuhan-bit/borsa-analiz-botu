"""Sinyal motoru iki-aşamalı akış testleri — ağ/anahtar gerektirmez.

Alpha Vantage çağrılarının yalnızca en güçlü adaylara ve max_symbols_per_run
sınırına kadar yapıldığını doğrular (ücretsiz limit koruması).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.config import Settings
from bot.signals import SignalEngine


def _synthetic_df(n: int = 260) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0.3, 1.0, n))
    idx = pd.bdate_range("2022-01-01", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, n)},
        index=idx,
    )


def test_run_caps_fundamental_enrichment(monkeypatch):
    s = Settings.load(strict=False)
    # Her sepetten 3 sembol -> 9 sembol
    for _name, cfg in s.strategy.baskets.items():
        cfg["universe"] = cfg["universe"][:3]
    s.strategy.raw["fundamental"]["max_symbols_per_run"] = 2
    s.strategy.raw["fundamental"]["min_technical_abs"] = 0.0   # hepsi aday olabilsin

    eng = SignalEngine(s)
    df = _synthetic_df()
    monkeypatch.setattr(eng, "_get_bars", lambda symbol, *, years=1.0: df)
    eng._av = object()   # Alpha Vantage varmış gibi davran

    called: list[str] = []
    monkeypatch.setattr(eng, "_get_fundamental_data",
                        lambda symbol, price: (called.append(symbol) or {}))

    signals = eng.run()
    assert len(signals) == 9                    # tüm evren döner
    assert len(called) == 2                     # yalnızca 2 sembol zenginleştirildi (cap)


def test_run_skips_fundamental_when_no_av(monkeypatch):
    s = Settings.load(strict=False)
    for _name, cfg in s.strategy.baskets.items():
        cfg["universe"] = cfg["universe"][:2]

    eng = SignalEngine(s)
    eng._av = None       # AV yok
    df = _synthetic_df()
    monkeypatch.setattr(eng, "_get_bars", lambda symbol, *, years=1.0: df)

    called: list[str] = []
    monkeypatch.setattr(eng, "_get_fundamental_data",
                        lambda symbol, price: (called.append(symbol) or {}))

    signals = eng.run()
    assert len(signals) == 6
    assert called == []   # AV yokken hiç temel çağrı yapılmaz
