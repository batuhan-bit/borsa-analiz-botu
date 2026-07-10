"""Teknik göstergeler ve teknik sinyal skoru.

Göstergeler: RSI, MACD, 50/200 hareketli ortalama kesişimi, hacim teyidi.
Girdi: günlük OHLCV DataFrame (bot.data.common sözleşmesi).
Çıktı: gösterge değerleri sözlüğü + [-1, 1] teknik skor ve gerekçeler.

Skor konvansiyonu: pozitif = boğa/alış eğilimi, negatif = ayı/satış eğilimi.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from .util import clip, last_valid, tail2


def compute_indicators(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    """OHLCV DataFrame'inden ham gösterge değerlerini hesapla.

    Kesişim tespiti için MACD/MA'ların hem son hem önceki değerleri döner.
    Yetersiz veri varsa ilgili alanlar None olur.
    """
    if df is None or df.empty or len(df) < 2:
        return {}

    from ta.momentum import RSIIndicator
    from ta.trend import MACD

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    rsi_cfg = cfg["rsi"]
    macd_cfg = cfg["macd"]
    ma_cfg = cfg["moving_averages"]
    vol_cfg = cfg["volume_confirmation"]

    rsi = RSIIndicator(close, window=rsi_cfg["period"]).rsi()
    macd = MACD(
        close,
        window_slow=macd_cfg["slow"],
        window_fast=macd_cfg["fast"],
        window_sign=macd_cfg["signal"],
    )
    macd_line = macd.macd()
    macd_sig = macd.macd_signal()
    ma_short = close.rolling(ma_cfg["short"]).mean()
    ma_long = close.rolling(ma_cfg["long"]).mean()
    vol_avg = volume.rolling(vol_cfg["lookback_days"]).mean()

    macd_prev, macd_now = tail2(macd_line)
    sig_prev, sig_now = tail2(macd_sig)
    mas_prev, mas_now = tail2(ma_short)
    mal_prev, mal_now = tail2(ma_long)

    last_vol = last_valid(volume)
    avg_vol = last_valid(vol_avg)
    volume_ratio = (last_vol / avg_vol) if (last_vol and avg_vol) else None

    return {
        "close": last_valid(close),
        "rsi": last_valid(rsi),
        "macd": macd_now,
        "macd_prev": macd_prev,
        "macd_signal": sig_now,
        "macd_signal_prev": sig_prev,
        "ma_short": mas_now,
        "ma_short_prev": mas_prev,
        "ma_long": mal_now,
        "ma_long_prev": mal_prev,
        "volume_ratio": volume_ratio,
        "n_bars": len(df),
    }


def technical_score(indicators: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Göstergelerden [-1, 1] teknik skor ve insan-okur gerekçeleri üret."""
    if not indicators:
        return 0.0, []

    reasons: list[str] = []
    components: list[float] = []

    # --- RSI: aşırı satım pozitif, aşırı alım negatif ---
    rsi = indicators.get("rsi")
    overbought = cfg["rsi"]["overbought"]
    oversold = cfg["rsi"]["oversold"]
    if rsi is not None:
        # 50 nötr; overbought'ta -1, aynı mesafede altında +1 olacak şekilde ölçekle
        components.append(clip((50 - rsi) / (overbought - 50), -1, 1))
        if rsi <= oversold:
            reasons.append(f"RSI {rsi:.0f} (aşırı satım — alış)")
        elif rsi >= overbought:
            reasons.append(f"RSI {rsi:.0f} (aşırı alım — satış)")

    # --- MACD: sinyal çizgisiyle kesişim ---
    m, mp = indicators.get("macd"), indicators.get("macd_prev")
    s, sp = indicators.get("macd_signal"), indicators.get("macd_signal_prev")
    if m is not None and s is not None:
        crossed_up = mp is not None and sp is not None and mp <= sp and m > s
        crossed_down = mp is not None and sp is not None and mp >= sp and m < s
        if crossed_up:
            components.append(1.0)
            reasons.append("MACD yukarı kesişim (boğa)")
        elif crossed_down:
            components.append(-1.0)
            reasons.append("MACD aşağı kesişim (ayı)")
        elif m > s:
            components.append(0.4)
        elif m < s:
            components.append(-0.4)

    # --- 50/200 hareketli ortalama: altın / ölüm çaprazı ---
    short, sh_p = indicators.get("ma_short"), indicators.get("ma_short_prev")
    long, lo_p = indicators.get("ma_long"), indicators.get("ma_long_prev")
    if short is not None and long is not None:
        golden = sh_p is not None and lo_p is not None and sh_p <= lo_p and short > long
        death = sh_p is not None and lo_p is not None and sh_p >= lo_p and short < long
        if golden:
            components.append(1.0)
            reasons.append("Altın çaprazı (50G > 200G)")
        elif death:
            components.append(-1.0)
            reasons.append("Ölüm çaprazı (50G < 200G)")
        elif short > long:
            components.append(0.4)
        elif short < long:
            components.append(-0.4)

    if not components:
        return 0.0, reasons

    score = sum(components) / len(components)

    # --- Hacim teyidi: yüksek hacim sinyali güçlendirir, düşük hacim zayıflatır ---
    vr = indicators.get("volume_ratio")
    min_mult = cfg["volume_confirmation"]["min_multiplier"]
    if vr is not None:
        if vr >= min_mult:
            score *= 1.15
            reasons.append(f"Hacim ortalamanın {vr:.1f}× (teyit)")
        elif vr < 0.7:
            score *= 0.85

    return clip(score, -1, 1), reasons
