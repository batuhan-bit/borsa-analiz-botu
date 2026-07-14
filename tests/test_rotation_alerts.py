"""Kural-bazlı satış uyarıları (Görev A.3) birim testleri.

Üç tetik ayrı ayrı; aynı pozisyon için aynı tetik günde bir kez (spam koruması).
"""
from __future__ import annotations

from datetime import date

from bot.config import Strategy
from bot.rotation import (
    SellAlertEngine,
    TriggerType,
    check_fundamental_red_flags,
    check_ranking_collapse,
    check_technical_emergency,
)

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
