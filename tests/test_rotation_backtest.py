"""Rotasyon backtest'i (Görev B.1) birim testleri — ağ/anahtar gerektirmez.

Sentetik barlarla motorun determinizmini, maliyet muhasebesini, satış-uyarısı
tetiklerini ve kapsam raporunu doğrular. Skorlama s2_momentum (kısa pencere) ile
yapılır ki sentetik veri kısa tutulabilsin.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.config import Strategy
from backtest.rotation_backtest import run_rotation_backtest


# ----------------------------------------------------------------------
#  Sentetik veri ve strateji yardımcıları
# ----------------------------------------------------------------------
def _bars(daily_return: float, n: int = 160, start="2020-01-01", *,
          base: float = 100.0, crash_at: int | None = None,
          crash_factor: float = 0.5) -> pd.DataFrame:
    """Sabit günlük getirili OHLCV çerçevesi (deterministik sıralama için).

    crash_at verilirse o günden itibaren fiyat crash_factor ile bir kez çöker
    (teknik acil durum tetiğini test etmek için).
    """
    idx = pd.bdate_range(start=start, periods=n)
    closes = []
    price = base
    for i in range(n):
        if crash_at is not None and i == crash_at:
            price *= crash_factor
        else:
            price *= (1 + daily_return)
        closes.append(price)
    close = pd.Series(closes, index=idx)
    open_ = close.shift(1).fillna(base)
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.01
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.99
    vol = pd.Series(1_000_000, index=idx)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def _strategy(**rotation_overrides) -> Strategy:
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {})
    strat.raw["rotation"].update(
        {"score": "s2_momentum", "frequency": "monthly",
         "momentum": {"lookback_days": 5, "skip_days": 1}}
    )
    strat.raw["rotation"].update(rotation_overrides)
    return strat


def _universe_bars() -> dict[str, pd.DataFrame]:
    """Her sepetten iki sembol + SPY; farklı drift → deterministik sıralama."""
    return {
        # low_volatility
        "JNJ": _bars(0.004), "PG": _bars(0.003), "SPY": _bars(0.002),
        # high_volatility
        "NVDA": _bars(0.006), "AMD": _bars(0.005),
        # under_radar
        "IONQ": _bars(0.007), "RKLB": _bars(0.0055),
    }


# ----------------------------------------------------------------------
#  Testler
# ----------------------------------------------------------------------
def test_runs_and_produces_trades():
    strat = _strategy()
    bars = _universe_bars()
    r = run_rotation_backtest(strat, bars, apply_costs=True)
    assert r.num_trades > 0
    assert r.equity_curve is not None and not r.equity_curve.empty
    # En yüksek driftli semboller (NVDA/IONQ) portföye girmiş olmalı
    entered = {t.symbol for t in r.trades}
    assert "NVDA" in entered and "IONQ" in entered


def test_determinism_bitwise():
    """Kabul kriteri: aynı girdi → bit-bazında aynı sonuç."""
    strat = _strategy()
    bars = _universe_bars()
    r1 = run_rotation_backtest(strat, bars, apply_costs=True)
    r2 = run_rotation_backtest(strat, bars, apply_costs=True)
    assert r1.final_equity == r2.final_equity
    assert r1.total_cost == r2.total_cost
    assert list(r1.equity_curve.values) == list(r2.equity_curve.values)
    assert [t.__dict__ for t in r1.trades] == [t.__dict__ for t in r2.trades]


def test_cost_free_vs_costed():
    """Maliyetli/maliyetsiz fark raporlanabilir; maliyet getiriyi düşürür."""
    strat = _strategy()
    bars = _universe_bars()
    costed = run_rotation_backtest(strat, bars, apply_costs=True)
    free = run_rotation_backtest(strat, bars, apply_costs=False)
    assert costed.total_cost > 0
    assert free.total_cost == 0.0
    # Maliyet nihai özsermayeyi düşürmeli (yükseliş piyasasında)
    assert free.final_equity >= costed.final_equity


def test_slippage_scale_increases_cost():
    strat = _strategy()
    bars = _universe_bars()
    base = run_rotation_backtest(strat, bars, apply_costs=True, slippage_scale=1.0)
    high = run_rotation_backtest(strat, bars, apply_costs=True, slippage_scale=2.0)
    assert high.total_cost > base.total_cost


def test_technical_emergency_exit():
    """Girişten sonra çöken bir pozisyon rotasyon-dışı satış tetiğiyle çıkar."""
    strat = _strategy()
    bars = _universe_bars()
    # NVDA erken girer; ~90. günde çökertelim → teknik acil / sıralama çöküşü
    bars["NVDA"] = _bars(0.006, crash_at=90, crash_factor=0.4)
    r = run_rotation_backtest(strat, bars, apply_costs=True)
    reasons = {t.exit_reason for t in r.trades if t.symbol == "NVDA"}
    assert reasons & {"technical_emergency", "ranking_collapse"}


def test_coverage_report():
    strat = _strategy()
    bars = _universe_bars()
    r = run_rotation_backtest(strat, bars, apply_costs=True)
    # Sağlanan barlar: low_volatility 2 (JNJ, PG) — SPY de low_volatility → 3
    assert r.coverage["low_volatility"][0] == 3
    assert r.coverage["high_volatility"][0] == 2
    assert r.coverage["under_radar"][0] == 2
    # Toplam sayılar evrenin tamamını yansıtır
    assert r.coverage["high_volatility"][1] >= 2


def test_window_filtering():
    strat = _strategy()
    bars = _universe_bars()
    full = run_rotation_backtest(strat, bars)
    half = run_rotation_backtest(strat, bars, start="2020-04-01")
    assert pd.Timestamp(half.start) >= pd.Timestamp("2020-04-01")
    assert pd.Timestamp(full.start) < pd.Timestamp("2020-04-01")
