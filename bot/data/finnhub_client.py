"""Finnhub istemcisi — Alpha Vantage'dan bağımsız, ÜCRETSİZ çapraz doğrulama.

/news-sentiment uç noktası, sembol için son bir haftalık haber akışından
türetilmiş boğa/ayı yüzdelerini döndürür. Alpha Vantage'ın kendi taradığı
haber kümesinden farklı bir kaynak olduğu için iki bağımsız görüş sağlar.

Not: Finnhub ücretsiz plana dahil olmayabilecek uç noktaları 401/403 ile
reddeder. Bu istemci böyle bir yanıtı hata olarak fırlatır; motor bunu
diğer sağlayıcılar gibi zarifçe yakalayıp atlar (bkz. engine._get_fundamental_data).
"""
from __future__ import annotations

import logging

import requests

from ..config import Secrets
from . import cache

log = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1/news-sentiment"
DEFAULT_TTL = 12 * 3600  # AV ile tutarlı: temel veriler yarım gün cache'lenir


class FinnhubError(RuntimeError):
    """API hatası, yetki reddi veya beklenmeyen yanıt yapısı."""


class FinnhubClient:
    def __init__(self, secrets: Secrets, *, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._api_key = secrets.finnhub_api_key
        self._ttl = ttl_seconds
        self._session = requests.Session()

    def get_news_sentiment(self, symbol: str) -> dict:
        """Ham /news-sentiment yanıtını döndür (cache'li)."""
        cache_key = f"finnhub:news-sentiment:{symbol}"
        cached = cache.get_cached(cache_key, self._ttl)
        if cached is not None:
            log.debug("Finnhub cache hit: %s", symbol)
            return cached

        resp = self._session.get(
            BASE_URL, params={"symbol": symbol, "token": self._api_key}, timeout=30
        )
        if resp.status_code in (401, 403):
            raise FinnhubError(
                f"Yetki reddedildi ({resp.status_code}) — bu uç nokta ücretsiz "
                f"plana dahil olmayabilir."
            )
        if resp.status_code == 429:
            raise FinnhubError("Rate limit aşıldı (60 istek/dk).")
        resp.raise_for_status()
        data = resp.json()

        cache.set_cached(cache_key, data)
        return data
