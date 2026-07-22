"""Slot doldurma + günlük gözlem (Görev A.4) birim testleri.

slot_candidates sepet/tema kısıtlarına saygı duymalı; günlük gözlem eylem dili
İÇERMEMELİ (kabul kriterleri).
"""
from __future__ import annotations

from bot.config import Strategy
from bot.rotation import (
    basket_rank_map,
    daily_observation,
    render_observation_lines,
    slot_candidates,
)
from bot.rotation.alerts import collapse_cutoff, collapse_rank_map
from bot.rotation.slots import BasketRank, has_action_language


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


def test_slot_candidates_excludes_cooldown_symbols():
    """excluded (AlertCooldown bekleme) semboller aday olamaz — aç-kapa koruması."""
    strat = _strategy(selection="per_basket")
    # low_volatility'de JNJ açık, 1 slot boş. PG en yüksek aday ama cooldown'da.
    ranking = [("PG", 0.9), ("JNJ", 0.8), ("KO", 0.7)]
    cands = slot_candidates(strat, holdings=["JNJ"], ranking=ranking, excluded=["PG"])
    low = [c.symbol for c in cands if c.basket == "low_volatility"]
    assert "PG" not in low          # cooldown'da -> aday değil
    assert low[0] == "KO"           # sıradaki uygun aday gelir


def test_slot_candidates_same_base_as_collapse_per_basket():
    """Slot adayı seçimi ile çöküş testi AYNI tabanı (sepet-içi sıra) kullanır."""
    from bot.rotation.alerts import collapse_rank_map
    strat = _strategy(selection="per_basket")
    ur = [s for s in strat.universe_symbols if strat.basket_of(s) == "under_radar"][:3]
    lv = [s for s in strat.universe_symbols if strat.basket_of(s) == "low_volatility"][:1]
    # Küresel sıra: low_vol önce -> under_radar sembolleri küresel #2..#4, sepet-içi #1..#3
    ranking = [(lv[0], 0.95)] + [(u, 0.9 - i * 0.01) for i, u in enumerate(ur)]
    rmap = collapse_rank_map(strat, ranking)
    assert rmap[ur[0]] == 1                       # çöküş testi: sepet-içi #1
    cands = slot_candidates(strat, holdings=[lv[0]], ranking=ranking)
    ur_c = [c.symbol for c in cands if c.basket == "under_radar"]
    assert ur_c[0] == ur[0]                       # slot da sepet-içi #1'i önerir


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


# ---------------- sepet-içi sıra (gözlem) ----------------

def test_basket_rank_map_uses_collapse_base():
    """Sepet-içi sıra çöküş testiyle AYNI fonksiyondan gelir (tek doğruluk kaynağı)."""
    strat = _strategy(selection="per_basket")
    lv = [s for s in strat.universe_symbols if strat.basket_of(s) == "low_volatility"][:3]
    # Küresel sıralama: 3 low_vol sembolü sepet-içi #1..#3
    ranking = [(s, 0.9 - i * 0.01) for i, s in enumerate(lv)]
    rmap = collapse_rank_map(strat, ranking)
    bmap = basket_rank_map(strat, ranking, holdings=lv)
    for s in lv:
        assert bmap[s].rank == rmap[s]            # çöküş tabanıyla birebir
        assert bmap[s].basket == "low_volatility"
        assert bmap[s].size == 3                  # sepette 3 sembol görüldü


def test_basket_rank_map_flags_over_threshold():
    """Sepet-içi sıra çöküş eşiğinin (per_basket) dışındaysa over_threshold=True."""
    strat = _strategy(selection="per_basket")
    cutoff = collapse_cutoff(strat)               # varsayılan 2×2 = 4
    lv = [s for s in strat.universe_symbols if strat.basket_of(s) == "low_volatility"][:cutoff + 1]
    ranking = [(s, 0.9 - i * 0.01) for i, s in enumerate(lv)]
    bmap = basket_rank_map(strat, ranking, holdings=lv)
    assert bmap[lv[0]].over_threshold is False    # sepet-içi #1
    assert bmap[lv[cutoff]].over_threshold is True  # sepet-içi #(cutoff+1) -> eşik dışı


def test_render_observation_shows_basket_and_size():
    obs = daily_observation(
        {"MO": 17}, {}, holdings=["MO"], top_n=6,
        basket_ranks={"MO": BasketRank("low_volatility", 9, 20, over_threshold=True)},
    )
    lines = render_observation_lines(obs, basket_label=lambda b: "Düşük Vol")
    rank_line = next(ln for ln in lines if "Portföy sıraları" in ln)
    # Küresel sıra + sepet-içi sıra/boyut birlikte
    assert "MO #17 (Düşük Vol #9/20)" in rank_line
    # Eşik dışı -> hafif italik vurgu; sert uyarı işareti değil
    assert "_MO #17 (Düşük Vol #9/20)_" in rank_line
    assert not has_action_language(lines)


def test_render_observation_no_emphasis_within_threshold():
    obs = daily_observation(
        {"MU": 1}, {}, holdings=["MU"], top_n=6,
        basket_ranks={"MU": BasketRank("high_volatility", 1, 20, over_threshold=False)},
    )
    lines = render_observation_lines(obs, basket_label=lambda b: "Yüksek Vol")
    rank_line = next(ln for ln in lines if "Portföy sıraları" in ln)
    assert "MU #1 (Yüksek Vol #1/20)" in rank_line
    assert "_MU" not in rank_line                 # eşik içi -> vurgu yok
