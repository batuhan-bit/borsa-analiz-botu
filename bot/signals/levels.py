"""BUY sinyalleri için fiyat seviyeleri: destek, direnç, stop ve hedefler.

Fiyat verisinden (OHLC) hesaplanır; kaynak yok, tamamen deterministik.
- support   : son 20 günün en düşüğü (yakın taban)
- resistance: son 60 günün en yükseği (yakın tavan — bağlam)
- stop      : desteğin ~0.5 ATR altı; ancak strateji %20 zarar tavanını aşmaz
- target1/2 : ATR tabanlı projeksiyon (2 ve 4 ATR)
- risk_reward: (hedef1 - giriş) / (giriş - stop)

Bunlar mekanik seviyelerdir, tavsiye değildir; kullanıcı kendi kararını verir.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range (oynaklık ölçüsü)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr = tr.rolling(period).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else 0.0


def price_levels(df: pd.DataFrame, entry_price: float, *, max_loss_pct: float = 20.0) -> dict[str, Any]:
    """BUY için stop/destek/direnç/hedef seviyelerini hesapla (yetersiz veri -> {})."""
    if df is None or len(df) < 20 or not entry_price:
        return {}

    atr = _atr(df)
    support = float(df["low"].tail(20).min())
    resistance = float(df["high"].tail(60).max())

    # Stop: desteğin biraz altı, ama %max_loss'tan fazla riske girme
    floor_by_pct = entry_price * (1 - max_loss_pct / 100.0)
    technical_stop = support - 0.5 * atr if atr else support
    stop = max(technical_stop, floor_by_pct)   # ikisinden girişe yakın olanı (daha az risk)

    # Hedef1: 3 ATR projeksiyon (ara hedef). Hedef2: yakın direnç (yoksa 5 ATR).
    target1 = entry_price + 3 * atr if atr else resistance
    target2 = resistance if resistance > target1 else (entry_price + 5 * atr if atr else resistance)

    risk = entry_price - stop
    reward = target1 - entry_price
    risk_reward = (reward / risk) if risk > 0 else None

    return {
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "stop": round(stop, 2),
        "target1": round(target1, 2),
        "target2": round(target2, 2),
        "risk_reward": round(risk_reward, 2) if risk_reward else None,
    }
