"""Pozisyon boyutu önerisi (canlı yol) — Sizing v2 kuralıyla.

Backtest'teki v2 boyutlandırmayla (Görev 2.2) TUTARLI bir "önerilen tutar/adet"
üretir: her pozisyonun hedef ağırlığı = sepet dağılımı / sepetteki pozisyon sayısı,
önerilen tutar = hedef ağırlık × portföy özsermayesi. Kesirli hisse config'ine
(`portfolio.sizing.fractional_shares`) saygılıdır.

Canlıda `execution: manual` olduğundan bu YALNIZCA bir öneridir; bot emir vermez.
Ağdan bağımsız, saf fonksiyon — kolay test edilir.
"""
from __future__ import annotations

import math
from typing import Any, Optional


def target_weight(allocation_pct: float, positions_per_basket: int) -> float:
    """Sepet başına tek pozisyonun hedef ağırlığı (0..1)."""
    if positions_per_basket <= 0:
        return 0.0
    return (float(allocation_pct) / 100.0) / positions_per_basket


def suggested_position(
    equity: Optional[float],
    price: Optional[float],
    allocation_pct: float,
    positions_per_basket: int,
    sizing_cfg: dict[str, Any] | None = None,
) -> Optional[dict]:
    """Bir BUY için önerilen dolar tutarı ve adet.

    equity: portföy özsermayesi (Sheets'ten türetilir). price: güncel fiyat.
    Dönüş: {weight_pct, amount, shares, cost, fractional, affordable} veya
    hesaplanamıyorsa None. `affordable=False` → tam adet modunda 1 hisse bile
    hedef tutarı aşıyor (fiyat, hedef ağırlıktan pahalı).
    """
    sizing_cfg = sizing_cfg or {}
    if not equity or equity <= 0 or not price or price <= 0 or positions_per_basket <= 0:
        return None

    weight = target_weight(allocation_pct, positions_per_basket)
    amount = weight * equity
    fractional = bool(sizing_cfg.get("fractional_shares", False))

    if fractional:
        raw_shares = amount / price
        shares: float = round(raw_shares, 4)
    else:
        shares = float(math.floor(amount / price))

    affordable = shares > 0
    cost = shares * price
    return {
        "weight_pct": round(weight * 100.0, 1),
        "amount": round(amount, 2),
        "shares": shares,
        "cost": round(cost, 2),
        "fractional": fractional,
        "affordable": affordable,
    }


def portfolio_equity(holdings_value: float, invested_cost: float, budget_max: float) -> float:
    """Sheets verisinden portföy özsermayesi tahmini.

    Sheets yalnız açık pozisyonların değerini bilir; serbest nakit ayrı
    tutulmaz. Toplam sermaye çıpası olarak config'teki `budget_max` alınır:
      özsermaye ≈ (güncel pozisyon değeri) + max(budget_max − yatırılan maliyet, 0)
    Pozisyon yokken özsermaye = budget_max; portföy büyürse (holdings > çıpa)
    büyümeyi yansıtır. Öneri bağlayıcı değil, bu yaklaşım kabul edilebilir.
    """
    cash_est = max(float(budget_max) - float(invested_cost), 0.0)
    return float(holdings_value) + cash_est
