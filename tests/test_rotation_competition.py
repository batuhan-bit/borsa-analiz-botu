"""Konfig yarışması (Görev B.3) birim testleri — ağ/anahtar gerektirmez.

Izgara üretimi, ızgara noktası uygulaması, aday seçimi ve dönem-ayrımı
akışının saf parçalarını sentetik barlarla doğrular.
"""
from __future__ import annotations

from bot.config import Strategy
from backtest.competition import (
    GridPoint,
    build_grid,
    run_config_ensemble,
    select_candidates,
)
from backtest.ensemble import EnsembleStats, EnsembleReport
from tests.test_rotation_backtest import _strategy, _universe_bars


def _base_strategy() -> Strategy:
    """Küçük ızgara + hızlı topluluk ile tam yarışma stratejisi."""
    strat = _strategy()
    rb = strat.raw.setdefault("rotation_backtest", {})
    rb.setdefault("windows", {})["tune"] = {"start": "2020-01-15", "end": "2020-08-01"}
    rb["ensemble"] = {"runs": 6, "start_jitter_days": 3, "slippage_jitter_pct": 50,
                      "band_low_pct": 10, "band_high_pct": 90, "health_band_pct": 30, "seed": 3}
    rb["competition"] = {
        "grid": {"score": ["s2_momentum"], "selection": ["per_basket", "global_top_n"],
                 "top_n": [6], "frequency": ["monthly"], "regime": [False, True]},
        "max_candidates": 2,
    }
    return strat


def test_build_grid_cartesian_product():
    strat = Strategy.load()   # varsayılan tam ızgara: 2·2·2·2·2 = 32
    points = build_grid(strat)
    assert len(points) == 32
    labels = {p.label for p in points}
    assert len(labels) == 32   # hepsi benzersiz


def test_grid_point_apply_is_isolated():
    """apply base'i değiştirmemeli; yeni Strategy doğru ayarları taşımalı."""
    base = Strategy.load()
    original_score = base.rotation.get("score")
    p = GridPoint("s2_momentum", "global_top_n", 8, "biweekly", True)
    derived = p.apply(base)
    assert derived.rotation["score"] == "s2_momentum"
    assert derived.rotation["selection"] == "global_top_n"
    assert derived.rotation["top_n"] == 8
    assert derived.rotation["frequency"] == "biweekly"
    assert derived.rotation_backtest["regime"]["enabled"] is True
    # base dokunulmadı
    assert base.rotation.get("score") == original_score
    assert base.rotation_backtest.get("regime", {}).get("enabled", False) is False


def test_select_candidates_ranks_by_median_then_band():
    def rep(median, width):
        # median ve band_width'i verecek örnekler kur
        lo = median - width / 2
        hi = median + width / 2
        return EnsembleReport("c", ("s", "e"), 3,
                              EnsembleStats("c", [lo, median, hi], 10, 90))
    a = (GridPoint("s1_technical", "per_basket", 6, "monthly", False), rep(10.0, 5.0))
    b = (GridPoint("s2_momentum", "per_basket", 6, "monthly", False), rep(20.0, 8.0))
    c = (GridPoint("s2_momentum", "global_top_n", 6, "monthly", False), rep(20.0, 2.0))
    chosen = select_candidates([a, b, c], max_candidates=2)
    # En yüksek medyan (20) iki tane; dar bant (c: 2.0) önce, sonra b (8.0)
    assert [p.label for p, _ in chosen] == [c[0].label, b[0].label]
    assert len(chosen) == 2


def test_max_candidates_caps_selection():
    # global_top_n'de top_n etkin bir parametredir -> her nokta ayrı aday sayılır
    reps = [(GridPoint("s2_momentum", "global_top_n", n, "monthly", False),
             EnsembleReport("c", ("s", "e"), 3, EnsembleStats("c", [float(n)], 10, 90)))
            for n in range(2, 10)]
    assert len(select_candidates(reps, max_candidates=2)) == 2


def test_select_candidates_dedupes_ineffective_top_n():
    """per_basket'te top_n etkisizdir: yalnız top_n farkıyla ayrışan noktalar

    aynı etkin konfigürasyon sayılır ve aday listesinde bir kez yer alır.
    """
    def rep(median):
        return EnsembleReport("c", ("s", "e"), 3, EnsembleStats("c", [median], 10, 90))
    a = (GridPoint("s2_momentum", "per_basket", 6, "monthly", False), rep(20.0))
    b = (GridPoint("s2_momentum", "per_basket", 8, "monthly", False), rep(20.0))   # aynı etkin config
    c = (GridPoint("s1_technical", "per_basket", 6, "monthly", False), rep(10.0))
    chosen = select_candidates([a, b, c], max_candidates=3)
    assert [p.label for p, _ in chosen] == [a[0].label, c[0].label]
    assert len(chosen) == 2


def test_run_config_ensemble_on_tune_window():
    """Uçtan uca: bir ızgara noktası tune penceresinde topluluk üretir."""
    base = _base_strategy()
    bars = _universe_bars()
    p = build_grid(base)[0]
    rep = run_config_ensemble(base, p, bars, "tune")
    assert rep.runs == 6
    assert rep.window == ("2020-01-15", "2020-08-01")
    assert len(rep.strategy_stats.samples) == 6
    assert len(rep.benchmarks) == 3
