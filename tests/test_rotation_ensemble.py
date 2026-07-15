"""Pertürbasyon topluluğu (Görev B.2) birim testleri — ağ/anahtar gerektirmez.

Sentetik barlarla topluluk determinizmini, bant üretimini, benchmark'ları,
tasarım-sağlığı uyarısını ve "bantsız rakam yok" kabul kriterini doğrular.
"""
from __future__ import annotations

import re

import pandas as pd

from bot.config import Strategy
from backtest.ensemble import (
    EnsembleStats,
    render_report_md,
    run_ensemble,
)
from tests.test_rotation_backtest import _bars, _strategy, _universe_bars


def _small_ensemble_strategy(**overrides) -> Strategy:
    strat = _strategy(**overrides)
    strat.raw.setdefault("rotation_backtest", {})
    # Hızlı ve deterministik topluluk
    strat.raw["rotation_backtest"].setdefault("ensemble", {})
    strat.raw["rotation_backtest"]["ensemble"].update(
        {"runs": 12, "start_jitter_days": 5, "slippage_jitter_pct": 50,
         "band_low_pct": 10, "band_high_pct": 90, "health_band_pct": 30, "seed": 7}
    )
    return strat


def test_ensemble_deterministic_same_seed():
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    r1 = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    r2 = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    assert r1.strategy_stats.samples == r2.strategy_stats.samples
    assert r1.runs == 12 == len(r1.strategy_stats.samples)


def test_ensemble_produces_band():
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    s = rep.strategy_stats
    assert s.p_low <= s.median <= s.p_high
    assert s.band_width >= 0


def test_benchmarks_present():
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    labels = {b.label for b in rep.benchmarks}
    assert labels == {"SPY al-tut", "Eşit-ağırlık evren", "Sepet-ağırlıklı evren"}
    for b in rep.benchmarks:
        assert b.samples          # boş değil


def test_strategy_maxdd_trades_cost_populated():
    """MaxDD/işlem sayısı/toplam maliyet her koşu için toplanır (medyan+bant)."""
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    assert len(rep.strategy_maxdd.samples) == rep.runs
    assert len(rep.strategy_trades.samples) == rep.runs
    assert len(rep.strategy_cost.samples) == rep.runs
    assert rep.strategy_maxdd.median <= 0.0          # düşüş her zaman <= 0
    assert rep.strategy_trades.median >= 0
    assert rep.strategy_cost.median >= 0.0


def test_benchmark_maxdd_matches_benchmark_labels():
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    dd_labels = {b.label for b in rep.benchmark_maxdd}
    assert dd_labels == {b.label for b in rep.benchmarks}
    for b in rep.benchmark_maxdd:
        assert b.samples
        assert b.median <= 0.0


def test_benchmark_maxdd_reflects_a_real_drawdown():
    """Pencere ortasında çöken bir benchmark sembolü sıfırdan farklı MaxDD üretmeli."""
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    bars["SPY"] = _bars(0.002, crash_at=60, crash_factor=0.7)
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    spy_dd = next(b for b in rep.benchmark_maxdd if b.label == "SPY al-tut")
    assert spy_dd.median < -10.0


def test_render_report_md_includes_maxdd_trades_cost_columns():
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    md = render_report_md(rep)
    header = next(line for line in md.splitlines() if "Seri" in line)
    assert "MaxDD" in header
    assert "İşlem sayısı" in header
    assert "Toplam maliyet" in header


def test_report_md_has_no_bandless_number():
    """Kabul kriteri: hiçbir tabloda bantsız getiri rakamı yok.

    Tablo satırındaki her yüzde değeri bir bant ([..,..]) ile birlikte olmalı.
    """
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    md = render_report_md(rep)
    # Tablo satırları (| ile başlayan, başlık/ayraç hariç)
    for line in md.splitlines():
        if not line.startswith("|") or "medyan" in line or "----" in line or "Seri" in line:
            continue
        # Getiri hücresi bir bant içermeli
        assert "[" in line and "]" in line, f"bantsız satır: {line}"


def test_health_warning_on_wide_band():
    """Medyan ~0 iken bant genişse tasarım-sağlığı uyarısı tetiklenir."""
    # Yapay olarak dar bir medyan ama geniş bir dağılım kur
    stats = EnsembleStats("x", [-40.0, -1.0, 0.0, 1.0, 40.0], 10, 90)
    threshold = 2.0 * 0.30 * abs(stats.median)     # medyan 0 -> eşik 0
    assert stats.band_width > threshold            # geniş bant


def test_health_ok_on_narrow_band():
    stats = EnsembleStats("x", [19.0, 20.0, 20.0, 20.0, 21.0], 10, 90)
    threshold = 2.0 * 0.30 * abs(stats.median)     # 12.0
    assert stats.band_width <= threshold


def test_cost_ratio_and_avg_capital_collected():
    """Görev D.2: topluluk yıllık-maliyet/ortalama-sermaye oranını da toplar."""
    strat = _small_ensemble_strategy()
    bars = _universe_bars()
    rep = run_ensemble(strat, bars, start="2020-01-15", end="2020-08-01")
    assert rep.strategy_cost_ratio_pct is not None
    assert len(rep.strategy_cost_ratio_pct.samples) == rep.runs
    assert rep.strategy_avg_capital is not None
    assert rep.strategy_avg_capital.median > 0
    # Oran negatif olamaz (maliyet ve sermaye pozitif)
    assert rep.strategy_cost_ratio_pct.median >= 0


def test_small_budget_has_higher_cost_ratio():
    """Görev D.2 çekirdek iddiası: küçük bütçe + sabit komisyon → daha yüksek
    yıllık-maliyet/ortalama-sermaye oranı (ölçek cezası görünür olmalı)."""
    bars = _universe_bars()
    std = _small_ensemble_strategy()
    std.raw["rotation_backtest"].update(
        {"initial_capital": 3000, "commission_fixed_usd": 0, "fractional_shares": False}
    )
    small = _small_ensemble_strategy()
    small.raw["rotation_backtest"].update(
        {"initial_capital": 1000, "commission_fixed_usd": 1.5, "fractional_shares": True}
    )
    r_std = run_ensemble(std, bars, start="2020-01-15", end="2020-08-01")
    r_small = run_ensemble(small, bars, start="2020-01-15", end="2020-08-01")
    assert r_small.strategy_cost_ratio_pct.median > r_std.strategy_cost_ratio_pct.median
