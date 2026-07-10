"""Alpaca market data istemcisi (yalnızca veri; trading API DEĞİL).

Günlük OHLCV bar verisini çekmek için kullanılır. Gerçek implementasyon
2. geliştirme adımında doldurulacak.
"""
from __future__ import annotations

import pandas as pd

from ..config import Secrets


class AlpacaClient:
    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets
        # TODO(adım 2): alpaca-py StockHistoricalDataClient başlat

    def get_daily_bars(self, symbol: str, *, years: float = 1.0) -> pd.DataFrame:
        """Sembol için günlük OHLCV barlarını döndür.

        Dönen DataFrame kolonları: open, high, low, close, volume (tarih index).
        """
        raise NotImplementedError("Adım 2'de doldurulacak")
