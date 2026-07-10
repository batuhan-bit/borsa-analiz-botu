"""yfinance istemcisi — Alpaca'yı tamamlayıcı/yedek fiyat verisi.

Uzun geçmiş (backtest için 3 yıl), piyasa değeri, beta gibi alanlar için
kullanışlıdır.
"""
from __future__ import annotations

import pandas as pd


class YFinanceClient:
    def get_daily_bars(self, symbol: str, *, years: float = 3.0) -> pd.DataFrame:
        """Sembol için günlük OHLCV geçmişini döndür (backtest'e uygun uzunluk)."""
        raise NotImplementedError("Adım 2'de doldurulacak")

    def get_fundamentals(self, symbol: str) -> dict:
        """Piyasa değeri, beta, sektör vb. temel alanları döndür.

        Radar altı sepeti filtreleri (market cap 500M-5B) burada kullanılır.
        """
        raise NotImplementedError("Adım 2'de doldurulacak")
