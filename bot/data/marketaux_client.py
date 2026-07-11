"""Marketaux istemcisi — Alpha Vantage'dan bağımsız, ÜCRETSİZ çapraz doğrulama.

/news/all uç noktası, sembolü geçen haberleri "entities" listesiyle döndürür;
her entity zaten [-1, 1] aralığında bir sentiment_score taşır. Alpha Vantage'ın
kendi taradığı haber kümesinden farklı bir kaynak olduğu için iki bağımsız
görüş sağlar.

Ücretsiz plan: 100 istek/gün. Motor koşu başına yalnızca ~6 aday sembole
(en çok max_symbols_per_run) istek attığı için bu limit rahatça yeterlidir.
"""
from __future__ import annotations

import logging

import requests

from ..config import Secrets
from . import cache

log = logging.getLogger(__name__)

BASE_URL = "https://api.marketaux.com/v1/news/all"
DEFAULT_TTL = 12 * 3600  # AV ile tutarlı: temel veriler yarım gün cache'lenir


class MarketauxError(RuntimeError):
    """API hatası, yetki reddi veya rate-limit yanıtı."""


class MarketauxClient:
    def __init__(self, secrets: Secrets, *, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._api_key = secrets.marketaux_api_key
        self._ttl = ttl_seconds
        self._session = requests.Session()

    def get_news(self, symbol: str, *, limit: int = 10) -> dict:
        """Sembolü geçen son haberleri entity-bazlı sentiment ile döndür (cache'li)."""
        cache_key = f"marketaux:news:{symbol}"
        cached = cache.get_cached(cache_key, self._ttl)
        if cached is not None:
            log.debug("Marketaux cache hit: %s", symbol)
            return cached

        resp = self._session.get(
            BASE_URL,
            params={
                "symbols": symbol,
                "filter_entities": "true",
                "language": "en",
                "limit": limit,
                "api_token": self._api_key,
            },
            timeout=30,
        )
        if resp.status_code in (401, 403):
            raise MarketauxError(f"Yetki reddedildi ({resp.status_code}) — API anahtarını kontrol edin.")
        if resp.status_code == 429:
            raise MarketauxError("Rate limit aşıldı (100 istek/gün).")
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise MarketauxError(f"API hatası: {data['error']}")

        cache.set_cached(cache_key, data)
        return data
