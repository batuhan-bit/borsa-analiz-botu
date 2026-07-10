"""Alpha Vantage istemcisi — temel analiz verisi.

Uç noktalar: NEWS_SENTIMENT (haber & duygu), EARNINGS (kazanç takvimi/sürpriz),
OVERVIEW (şirket genel bilgisi: piyasa değeri, analist hedefi vb.).

Ücretsiz plan limiti 25 istek/gün olduğundan yanıtlar disk cache'te tutulur
(varsayılan TTL: 12 saat). Rate-limit yanıtları tespit edilip cache'lenmez.
"""
from __future__ import annotations

import logging

import requests

from ..config import Secrets
from . import cache

log = logging.getLogger(__name__)

BASE_URL = "https://www.alphavantage.co/query"
DEFAULT_TTL = 12 * 3600  # temel veriler yavaş değişir; yarım gün cache yeterli


class AlphaVantageError(RuntimeError):
    """API hata veya rate-limit yanıtı döndürdüğünde."""


class AlphaVantageClient:
    def __init__(self, secrets: Secrets, *, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._api_key = secrets.alpha_vantage_api_key
        self._ttl = ttl_seconds
        self._session = requests.Session()

    def _get(self, params: dict) -> dict:
        """Cache-öncelikli GET. Rate-limit/hata yanıtlarını tespit eder."""
        cache_key = "av:" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        cached = cache.get_cached(cache_key, self._ttl)
        if cached is not None:
            log.debug("Alpha Vantage cache hit: %s", params)
            return cached

        full = {**params, "apikey": self._api_key}
        resp = self._session.get(BASE_URL, params=full, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Alpha Vantage hata/limit yanıtlarını 200 ile döndürür; içeriğe bakılmalı
        if "Error Message" in data:
            raise AlphaVantageError(f"API hatası: {data['Error Message']}")
        if "Note" in data or "Information" in data:
            msg = data.get("Note") or data.get("Information")
            raise AlphaVantageError(f"Rate limit / bilgi yanıtı: {msg}")

        cache.set_cached(cache_key, data)
        return data

    def get_news_sentiment(self, symbol: str, *, limit: int = 50) -> dict:
        """Sembol için haber akışı ve duygu skorlarını döndür."""
        return self._get(
            {"function": "NEWS_SENTIMENT", "tickers": symbol, "limit": str(limit)}
        )

    def get_earnings(self, symbol: str) -> dict:
        """Geçmiş çeyreklik kazanç raporları ve sürprizleri döndür."""
        return self._get({"function": "EARNINGS", "symbol": symbol})

    def get_overview(self, symbol: str) -> dict:
        """Şirket genel bilgisi (piyasa değeri, analist hedefi, beta vb.)."""
        return self._get({"function": "OVERVIEW", "symbol": symbol})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    c = AlphaVantageClient(Secrets.load())
    print(c.get_overview("AAPL").get("Name"))
