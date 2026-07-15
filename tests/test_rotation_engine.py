"""Rotasyon çekirdeği (Görev A.1) birim testleri — ağ/anahtar gerektirmez.

Sabit (deterministik) bir sahte skorlayıcı ile motorun hedef portföy, fark ve
rebalans üretimini doğrular. Kabul kriteri: aynı girdi -> birebir aynı plan.
"""
from __future__ import annotations

from bot.config import Strategy
from bot.rotation import RotationEngine, size_positions


def _fixed_ranker(scores: dict[str, float]):
    """Sabit skor sözlüğünden rank_fn üret (bilinmeyen sembole 0.0)."""
    def rank_fn(symbols):
        return [(s, scores.get(s, 0.0)) for s in symbols]
    return rank_fn


def _strategy(**rotation_overrides) -> Strategy:
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {})
    strat.raw["rotation"].update(rotation_overrides)
    return strat


def test_per_basket_selects_two_per_basket_with_basket_weights():
    strat = _strategy(selection="per_basket")
    eng = RotationEngine(strat)
    # Her sembole eşit skor -> alfabetik ilk 2 (deterministik tie-break)
    plan = eng.build_plan(_fixed_ranker({}))

    # 3 sepet x 2 = 6 pozisyon
    assert len(plan.targets) == 6
    baskets = {}
    for t in plan.targets:
        baskets.setdefault(t.basket, []).append(t)
    assert set(baskets) == {"low_volatility", "high_volatility", "under_radar"}
    for t in plan.targets:
        assert len(baskets[t.basket]) == 2

    # Pozisyon ağırlığı = sepet ağırlığı / 2
    low = [t for t in plan.targets if t.basket == "low_volatility"][0]
    assert low.weight == 0.40 / 2
    high = [t for t in plan.targets if t.basket == "high_volatility"][0]
    assert high.weight == 0.35 / 2
    # Toplam ağırlık ~1.0
    assert abs(sum(t.weight for t in plan.targets) - 1.0) < 1e-9


def test_per_basket_picks_highest_scores():
    strat = _strategy(selection="per_basket")
    eng = RotationEngine(strat)
    # low_volatility evreninden iki sembolü öne çıkar
    scores = {"JNJ": 0.9, "PG": 0.8}
    plan = eng.build_plan(_fixed_ranker(scores))
    low = sorted([t for t in plan.targets if t.basket == "low_volatility"],
                 key=lambda t: t.rank)
    assert [t.symbol for t in low] == ["JNJ", "PG"]
    assert low[0].rank == 1 and low[1].rank == 2


def test_global_top_n_equal_weight_and_theme_cap():
    strat = _strategy(selection="global_top_n", top_n=6, max_positions_per_theme=2)
    eng = RotationEngine(strat)
    # semis_ai teması çok sayıda sembol içerir; tema kapısı en çok 2'ye indirmeli
    scores = {"NVDA": 0.99, "AMD": 0.98, "AVGO": 0.97, "MU": 0.96,  # hepsi semis_ai
              "MRNA": 0.95, "IONQ": 0.94, "RKLB": 0.93, "OKLO": 0.92}
    plan = eng.build_plan(_fixed_ranker(scores))
    assert len(plan.targets) == 6
    # Eşit ağırlık
    assert all(abs(t.weight - 1 / 6) < 1e-9 for t in plan.targets)
    # semis_ai teması en çok 2 pozisyon
    semis = [t for t in plan.targets if t.theme == "semis_ai"]
    assert len(semis) == 2
    assert {t.symbol for t in semis} == {"NVDA", "AMD"}   # en yüksek 2 semis_ai


def test_diff_entering_exiting_staying():
    strat = _strategy(selection="per_basket")
    eng = RotationEngine(strat)
    scores = {"JNJ": 0.9, "PG": 0.8}
    # Mevcut portföyde JNJ (kalır) ve XLU (hedefte yok -> çıkar) olsun
    plan = eng.build_plan(_fixed_ranker(scores), current={"JNJ": 0.20, "XLU": 0.20})
    assert "JNJ" in plan.staying
    assert "XLU" in plan.exiting
    assert "PG" in plan.entering


def test_rebalance_band_triggers_on_drift():
    strat = _strategy(selection="per_basket", rebalance_band_pct=20)
    eng = RotationEngine(strat)
    scores = {"JNJ": 0.9}
    # JNJ hedef ağırlığı 0.20; mevcut 0.10 -> %50 sapma (>%20) -> "ekle"
    plan = eng.build_plan(_fixed_ranker(scores), current={"JNJ": 0.10})
    jnj_actions = [a for a in plan.rebalance if a.symbol == "JNJ"]
    assert len(jnj_actions) == 1
    assert jnj_actions[0].action == "ekle"
    assert jnj_actions[0].drift_pct == 50.0


def test_rebalance_band_ignores_small_drift():
    strat = _strategy(selection="per_basket", rebalance_band_pct=20)
    eng = RotationEngine(strat)
    scores = {"JNJ": 0.9}
    # Mevcut 0.19, hedef 0.20 -> %5 sapma (<%20) -> öneri yok
    plan = eng.build_plan(_fixed_ranker(scores), current={"JNJ": 0.19})
    assert [a for a in plan.rebalance if a.symbol == "JNJ"] == []


def test_determinism_same_input_same_plan():
    """Kabul kriteri: aynı tarih ve veriyle iki koşu birebir aynı plan."""
    strat = _strategy(selection="per_basket")
    eng = RotationEngine(strat)
    scores = {"NVDA": 0.7, "AMD": 0.6, "JNJ": 0.9, "PG": 0.8, "IONQ": 0.5, "RKLB": 0.4}
    ranker = _fixed_ranker(scores)
    p1 = eng.build_plan(ranker, current={"JNJ": 0.2})
    p2 = eng.build_plan(ranker, current={"JNJ": 0.2})
    assert p1 == p2
    assert p1.target_symbols == p2.target_symbols


def test_sizing_reused_for_weights():
    """Sizing v2 modülü ağırlıkları tutar/adete çevirir (tam sayı ve kesirli)."""
    strat = _strategy(selection="per_basket")
    eng = RotationEngine(strat)
    plan = eng.build_plan(_fixed_ranker({"JNJ": 0.9}))
    prices = {t.symbol: 100.0 for t in plan.targets}

    sized = eng.size(plan, capital=1000.0, prices=prices)
    # JNJ ağırlığı 0.20 -> 200 USD / 100 = 2 adet
    jnj = [s for s in sized if s.symbol == "JNJ"][0]
    assert jnj.target_value == 200.0
    assert jnj.shares == 2.0

    # Kesirli mod: 175 USD hedef, fiyat 100 -> 1.75 adet
    sized_frac = size_positions(
        [type("T", (), {"symbol": "X", "weight": 0.175})()],
        capital=1000.0, prices={"X": 100.0}, fractional=True,
    )
    assert sized_frac[0].shares == 1.75
