"""Ortak performans metrikleri — backtest ve benchmark aynı hesabı kullanır.

Tüm fonksiyonlar günlük özsermaye eğrisi (pd.Series, DatetimeIndex) üzerinde
çalışır. Sharpe için rf=0 kabulü yapılır (iş listesi Görev 1.1).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def total_return_pct(equity: pd.Series) -> float:
    """Toplam getiri (%) — eğrinin ilk değerinden son değerine."""
    if equity is None or len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0] - 1) * 100.0)


def cagr_pct(equity: pd.Series) -> float:
    """Yıllıklandırılmış getiri (%) — takvim süresine göre bileşik."""
    if equity is None or len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    span_years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9)
    ratio = float(equity.iloc[-1] / equity.iloc[0])
    if ratio <= 0:
        return -100.0
    return float((ratio ** (1 / span_years) - 1) * 100.0)


def max_drawdown_pct(equity: pd.Series) -> float:
    """Maksimum düşüş (%) — negatif değer döner (ör. -25.3)."""
    if equity is None or equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min() * 100.0)


def sharpe_ratio(equity: pd.Series) -> float:
    """Yıllıklandırılmış Sharpe oranı (rf=0), günlük getirilerden."""
    if equity is None or len(equity) < 3:
        return 0.0
    daily = equity.pct_change().dropna()
    std = float(daily.std())
    if std == 0 or np.isnan(std):
        return 0.0
    return float(daily.mean() / std * np.sqrt(TRADING_DAYS_PER_YEAR))


def calmar_ratio(equity: pd.Series) -> Optional[float]:
    """Calmar oranı: CAGR / |maks. düşüş|. Düşüş yoksa None."""
    dd = max_drawdown_pct(equity)
    if dd >= 0:
        return None
    return float(cagr_pct(equity) / abs(dd))


