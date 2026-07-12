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
    twenty_low = float(df["low"].tail(20).min())
    twenty_high = float(df["high"].tail(20).max())
    sixty_high = float(df["high"].tail(60).max())
    support, resistance = twenty_low, sixty_high

    # Stop: destek-temelli (20g dip altı) ve ATR-temelli (2 ATR altı) stopların
    # DAHA SIKI olanı — momentum hisselerinde 20g dip çok uzak kalırsa ATR devreye
    # girer. Hiçbir durumda %max_loss'tan fazla risk alınmaz.
    support_stop = twenty_low - 0.5 * atr if atr else twenty_low
    atr_stop = entry_price - 2 * atr if atr else twenty_low
    stop = max(support_stop, atr_stop)
    stop = max(stop, entry_price * (1 - max_loss_pct / 100.0))   # %max_loss tavanı
    stop = min(stop, entry_price * 0.999)                        # stop mutlaka girişin altında

    # Hedefler: yakın direnç veya ATR projeksiyonu (hangisi yukarıdaysa)
    target1 = max(twenty_high, entry_price + 2 * atr) if atr else twenty_high
    target2 = max(sixty_high, entry_price + 4 * atr) if atr else sixty_high
    if target2 <= target1:
        target2 = target1 + (2 * atr if atr else target1 * 0.02)

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
