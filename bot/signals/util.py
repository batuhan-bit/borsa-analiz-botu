"""Sinyal modülleri için küçük yardımcılar."""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def last_valid(series: pd.Series) -> Optional[float]:
    """Serinin son NaN olmayan değeri (yoksa None)."""
    s = series.dropna()
    if s.empty:
        return None
    val = float(s.iloc[-1])
    return None if math.isnan(val) else val


def tail2(series: pd.Series) -> tuple[Optional[float], Optional[float]]:
    """Son iki geçerli değeri (önceki, son) olarak döndür.

    Kesişim (crossover) tespiti için kullanılır.
    """
    s = series.dropna()
    if s.empty:
        return None, None
    if len(s) == 1:
        return None, float(s.iloc[-1])
    return float(s.iloc[-2]), float(s.iloc[-1])
