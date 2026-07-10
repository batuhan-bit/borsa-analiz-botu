"""Alpaca market data istemcisi (yalnızca veri; trading API DEĞİL).

Günlük OHLCV bar verisini çeker. Ücretsiz plan IEX beslemesini kullanır.

Tasarım notu: Alpaca istemcisi TEMBEL kurulur. Anahtar yoksa veya kurulum
başarısız olursa istemci çökmez; get_daily_bars boş DataFrame döndürür ve
çağıran taraf (sinyal motoru) yfinance'e düşebilir.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from ..config import Secrets
from .common import normalize_ohlcv

log = logging.getLogger(__name__)


class AlpacaClient:
    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets
        self._client = None          # tembel kurulur
        self._init_failed = False    # tekrar tekrar denemeyi önle

    def _ensure_client(self):
        """Alpaca istemcisini gerektiğinde kur; başarısızsa None döndür."""
        if self._client is not None or self._init_failed:
            return self._client

        if not (self._secrets.alpaca_api_key and self._secrets.alpaca_secret_key):
            log.warning("Alpaca anahtarları eksik — yfinance'e düşülecek.")
            self._init_failed = True
            return None

        try:
            from alpaca.data.historical import StockHistoricalDataClient

            self._client = StockHistoricalDataClient(
                api_key=self._secrets.alpaca_api_key,
                secret_key=self._secrets.alpaca_secret_key,
            )
        except Exception as exc:
            log.warning("Alpaca istemcisi kurulamadı: %s", exc)
            self._init_failed = True
            return None
        return self._client

    def get_daily_bars(self, symbol: str, *, years: float = 1.0) -> pd.DataFrame:
        """Sembol için günlük (split/temettü ayarlı) OHLCV barlarını döndür.

        Dönen DataFrame: DatetimeIndex + [open, high, low, close, volume].
        Anahtar yoksa veya veri gelmezse boş DataFrame döner.
        """
        client = self._ensure_client()
        if client is None:
            return pd.DataFrame()

        from alpaca.data.enums import Adjustment
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=int(years * 365) + 5)

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment=Adjustment.ALL,  # split + temettü ayarlı
        )

        try:
            bars = client.get_stock_bars(request)
        except Exception as exc:  # ağ / yetki / geçersiz sembol
            log.warning("Alpaca bar çekimi başarısız (%s): %s", symbol, exc)
            return pd.DataFrame()

        df = bars.df
        if df is None or df.empty:
            log.info("Alpaca: %s için veri yok", symbol)
            return pd.DataFrame()

        # bars.df MultiIndex (symbol, timestamp) döndürür — sembol seviyesini düşür
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        # Alpaca kolonları zaten küçük harf: open, high, low, close, volume, ...
        return normalize_ohlcv(df)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    client = AlpacaClient(Secrets.load())
    print(client.get_daily_bars("AAPL", years=0.1).tail())
