"""Teknik göstergeler ve teknik sinyal skoru.

Göstergeler: RSI, MACD, 50/200 hareketli ortalama kesişimi, hacim teyidi.
Girdi: günlük OHLCV DataFrame. Çıktı: gösterge değerleri + [-1, 1] skor.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def compute_indicators(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    """OHLCV DataFrame'inden ham gösterge değerlerini hesapla.

    Döndürür: rsi, macd, macd_signal, ma_short, ma_long, volume_ratio, ...
    """
    raise NotImplementedError("Adım 3'te doldurulacak")


def technical_score(indicators: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Göstergelerden [-1, 1] arası teknik skor ve gerekçeleri üret.

    Örn: RSI < 30 (aşırı satım) + MACD yukarı kesişim + altın çaprazı +
    hacim teyidi → güçlü pozitif skor.
    """
    raise NotImplementedError("Adım 3'te doldurulacak")
