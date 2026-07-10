"""Pozisyon bazlı risk yönetimi.

Kural: Herhangi bir tek pozisyon giriş fiyatına göre %20 kaybederse, o
pozisyon için STOP_LOSS (acil satış) sinyali üretilir.
Portföy seviyesinde ayrı bir durdurma eşiği YOKTUR.

Açık pozisyonlar Google Sheets loglama katmanından okunur (manuel işlem
modeli: kullanıcının alım kaydettiği pozisyonlar takip edilir).
"""
from __future__ import annotations

from ..models import Basket, Signal, SignalType


def check_stop_loss(
    symbol: str,
    basket: Basket,
    entry_price: float,
    current_price: float,
    stop_loss_pct: float,
) -> Signal | None:
    """Pozisyon stop-loss eşiğini aştıysa STOP_LOSS sinyali döndür, yoksa None.

    stop_loss_pct pozitif bir yüzde olarak verilir (ör. 20 = %20).
    """
    if not entry_price or entry_price <= 0:
        return None

    change_pct = (current_price - entry_price) / entry_price * 100.0
    if change_pct <= -abs(stop_loss_pct):
        return Signal(
            symbol=symbol,
            basket=basket,
            signal=SignalType.STOP_LOSS,
            score=1.0,  # stop-loss kesin bir kuraldır, tam güven
            price=current_price,
            reasons=[
                f"Pozisyon %{change_pct:.1f} zararda "
                f"(stop-loss eşiği -%{abs(stop_loss_pct):.0f}) — ACİL SATIŞ"
            ],
        )
    return None
