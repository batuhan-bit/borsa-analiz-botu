"""Kural-bazlı satış uyarıları (Görev A.3) birim testleri.

Üç tetik ayrı ayrı; aynı pozisyon için aynı tetik günde bir kez (spam koruması).
"""
from __future__ import annotations

from datetime import date

from bot.config import Strategy
from bot.rotation import (
    AlertCooldown,
    RankingCollapseTracker,
    SellAlertEngine,
    TriggerType,
    check_fundamental_red_flags,
    check_ranking_collapse,
    check_technical_emergency,
    collapse_cutoff,
    collapse_rank_map,
)


def _strat(**rotation_overrides) -> Strategy:
    s = Strategy.load()
    s.raw.setdefault("rotation", {}).update(rotation_overrides)
    return s


def _strat_with_multiple(multiple: int, **rotation_overrides) -> Strategy:
    """_strat + ranking_collapse_multiple override — mekanizma testleri config'in
    kalibre edilmiş varsayılanından (strategy.yaml) bağımsız olsun diye izole eder."""
    s = _strat(**rotation_overrides)
    s.raw.setdefault("sell_alerts", {})["ranking_collapse_multiple"] = multiple
    return s


def _ranking(symbols: list[str]):
    """Sıralı sembol listesini azalan skorlu (symbol, skor) listesine çevir."""
    return [(s, 1.0 - i * 0.001) for i, s in enumerate(symbols)]

FUND_CFG = {
    "earnings_surprise_min_pct": -15,
    "revenue_growth_max": 0.0,
    "insider_sell_ratio_min": 3.0,
    "insider_sell_min_count": 3,
    "news_negative_max": -0.30,
}


# ---------------- 1) Teknik acil durum ----------------

def test_technical_emergency_triggers_below_atr_threshold():
    # Giriş 100, ATR 5, çarpan 3 -> eşik 85. Fiyat 84 -> tetik.
    t = check_technical_emergency(100.0, 84.0, 5.0, multiple=3.0)
    assert t is not None and t.type is TriggerType.TECHNICAL


def test_technical_emergency_silent_above_threshold():
    # Fiyat 90 > eşik 85 -> tetik yok
    assert check_technical_emergency(100.0, 90.0, 5.0, multiple=3.0) is None


def test_technical_emergency_needs_valid_inputs():
    assert check_technical_emergency(0.0, 50.0, 5.0, multiple=3.0) is None   # giriş yok
    assert check_technical_emergency(100.0, 50.0, 0.0, multiple=3.0) is None  # ATR yok


# ---------------- 2) Sıralama çöküşü ----------------

def test_ranking_collapse_triggers_outside_cutoff():
    # top_n=6, çarpan 2 -> eşik 12. Sıra 13 -> tetik.
    t = check_ranking_collapse(13, top_n=6, multiple=2)
    assert t is not None and t.type is TriggerType.RANKING


def test_ranking_collapse_silent_inside_cutoff():
    assert check_ranking_collapse(12, top_n=6, multiple=2) is None   # sınırda, hâlâ içeride
    assert check_ranking_collapse(3, top_n=6, multiple=2) is None


def test_ranking_collapse_none_when_rank_unknown():
    assert check_ranking_collapse(None, top_n=6, multiple=2) is None


# ---------------- 3) Temel kırmızı bayrak ----------------

def test_fundamental_earnings_collapse():
    flags = check_fundamental_red_flags({"earnings_surprise_pct": -30}, FUND_CFG)
    assert any("Kazanç sürprizi" in f.reason for f in flags)
    assert all(f.type is TriggerType.FUNDAMENTAL for f in flags)


def test_fundamental_loss_plus_contraction_together():
    # Zarar (marj<0) VE gelir daralması (büyüme<0) birlikte -> tetik
    flags = check_fundamental_red_flags(
        {"profit_margin": -0.1, "revenue_growth_yoy": -0.05}, FUND_CFG)
    assert any("birlikte" in f.reason for f in flags)
    # Yalnız zarar ama gelir büyüyorsa tetik YOK
    flags2 = check_fundamental_red_flags(
        {"profit_margin": -0.1, "revenue_growth_yoy": 0.20}, FUND_CFG)
    assert not any("birlikte" in f.reason for f in flags2)


def test_fundamental_heavy_insider_selling_asymmetric():
    # 6 satış, 1 alım -> 6 >= 3*1 -> tetik
    flags = check_fundamental_red_flags({"insider_sells": 6, "insider_buys": 1}, FUND_CFG)
    assert any("içeriden satış" in f.reason for f in flags)
    # 4 satış, 3 alım -> 4 < 3*3 -> tetik yok (asimetri: alımlar dengeler)
    flags2 = check_fundamental_red_flags({"insider_sells": 4, "insider_buys": 3}, FUND_CFG)
    assert not any("içeriden satış" in f.reason for f in flags2)


def test_fundamental_two_negative_news_sources():
    # AV -0.2 (/0.35 -> -0.57) ve web -0.5, ikisi de <= -0.30 -> tetik
    flags = check_fundamental_red_flags(
        {"news_sentiment_score": -0.2, "web_sentiment_score": -0.5}, FUND_CFG)
    assert any("belirgin negatif" in f.reason for f in flags)
    # Yalnız biri negatifse tetik yok
    flags2 = check_fundamental_red_flags(
        {"news_sentiment_score": -0.2, "web_sentiment_score": 0.4}, FUND_CFG)
    assert not any("belirgin negatif" in f.reason for f in flags2)


def test_fundamental_empty_data_no_flags():
    assert check_fundamental_red_flags({}, FUND_CFG) == []


# ---------------- Spam koruması (engine) ----------------

def _engine() -> SellAlertEngine:
    return SellAlertEngine(Strategy.load())


def test_engine_aggregates_multiple_triggers():
    eng = _engine()
    alert = eng.evaluate(
        "NVDA", entry_price=100.0, current_price=80.0, atr=5.0, rank_now=20,
        fundamental={"earnings_surprise_pct": -40}, day=date(2026, 7, 14),
    )
    assert alert is not None
    types = {t.type for t in alert.triggers}
    assert TriggerType.TECHNICAL in types
    assert TriggerType.RANKING in types
    assert TriggerType.FUNDAMENTAL in types
    assert alert.current_rank == 20


def test_engine_same_trigger_reported_once_per_day():
    eng = _engine()
    kwargs = dict(entry_price=100.0, current_price=80.0, atr=5.0, rank_now=3,
                  day=date(2026, 7, 14))
    first = eng.evaluate("NVDA", **kwargs)
    assert first is not None and first.triggers[0].type is TriggerType.TECHNICAL
    # Aynı gün ikinci kez -> aynı tetik bastırılır -> None
    second = eng.evaluate("NVDA", **kwargs)
    assert second is None


def test_engine_new_day_resets_via_new_engine():
    """Ertesi gün (yeni ledger) aynı tetik yeniden bildirilebilir."""
    kwargs = dict(entry_price=100.0, current_price=80.0, atr=5.0, rank_now=3)
    e1 = _engine()
    assert e1.evaluate("NVDA", day=date(2026, 7, 14), **kwargs) is not None
    e2 = _engine()
    assert e2.evaluate("NVDA", day=date(2026, 7, 15), **kwargs) is not None


# ================= (1) TABAN HİZALAMA =================

def test_collapse_cutoff_per_basket_uses_positions_per_basket():
    # multiple mekanizma testi -- config'in kalibre edilmiş varsayılanından
    # (strategy.yaml: 3, bkz. results/diag_sensitivity_sweep.md) bağımsız olsun
    # diye açıkça 2 verilir.
    s = _strat_with_multiple(2, selection="per_basket")
    # ranking_collapse_multiple=2 × positions_per_basket=2 -> 4
    assert collapse_cutoff(s) == 2 * int(s.portfolio["positions_per_basket"])


def test_collapse_cutoff_global_uses_top_n():
    s = _strat_with_multiple(2, selection="global_top_n", top_n=6)
    assert collapse_cutoff(s) == 12   # 2×top_n (klasik küresel davranış korunur)


def test_collapse_rank_map_per_basket_is_within_basket():
    """per_basket: sıra SEPET-İÇİ; global_top_n: KÜRESEL. Taban farkını gösterir."""
    s = _strat(selection="per_basket")
    lv = [x for x in s.universe_symbols if s.basket_of(x) == "low_volatility"][:3]
    ur = [x for x in s.universe_symbols if s.basket_of(x) == "under_radar"][:2]
    # Küresel sıra: 3 low_vol önce, sonra under_radar -> ur[0] küresel #4, sepet-içi #1
    ranking = _ranking(lv + ur)
    rmap = collapse_rank_map(s, ranking)
    assert rmap[ur[0]] == 1 and rmap[ur[1]] == 2   # sepet-içi
    assert rmap[lv[2]] == 3                          # low_vol sepet-içi
    # Küresel tabanda ur[0] #4 olurdu — hizalama olmasaydı yanlış çöküş kaynağı
    gmap = collapse_rank_map(_strat(selection="global_top_n", top_n=6), ranking)
    assert gmap[ur[0]] == 4


# ================= (2) KALICILIK ŞARTI =================

def test_ranking_collapse_requires_persist_days():
    """Çöküş eşiği ancak art arda N işlem günü aşılırsa tetiklenir."""
    s = _strat_with_multiple(2, selection="per_basket")  # cutoff 4 (mekanizma testi)
    ur = [x for x in s.universe_symbols if s.basket_of(x) == "under_radar"][:6]
    ranking = _ranking(ur)                       # ur[5] sepet-içi #6 (>4)
    tr = RankingCollapseTracker(s, persist_days=3)
    held = [ur[0], ur[5]]
    assert tr.update(ranking, held) == set()     # 1. gün — henüz değil
    assert tr.update(ranking, held) == set()     # 2. gün
    assert tr.update(ranking, held) == {ur[5]}   # 3. gün — çöküş
    # ur[0] sepet-içi #1: hiçbir gün çökmez (taban hizalama)
    assert ur[0] not in tr.update(ranking, held)


def test_persistence_resets_on_one_day_recovery():
    """Tek günlük toparlanma seriyi sıfırlar — gürültü birikmez."""
    s = _strat_with_multiple(2, selection="per_basket")  # cutoff 4 (mekanizma testi)
    ur = [x for x in s.universe_symbols if s.basket_of(x) == "under_radar"][:6]
    bad = _ranking(ur)                           # ur[5] #6 (>4)
    good = _ranking([ur[5]] + ur[:5])            # ur[5] sepet-içi #1 (<=4)
    tr = RankingCollapseTracker(s, persist_days=3)
    held = [ur[0], ur[5]]
    tr.update(bad, held)
    tr.update(bad, held)                          # seri 2
    tr.update(good, held)                         # toparlanma -> sıfırla
    assert tr.update(bad, held) == set()          # seri 1, henüz çökmedi


def test_dropped_symbol_streak_resets_on_reentry():
    """Portföyden çıkan sembol yeniden girince sayaç sıfırdan başlar."""
    s = _strat_with_multiple(2, selection="per_basket")  # cutoff 4 (mekanizma testi)
    ur = [x for x in s.universe_symbols if s.basket_of(x) == "under_radar"][:6]
    ranking = _ranking(ur)
    tr = RankingCollapseTracker(s, persist_days=3)
    tr.update(ranking, [ur[0], ur[5]])            # ur[5] seri 1
    tr.update(ranking, [ur[0]])                   # ur[5] portföyde değil -> düşürülür
    # Yeniden giriş: seri sıfırdan; iki gün daha çökmez
    assert tr.update(ranking, [ur[0], ur[5]]) == set()
    assert tr.update(ranking, [ur[0], ur[5]]) == set()


def test_technical_emergency_exempt_from_persistence():
    """Teknik acil tetik kalıcılık şartından MUAF — ilk çağrıda tetikler."""
    # Saf/durumsuz: persist_days beklemeden, tek günde tetiklenir.
    t = check_technical_emergency(100.0, 84.0, 5.0, multiple=3.0)
    assert t is not None and t.type is TriggerType.TECHNICAL


# ================= (3) YENİDEN-GİRİŞ BEKLEME SÜRESİ =================

def test_alert_cooldown_blocks_for_n_trading_days():
    s = _strat()
    s.raw.setdefault("sell_alerts", {})["slot_refill_cooldown_days"] = 5
    cd = AlertCooldown(s)
    cd.register("POWL", 10)
    assert cd.is_blocked("POWL", 10)         # kapanış günü
    assert cd.is_blocked("POWL", 14)         # 5 işlem günü boyunca (10..14)
    assert not cd.is_blocked("POWL", 15)     # serbest
    assert "POWL" in cd.blocked(12)
    assert "POWL" not in cd.blocked(15)
    assert not cd.is_blocked("OTHER", 10)    # kayıtsız sembol hiç engellenmez
