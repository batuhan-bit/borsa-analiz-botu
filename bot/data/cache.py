"""Basit disk tabanlı JSON cache.

Özellikle Alpha Vantage (ücretsiz plan: 25 istek/gün) için gereklidir;
aynı gün içinde tekrar eden isteklerin API kotasını tüketmesini önler.
Cache dosyaları data_cache/ altında tutulur (.gitignore'da).
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ..config import ROOT

CACHE_DIR = ROOT / "data_cache"


def _key_to_path(key: str) -> Path:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return CACHE_DIR / f"{digest}.json"


def get_cached(key: str, ttl_seconds: float) -> Any | None:
    """Cache'te geçerli (süresi dolmamış) bir değer varsa döndür, yoksa None."""
    path = _key_to_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if time.time() - payload.get("_cached_at", 0) > ttl_seconds:
        return None
    return payload.get("value")


def set_cached(key: str, value: Any) -> None:
    """Değeri cache'e yaz (zaman damgasıyla)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _key_to_path(key)
    payload = {"_cached_at": time.time(), "value": value}
    path.write_text(json.dumps(payload), encoding="utf-8")
