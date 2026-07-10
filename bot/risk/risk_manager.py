"""Pozisyon bazlı risk yönetimi.

Kural: Herhangi bir tek pozisyon giriş fiyatına göre %20 kaybederse, o
pozisyon için STOP_LOSS (acil satış) sinyali üretilir.
Portföy seviyesinde ayrı bir durdurma eşiği YOKTUR.

Açık pozisyonlar Google Sheets loglama katmanından okunur (manuel işlem
modeli: kullanıcının alım kaydettiği pozisyonlar takip edilir).
"""
from __future__ import annotations

from ..models import Signal


def check_stop_loss(
    symbol: str,
    entry_price: float,
    current_price: float,
    stop_loss_pct: float,
) -> Signal | None:
    """Pozisyon stop-loss eşiğini aştıysa STOP_LOSS sinyali döndür, yoksa None."""
    raise NotImplementedError("Adım 3'te doldurulacak")
