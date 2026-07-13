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


def load_bars(symbol: str, *, years: float = 3.0) -> pd.DataFrame:
    """Sembol için günlük barları döndür (24 saat disk cache'li)."""
    BARS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = BARS_CACHE_DIR / f"{symbol}_{years:g}y.pkl"
    if cache_path.exists() and (time.time() - cache_path.stat().st_mtime) < CACHE_TTL_SECONDS:
        try:
            return pickle.loads(cache_path.read_bytes())
        except Exception:  # noqa: BLE001
            pass
    df = YFinanceClient().get_daily_bars(symbol, years=years)
    if not df.empty:
        cache_path.write_bytes(pickle.dumps(df))
    return df
