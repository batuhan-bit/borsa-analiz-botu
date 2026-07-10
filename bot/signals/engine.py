"""Sinyal motoru — teknik ve temel skorları birleştirip Signal üretir.

Nihai skor = (1 - w) * teknik + w * temel   (w = fundamental.weight)
Skora ve eşiklere göre BUY / SELL / HOLD kararı verilir.
"""
from __future__ import annotations

from ..config import Settings
from ..models import Basket, Signal


class SignalEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # TODO(adım 2-3): veri istemcilerini ve skorlayıcıları bağla

    def evaluate_symbol(self, symbol: str, basket: Basket) -> Signal:
        """Tek bir sembol için sinyal üret."""
        raise NotImplementedError("Adım 3'te doldurulacak")

    def run(self) -> list[Signal]:
        """Tüm sepetlerdeki evreni tara ve sinyal listesi döndür."""
        raise NotImplementedError("Adım 3'te doldurulacak")
