"""Finnhub içeriden işlem (insider-transactions) istemcisi.

Uç nokta: /stock/insider-transactions?symbol=X
Dönen 'data' listesi: her kayıt {name, share, change, transactionDate,
transactionPrice, transactionCode, ...}. 'change' negatif = satış, pozitif = alım.

Not: Finnhub'ın bazı uç noktaları (ör. news-sentiment) ücretsiz planda 403
veriyordu; insider-transactions dokümana göre ücretsiz. Yine de 401/403'e
dayanıklıyız: hata durumunda motor bunu zarifçe atlar ve içeriden-satış
bileşeni skora katılmaz.
"""
from __future__ import annotations

import logging

import requests

from ..config import Secrets
from . import cache

log = logging.getLogger(__name__)

BASE_URL = "https://finnhub.io/api/v1/stock/insider-transactions"
DEFAULT_TTL = 24 * 3600  # içeriden işlemler seyrek; günde bir yeterli


class FinnhubInsiderError(RuntimeError):
    """API hatası, yetki reddi veya beklenmeyen yanıt."""


class FinnhubInsiderClient:
    def __init__(self, secrets: Secrets, *, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._api_key = secrets.finnhub_api_key
        self._ttl = ttl_seconds
        self._session = requests.Session()

    def get_insider_transactions(self, symbol: str) -> dict:
        """Ham insider-transactions yanıtını döndür (cache'li)."""
        cache_key = f"finnhub-insider:{symbol}"
        cached = cache.get_cached(cache_key, self._ttl)
        if cached is not None:
            return cached

        resp = self._session.get(
            BASE_URL, params={"symbol": symbol, "token": self._api_key}, timeout=30
        )
        if resp.status_code in (401, 403):
            raise FinnhubInsiderError(
                f"Yetki reddedildi ({resp.status_code}) — bu uç nokta ücretsiz "
                f"plana dahil olmayabilir."
            )
        if resp.status_code == 429:
            raise FinnhubInsiderError("Rate limit aşıldı (60 istek/dk).")
        resp.raise_for_status()
        data = resp.json()

        cache.set_cached(cache_key, data)
        return data
