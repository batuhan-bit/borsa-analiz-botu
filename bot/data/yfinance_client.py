"""yfinance istemcisi — Alpaca'yı tamamlayıcı/yedek fiyat verisi.

Uzun geçmiş (backtest için ~3 yıl) ve piyasa değeri / beta / sektör gibi
temel alanlar için kullanılır. API anahtarı gerektirmez.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from .common import normalize_ohlcv

log = logging.getLogger(__name__)


class YFinanceClient:
    def get_daily_bars(self, symbol: str, *, years: float = 3.0) -> pd.DataFrame:
        """Sembol için günlük (temettü/split ayarlı) OHLCV geçmişini döndür."""
        import yfinance as yf

        end = date.today()
        start = end - timedelta(days=int(years * 365) + 5)

        try:
            ticker = yf.Ticker(symbol)
            raw = ticker.history(
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=True,   # ayarlı OHLC (backtest için)
                raise_errors=False,
            )
        except Exception as exc:
            log.warning("yfinance bar çekimi başarısız (%s): %s", symbol, exc)
            return pd.DataFrame()

        # yfinance kolonları: Open, High, Low, Close, Volume (+ Dividends, Stock Splits)
        return normalize_ohlcv(
            raw,
            rename={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            },
        )

    def get_fundamentals(self, symbol: str) -> dict:
        """Piyasa değeri, beta, sektör vb. temel alanları döndür.

        Radar altı sepeti filtreleri (market cap 500M-5B) ve düşük volatilite
        sepeti (max beta) burada kullanılır. Alan bulunamazsa None döner.
        """
        import yfinance as yf

        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            log.warning("yfinance fundamentals başarısız (%s): %s", symbol, exc)
            return {}

        return {
            "symbol": symbol,
            "market_cap": info.get("marketCap"),
            "beta": info.get("beta"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "name": info.get("shortName") or info.get("longName"),
            "avg_volume": info.get("averageVolume"),
            "trailing_pe": info.get("trailingPE"),
            "target_mean_price": info.get("targetMeanPrice"),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    c = YFinanceClient()
    print(c.get_daily_bars("AAPL", years=0.1).tail())
    print(c.get_fundamentals("AAPL"))
