"""Veri katmanı birim testleri — ağ/anahtar gerektirmez."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from bot.config import Secrets
from bot.data import AlpacaClient, cache
from bot.data.common import OHLCV_COLUMNS, normalize_ohlcv


def test_normalize_lowercases_and_selects_columns():
    raw = pd.DataFrame(
        {
            "Open": [1.0, 2.0],
            "High": [2.0, 3.0],
            "Low": [0.5, 1.5],
            "Close": [1.5, 2.5],
            "Volume": [100, 200],
            "Dividends": [0, 0],  # fazladan kolon atılmalı
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-01"]),  # ters sıralı
    )
    out = normalize_ohlcv(
        raw,
        rename={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"},
    )
    assert list(out.columns) == OHLCV_COLUMNS
    assert out.index.is_monotonic_increasing          # artan sıraya alındı
    assert out.index.name == "date"
    assert out.index.tz is None


def test_normalize_strips_timezone():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("America/New_York")
    raw = pd.DataFrame(
        {c: [1.0, 2.0] for c in OHLCV_COLUMNS},
        index=idx,
    )
    out = normalize_ohlcv(raw)
    assert out.index.tz is None


def test_normalize_missing_columns_raises():
    raw = pd.DataFrame({"open": [1.0]}, index=pd.to_datetime(["2024-01-01"]))
    with pytest.raises(ValueError, match="OHLCV kolonları eksik"):
        normalize_ohlcv(raw)


def test_normalize_empty_returns_empty_contract():
    out = normalize_ohlcv(pd.DataFrame())
    assert list(out.columns) == OHLCV_COLUMNS
    assert out.empty


def test_cache_roundtrip_and_ttl():
    key = "test:roundtrip"
    cache.set_cached(key, {"a": 1})
    assert cache.get_cached(key, ttl_seconds=60) == {"a": 1}
    # TTL geçmişse None dönmeli
    time.sleep(0.01)
    assert cache.get_cached(key, ttl_seconds=0.001) is None


def test_alpaca_degrades_without_keys():
    client = AlpacaClient(Secrets.load(strict=False))
    df = client.get_daily_bars("AAPL", years=0.1)
    assert df.empty   # anahtar yoksa çökmeden boş döner
