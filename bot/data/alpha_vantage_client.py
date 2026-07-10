"""Alpha Vantage istemcisi — temel analiz verisi.

Haberler & duygu (NEWS_SENTIMENT), kazanç takvimi (EARNINGS),
şirket genel bilgisi (OVERVIEW) uç noktaları için kullanılır.
Ücretsiz plan limiti: 25 istek/gün — çağrılar dikkatli yapılmalı.
"""
from __future__ import annotations

import requests

from ..config import Secrets

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageClient:
    def __init__(self, secrets: Secrets) -> None:
        self._api_key = secrets.alpha_vantage_api_key
        self._session = requests.Session()

    def _get(self, params: dict) -> dict:
        params = {**params, "apikey": self._api_key}
        resp = self._session.get(BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_news_sentiment(self, symbol: str) -> dict:
        """Sembol için haber duygu skorlarını döndür."""
        raise NotImplementedError("Adım 2'de doldurulacak")

    def get_earnings(self, symbol: str) -> dict:
        """Geçmiş ve yaklaşan kazanç raporu bilgisini döndür."""
        raise NotImplementedError("Adım 2'de doldurulacak")

    def get_overview(self, symbol: str) -> dict:
        """Şirket genel bilgisi (piyasa değeri, analist hedefi vb.)."""
        raise NotImplementedError("Adım 2'de doldurulacak")
