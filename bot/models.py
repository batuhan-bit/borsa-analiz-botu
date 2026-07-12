"""Ortak veri modelleri — modüller arası paylaşılan tipler.

Sinyal motoru, bildirim ve loglama modülleri bu tipleri kullanarak
birbirleriyle konuşur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    STOP_LOSS = "STOP_LOSS"   # pozisyon bazlı %20 kuralı tetiklendi


class Basket(str, Enum):
    LOW_VOLATILITY = "low_volatility"
    HIGH_VOLATILITY = "high_volatility"
    UNDER_RADAR = "under_radar"


@dataclass
class Signal:
    """Bir sembol için üretilen tek bir sinyal."""

    symbol: str
    basket: Basket
    signal: SignalType
    # 0..1 arası güven skoru (teknik + temel bileşenlerin ağırlıklı toplamı)
    score: float
    price: float
    # İşaretli nihai skor [-1, 1] (pozitif=boğa). score = |raw_score|.
    # Aday seçimi ve hata ayıklama için tutulur.
    raw_score: float = 0.0
    reasons: list[str] = field(default_factory=list)   # insan-okur gerekçeler
    technical: dict[str, Any] = field(default_factory=dict)   # ham gösterge değerleri
    fundamental: dict[str, Any] = field(default_factory=dict)
    levels: dict[str, Any] = field(default_factory=dict)      # BUY için stop/destek/hedef
    notes: list[str] = field(default_factory=list)            # önemli uyarılar (ayrı iletilir)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> list[Any]:
        """Google Sheets satırına çevir."""
        return [
            self.generated_at.isoformat(),
            self.symbol,
            self.basket.value,
            self.signal.value,
            round(self.score, 3),
            round(self.price, 2),
            "; ".join(self.reasons),
        ]
