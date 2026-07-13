"""Backtest/benchmark için günlük bar yükleme (24 saatlik disk cache'li).

backtest.py ve benchmark.py aynı veri erişimini paylaşır — aynı sembol+dönem
ikinci kez istendiğinde yeniden indirilmez (cache anahtarı döneme bağlıdır).
"""
from __future__ import annotations

import pickle
import time

import pandas as pd

from bot.config import ROOT
from bot.data import YFinanceClient

BARS_CACHE_DIR = ROOT / "data_cache" / "backtest_bars"
CACHE_TTL_SECONDS = 24 * 3600


def load_bars(
    symbol: str,
    *,
    years: float = 3.0,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Sembol için günlük barları döndür (24 saat disk cache'li).

    start/end (YYYY-MM-DD) verilirse o aralık çekilir (Görev 1.2); cache
    anahtarı döneme bağlıdır, farklı dönemler ayrı dosyalarda saklanır.
    """
    BARS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    period_key = f"{start}_{end}" if start or end else f"{years:g}y"
    cache_path = BARS_CACHE_DIR / f"{symbol}_{period_key}.pkl"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < CACHE_TTL_SECONDS:
        try:
            return pickle.loads(cache_path.read_bytes())
        except Exception:  # noqa: BLE001
            pass
    df = YFinanceClient().get_daily_bars(symbol, years=years, start=start, end=end)
    if not df.empty:
        cache_path.write_bytes(pickle.dumps(df))
    return df
