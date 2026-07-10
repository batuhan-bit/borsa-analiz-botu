"""İskelet doğrulama testleri — strateji konfigürasyonu yükleniyor mu?"""
from __future__ import annotations

from bot.config import Strategy
from bot.models import Basket


def test_strategy_loads():
    strat = Strategy.load()
    assert strat.portfolio["total_positions"] == 6
    assert strat.portfolio["target_return_pct"] == 15


def test_basket_allocations_sum_to_100():
    strat = Strategy.load()
    total = sum(b["allocation_pct"] for b in strat.baskets.values())
    assert total == 100, f"Sepet dağılımı %100 olmalı, %{total} bulundu"


def test_all_baskets_present():
    strat = Strategy.load()
    for basket in Basket:
        assert basket.value in strat.baskets


def test_stop_loss_configured():
    strat = Strategy.load()
    assert strat.risk["position_stop_loss_pct"] == 20
    # Portföy seviyesinde durdurma olmamalı
    assert strat.risk["portfolio_stop_loss_pct"] is None
