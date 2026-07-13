"""Görev 1.2 testleri: tarih aralığı, kapsam raporu, varyant anahtarları."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import backtest.backtest as bt
from bot.config import Settings, Strategy
from bot.signals.technical import technical_score

TECH_CFG = Strategy.load().technical


def _synthetic_bars(start: str, end: str, seed: int = 3, base: float = 100.0) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.normal(0.05, 1.0, len(idx)))
    close = np.maximum(close, 1.0)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, len(idx))},
        index=idx,
    )


# ----------------------------------------------------------------------
#  Trend filtresi ağırlık=0 -> bileşen hiç eklenmez (skoru sulandırmaz)
# ----------------------------------------------------------------------
def test_zero_trend_weight_disables_component():
    indicators = {
        "close": 90.0, "rsi": 50.0,
        "macd": -1.0, "macd_prev": -1.0, "macd_signal": 0.0, "macd_signal_prev": 0.0,
        "ma_short": 100.0, "ma_short_prev": 100.0,
        "ma_long": 110.0, "ma_long_prev": 110.0,
        "volume_ratio": 1.0, "vol_direction": None,
    }
    import copy
    cfg_off = copy.deepcopy(TECH_CFG)
    cfg_off["trend_filter"] = {"price_vs_ma_long": 0.0, "price_vs_ma_short": 0.0}

    score_on, reasons_on = technical_score(indicators, TECH_CFG)
    score_off, reasons_off = technical_score(indicators, cfg_off)

    # Fiyat MA'ların altında: filtre açıkken skor daha negatif olmalı
    assert score_off > score_on
    assert any("200G" in r for r in reasons_on)
    assert not any("200G" in r for r in reasons_off)


# ----------------------------------------------------------------------
#  Tarih aralığı + kapsam raporu (ağ yok — load_bars monkeypatch)
# ----------------------------------------------------------------------
@pytest.fixture()
def fake_bars(monkeypatch):
    def _load(symbol, *, years=3.0, start=None, end=None):
        # IONQ geç listelenen sembolü temsil eder (2016 ortası)
        if symbol == "IONQ":
            eff_start = "2016-06-01"
            if start and pd.Timestamp(start) > pd.Timestamp(eff_start):
                eff_start = start
            return _synthetic_bars(eff_start, end or "2017-06-30", seed=5)
        return _synthetic_bars(start or "2014-01-01", end or "2017-06-30",
                               seed=hash(symbol) % 100)

    monkeypatch.setattr(bt, "load_bars", _load)
    return _load


def test_range_mode_trades_only_inside_window(fake_bars):
    settings = Settings.load(strict=False)
    r = bt.run_backtest(settings, basket_limit=1,
                        start="2016-01-04", end="2016-12-30", verbose=False)
    assert r.equity_curve.index[0] >= pd.Timestamp("2016-01-04")
    assert r.equity_curve.index[-1] <= pd.Timestamp("2016-12-30")
    assert r.start >= "2016-01-04" and r.end <= "2016-12-30"


def test_coverage_reports_late_joiner(fake_bars):
    settings = Settings.load(strict=False)
    r = bt.run_backtest(settings, basket_limit=1,
                        start="2016-01-04", end="2017-06-30", verbose=False)
    # basket_limit=1 -> low_vol: SPY, high_vol: NVDA, under_radar: IONQ
    cov = r.coverage
    assert set(cov) == {"low_volatility", "high_volatility", "under_radar"}
    assert cov["low_volatility"]["active_at_start"] == 1
    assert "IONQ" in cov["under_radar"]["late_joiners"]
    join_date = cov["under_radar"]["late_joiners"]["IONQ"]
    assert join_date.startswith("2016-06")


def test_default_mode_unchanged_without_dates(fake_bars):
    settings = Settings.load(strict=False)
    r = bt.run_backtest(settings, basket_limit=1, verbose=False)
    # Range verilmedi -> tüm sentetik dönem işlem görür (eski davranış)
    assert r.equity_curve.index[0] <= pd.Timestamp("2014-02-01")


def test_disable_flags_change_signals(fake_bars):
    settings = Settings.load(strict=False)
    base = bt.run_backtest(settings, basket_limit=1,
                           start="2016-01-04", end="2016-12-30", verbose=False)
    variant = bt.run_backtest(settings, basket_limit=1,
                              start="2016-01-04", end="2016-12-30",
                              disable_trend_filter=True,
                              disable_volume_direction=True,
                              disable_rr_gate=True, verbose=False)
    # Aynı veri, farklı konfigürasyon -> sonuçlar birebir aynı olmamalı
    assert (base.num_trades, base.total_return_pct) != (variant.num_trades, variant.total_return_pct)
