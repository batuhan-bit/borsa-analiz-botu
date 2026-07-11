"""İskelet doğrulama testleri — strateji konfigürasyonu yükleniyor mu?"""
from __future__ import annotations

import pytest

from bot.config import Secrets, Strategy
from bot.models import Basket


# --- Sır (secret) zorunluluk kuralları ---
# Zorunlu tek şey Slack; Alpaca/AV/Sheets opsiyonel (zarif devre dışı).

def test_strict_requires_only_slack(monkeypatch):
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPHA_VANTAGE_API_KEY", "GOOGLE_SHEET_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.example/x")
    sec = Secrets.load(strict=True)          # Alpaca yokken de raise ETMEMELİ
    assert sec.slack_webhook_url
    assert sec.alpaca_api_key == ""          # Alpaca opsiyonel -> boş


def test_strict_missing_slack_raises(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(RuntimeError):
        Secrets.load(strict=True)


def test_strategy_loads():
    strat = Strategy.load()
    assert strat.portfolio["total_positions"] == 6
    assert strat.portfolio["target_return_pct"] == 6.5


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
