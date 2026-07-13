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


def bootstrap_total_return_ci(
    trade_pnls: list[float],
    initial_capital: float,
    *,
    samples: int = 10_000,
    confidence: float = 0.90,
    seed: int = 42,
) -> Optional[tuple[float, float]]:
    """İşlemleri yerine-koymalı örnekleyerek toplam getiri (%) güven aralığı (Görev 1.3).

    Her örneklemde n işlem (yerine koymalı) çekilir, toplam PnL başlangıç
    sermayesine oranlanır; dağılımın (1±confidence)/2 yüzdelikleri döner.
    Küçük örneklemlerde (3 yılda 32-51 işlem) ham getiri rakamının ne kadar
    gürültülü olduğunu görünür kılar. İşlem sayısı < 2 ise None.
    """
    if len(trade_pnls) < 2 or initial_capital <= 0:
        return None
    rng = np.random.default_rng(seed)
    pnls = np.asarray(trade_pnls, dtype=float)
    idx = rng.integers(0, len(pnls), size=(samples, len(pnls)))
    totals = pnls[idx].sum(axis=1) / initial_capital * 100.0
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(totals, [alpha, 1.0 - alpha])
    return float(lo), float(hi)


def ci_overlap(a: Optional[tuple[float, float]], b: Optional[tuple[float, float]]) -> Optional[bool]:
    """İki güven aralığı çakışıyor mu? Aralıklardan biri yoksa None."""
    if a is None or b is None:
        return None
    return a[0] <= b[1] and b[0] <= a[1]


