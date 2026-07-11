"""Perplexity istemcisi — bağımsız web araması ile temel analiz çapraz doğrulaması.

Alpha Vantage'ın kendi taradığı haber kümesinden farklı, canlı bir web
araması yapar. Amaç tek bir kaynağa bağımlı kalmamak: iki bağımsız kaynak
aynı yöne işaret ediyorsa güven artar, ters düşüyorsa sinyalde uyarı gösterilir
(bkz. bot.signals.fundamental.check_source_agreement).

Perplexity serbest metin döndüren bir sohbet modelidir; sayısal skor almak
için promptta kesin bir çıktı formatı isteniyor ve yanıt regex ile parse
ediliyor. Format uyulmazsa None döner (skor yok sayılır, çökmez).

Ücretsiz plan yoktur — her çağrı ücretlidir, bu yüzden motor bunu da Alpha
Vantage gibi yalnızca teknik olarak güçlü adaylara uygular.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

from ..config import Secrets
from . import cache

log = logging.getLogger(__name__)

API_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MODEL = "sonar"
DEFAULT_TTL = 12 * 3600  # AV ile tutarlı: temel veriler yarım gün cache'lenir

_SCORE_RE = re.compile(r"SKOR\s*:\s*(-?\d+(?:\.\d+)?)", re.IGNORECASE)

_PROMPT_TEMPLATE = """\
{symbol} hissesi için son birkaç gündeki güncel haberleri, analist \
yorumlarını ve piyasa duyarlılığını araştır.

Yanıtını KESİNLİKLE şu iki satır formatında ver, başka hiçbir şey ekleme:
SKOR: <-1.0 ile +1.0 arası bir sayı, negatif=olumsuz, pozitif=olumlu, 0=nötr>
ÖZET: <tek cümlelik Türkçe gerekçe>
"""


class PerplexityError(RuntimeError):
    """API hatası veya beklenmeyen yanıt formatı."""


class PerplexityClient:
    def __init__(self, secrets: Secrets, *, ttl_seconds: float = DEFAULT_TTL) -> None:
        self._api_key = secrets.perplexity_api_key
        self._ttl = ttl_seconds
        self._session = requests.Session()

    def _ask(self, symbol: str) -> str:
        cache_key = f"pplx:{symbol}"
        cached = cache.get_cached(cache_key, self._ttl)
        if cached is not None:
            log.debug("Perplexity cache hit: %s", symbol)
            return cached

        payload = {
            "model": DEFAULT_MODEL,
            "messages": [{"role": "user", "content": _PROMPT_TEMPLATE.format(symbol=symbol)}],
            "temperature": 0.1,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        resp = self._session.post(API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 429:
            raise PerplexityError("Rate limit / kota aşıldı")
        resp.raise_for_status()
        data = resp.json()

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PerplexityError(f"Beklenmeyen yanıt yapısı: {exc}") from exc

        cache.set_cached(cache_key, text)
        return text

    def get_web_sentiment(self, symbol: str) -> dict:
        """Sembol için web tabanlı duygu skoru ve özet döndür.

        Döner: {"score": float|None, "summary": str|None, "raw": str}
        Format uyuşmazsa score/summary None olur ama istisna fırlatmaz.
        """
        text = self._ask(symbol)
        match = _SCORE_RE.search(text)
        score: Optional[float] = None
        if match:
            try:
                score = max(-1.0, min(1.0, float(match.group(1))))
            except ValueError:
                score = None

        summary_line = next((l for l in text.splitlines() if l.strip().upper().startswith("ÖZET")), "")
        summary = summary_line.split(":", 1)[1].strip() if ":" in summary_line else None

        if score is None:
            log.warning("Perplexity yanıtı beklenen formatta değil (%s): %r", symbol, text[:150])

        return {"score": score, "summary": summary, "raw": text}
