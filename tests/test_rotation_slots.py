"""Slot doldurma + günlük gözlem (Görev A.4) birim testleri.

slot_candidates sepet/tema kısıtlarına saygı duymalı; günlük gözlem eylem dili
İÇERMEMELİ (kabul kriterleri).
"""
from __future__ import annotations

from bot.config import Strategy
from bot.rotation import (
    daily_observation,
    render_observation_lines,
    slot_candidates,
)
from bot.rotation.slots import has_action_language


def _strategy(**rotation_overrides) -> Strategy:
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {})
    strat.raw["rotation"].update(rotation_overrides)
    return strat


def _ranking(symbols_scores: list[tuple[str, float]]):
    """Zaten sıralı verilmiş (symbol, skor) listesi."""
    return symbols_scores


# ---------------- slot doldurma ----------------

def test_slot_candidate_per_basket_fills_empty_basket_slot():
    strat = _strategy(selection="per_basket")
    # low_volatility'de 1 pozisyon açık (JNJ); 1 slot boş.
    ranking = [("PG", 0.9), ("JNJ", 0.8), ("KO", 0.7), ("NVDA", 0.95)]
    cands = slot_candidates(strat, holdings=["JNJ"], ranking=ranking)
    low = [c for c in cands if c.basket == "low_volatility"]
    # En yüksek sıralı, portföy dışı low_volatility sembolü = PG
    assert low[0].symbol == "PG"
    # JNJ portföyde -> aday olarak önerilmez
    assert all(c.symbol != "JNJ" for c in cands)


def test_slot_candidate_respects_theme_cap():
    strat = _strategy(selection="global_top_n", top_n=6, max_positions_per_theme=2)
    # Portföyde 2 semis_ai (NVDA, AMD) -> tema dolu; sıradaki semis_ai aday olamaz.
    ranking = [("AVGO", 0.99), ("MRNA", 0.98), ("IONQ", 0.97)]  # AVGO=semis_ai
    cands = slot_candidates(strat, holdings=["NVDA", "AMD"], ranking=ranking)
    syms = [c.symbol for c in cands]
    assert "AVGO" not in syms                 # semis_ai teması dolu
    assert "MRNA" in syms and "IONQ" in syms  # farklı temalar uygun


def test_slot_candidate_none_when_portfolio_full():
    strat = _strategy(selection="global_top_n", top_n=2, max_positions_per_theme=2)
    ranking = [("PG", 0.9), ("KO", 0.8)]
    cands = slot_candidates(strat, holdings=["NVDA", "MRNA"], ranking=ranking)
    assert cands == []                        # 2/2 dolu, boş slot yok


def test_slot_candidate_per_basket_skips_full_basket():
    strat = _strategy(selection="per_basket")
    # high_volatility zaten 2 dolu -> o sepete aday önerilmez
    ranking = [("NVDA", 0.99), ("AMD", 0.98), ("PG", 0.9), ("KO", 0.85)]
    cands = slot_candidates(strat, holdings=["NVDA", "AMD"], ranking=ranking)
    assert all(c.basket != "high_volatility" for c in cands)
    # low_volatility'de 2 boş slot -> PG, KO önerilir
    low = [c.symbol for c in cands if c.basket == "low_volatility"]
    assert low[:2] == ["PG", "KO"]


# ---------------- günlük gözlem ----------------

def test_daily_observation_top_movers_outside_top_n():
    # Güncel sıra: AAA #8 (ilk-6 dışı), BBB #3 (ilk-6 içi), CCC #10
    rank_now = {"AAA": 8, "BBB": 3, "CCC": 10, "DDD": 12}
    # 5 gün önce: AAA #20 (çok yükseldi), CCC #11 (biraz), DDD #10 (düştü)
    rank_past = {"AAA": 20, "BBB": 5, "CCC": 11, "DDD": 10}
    obs = daily_observation(rank_now, rank_past, holdings=["BBB"], top_n=6, max_movers=3)
    movers = [m.symbol for m in obs.top_movers]
    assert "BBB" not in movers        # ilk-6 içi hariç
    assert "DDD" not in movers        # sırası düştü (improvement<=0)
    assert movers[0] == "AAA"         # en çok yükselen önce
    assert obs.portfolio_ranks == {"BBB": 3}


def test_observation_lines_have_no_action_language():
    """Kabul kriteri: gözlem bölümü eylem/imperatif dili içermez."""
    rank_now = {"AAA": 8, "JNJ": 3, "CCC": 10}
    rank_past = {"AAA": 20, "JNJ": 3, "CCC": 15}
    obs = daily_observation(rank_now, rank_past, holdings=["JNJ"], top_n=6)
    lines = render_observation_lines(obs)
    assert not has_action_language(lines)
    # Eylemsizlik ibaresi açıkça bulunmalı
    assert any("eylem önerisi değildir" in ln for ln in lines)


def test_observation_portfolio_rank_none_when_unranked():
    rank_now = {"AAA": 1}
    obs = daily_observation(rank_now, {}, holdings=["ZZZ"], top_n=6)
    assert obs.portfolio_ranks == {"ZZZ": None}
    lines = render_observation_lines(obs)
    assert any("ZZZ #—" in ln for ln in lines)
