"""Sizing v2 öneri yardımcısı testleri (bot/signals/sizing.py) — ağ yok."""
from __future__ import annotations

import pytest

from bot.signals.sizing import portfolio_equity, suggested_position, target_weight


def test_target_weight_basic():
    # düşük vol: %40 / 2 pozisyon = %20
    assert target_weight(40, 2) == pytest.approx(0.20)
    assert target_weight(25, 2) == pytest.approx(0.125)
    assert target_weight(40, 0) == 0.0   # sıfıra bölme koruması


def test_suggested_position_whole_shares():
    # özsermaye 5000, %20 hedef = 1000; fiyat 100 -> 10 adet, 1000$
    s = suggested_position(5000, 100.0, 40, 2, {"fractional_shares": False})
    assert s["weight_pct"] == pytest.approx(20.0)
    assert s["amount"] == pytest.approx(1000.0)
    assert s["shares"] == 10          # tam adet (floor)
    assert s["cost"] == pytest.approx(1000.0)
    assert s["affordable"] is True
    assert s["fractional"] is False


def test_suggested_position_floor_leaves_remainder():
    # 1000$ hedef, fiyat 300 -> floor(3.33)=3 adet, 900$ (kalan nakit hedefin altında)
    s = suggested_position(5000, 300.0, 40, 2, {"fractional_shares": False})
    assert s["shares"] == 3
    assert s["cost"] == pytest.approx(900.0)


def test_suggested_position_fractional():
    s = suggested_position(5000, 300.0, 40, 2, {"fractional_shares": True})
    assert s["fractional"] is True
    assert s["shares"] == pytest.approx(1000.0 / 300.0, abs=1e-3)


def test_suggested_position_not_affordable_whole_shares():
    # hedef 1000$, fiyat 1500 -> floor(0.66)=0 adet -> affordable False
    s = suggested_position(5000, 1500.0, 40, 2, {"fractional_shares": False})
    assert s["shares"] == 0
    assert s["affordable"] is False


def test_suggested_position_guards():
    assert suggested_position(0, 100, 40, 2, {}) is None       # özsermaye yok
    assert suggested_position(5000, 0, 40, 2, {}) is None      # fiyat yok
    assert suggested_position(5000, 100, 40, 0, {}) is None    # pozisyon sayısı 0


def test_portfolio_equity_anchor():
    # pozisyon yok -> özsermaye = budget_max
    assert portfolio_equity(0.0, 0.0, 5000) == pytest.approx(5000.0)
    # 2000$ maliyetle alınmış, şu an 3000$ değerinde -> 3000 + (5000-2000)=6000
    assert portfolio_equity(3000.0, 2000.0, 5000) == pytest.approx(6000.0)
    # portföy çıpayı aştıysa (maliyet > budget) nakit 0, sadece holdings
    assert portfolio_equity(8000.0, 6000.0, 5000) == pytest.approx(8000.0)
