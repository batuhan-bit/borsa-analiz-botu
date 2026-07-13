"""Teknik göstergeler ve teknik sinyal skoru.

Göstergeler: RSI, MACD, 50/200 hareketli ortalama kesişimi, hacim teyidi.
Girdi: günlük OHLCV DataFrame (bot.data.common sözleşmesi).
Çıktı: gösterge değerleri sözlüğü + [-1, 1] teknik skor ve gerekçeler.

Skor konvansiyonu: pozitif = boğa/alış eğilimi, negatif = ayı/satış eğilimi.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from .util import clip


def indicator_frame(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Tüm geçmiş için gösterge SERİLERİNİ tek DataFrame olarak hesapla.

    Kolonlar: close, rsi, macd, macd_signal, ma_short, ma_long, volume_ratio.
    Hem canlı motor (son satır) hem backtest (her gün) aynı kaynağı kullanır.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    from ta.momentum import RSIIndicator
    from ta.trend import MACD

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    macd_cfg = cfg["macd"]
    ma_cfg = cfg["moving_averages"]

    macd = MACD(
        close,
        window_slow=macd_cfg["slow"],
        window_fast=macd_cfg["fast"],
        window_sign=macd_cfg["signal"],
    )
    lookback = cfg["volume_confirmation"]["lookback_days"]
    vol_avg = volume.rolling(lookback).mean()

    # Yönlü hacim (toplama/dağıtım): son `lookback` günde hacmin ne kadarı
    # yükseliş günlerinde (fiyat arttı) vs düşüş günlerinde gerçekleşti.
    # (Σ yön·hacim) / (Σ hacim) ∈ [-1, 1]; +1 = tüm hacim yükselişte (toplama),
    # -1 = tüm hacim düşüşte (dağıtım). "Hacim hareketi teyit ediyor mu" sorusu.
    delta = close.diff()
    direction = (delta > 0).astype(int) - (delta < 0).astype(int)
    signed_vol = direction * volume

    frame = pd.DataFrame(index=df.index)
    frame["close"] = close
    frame["rsi"] = RSIIndicator(close, window=cfg["rsi"]["period"]).rsi()
    frame["macd"] = macd.macd()
    frame["macd_signal"] = macd.macd_signal()
    frame["ma_short"] = close.rolling(ma_cfg["short"]).mean()
    frame["ma_long"] = close.rolling(ma_cfg["long"]).mean()
    frame["volume_ratio"] = volume / vol_avg
    frame["vol_direction"] = signed_vol.rolling(lookback).sum() / volume.rolling(lookback).sum()
    return frame


def _nn(value: Any) -> Optional[float]:
    """NaN/None -> None; aksi halde float."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def indicators_from_rows(now: Any, prev: Any, *, n_bars: Optional[int] = None) -> dict[str, Any]:
    """Gösterge çerçevesinin bir (şimdiki, önceki) satır çiftini skor sözlüğüne çevir.

    now/prev pandas Series veya None olabilir. Kesişim tespiti prev'e dayanır.
    """
    def g(row: Any, key: str) -> Optional[float]:
        if row is None:
            return None
        return _nn(row.get(key))

    return {
        "close": g(now, "close"),
        "rsi": g(now, "rsi"),
        "macd": g(now, "macd"),
        "macd_prev": g(prev, "macd"),
        "macd_signal": g(now, "macd_signal"),
        "macd_signal_prev": g(prev, "macd_signal"),
        "ma_short": g(now, "ma_short"),
        "ma_short_prev": g(prev, "ma_short"),
        "ma_long": g(now, "ma_long"),
        "ma_long_prev": g(prev, "ma_long"),
        "volume_ratio": g(now, "volume_ratio"),
        "vol_direction": g(now, "vol_direction"),
        "n_bars": n_bars,
    }


def compute_indicators(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    """OHLCV DataFrame'inin SON gününe ait gösterge değerlerini döndür.

    Kesişim tespiti için MACD/MA'ların hem son hem önceki değerleri döner.
    Yetersiz veri varsa ilgili alanlar None olur.
    """
    frame = indicator_frame(df, cfg)
    if frame.empty:
        return {}
    now = frame.iloc[-1]
    prev = frame.iloc[-2] if len(frame) >= 2 else None
    return indicators_from_rows(now, prev, n_bars=len(df))


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

    # --- Fiyatın ortalamalara göre konumu (TREND FİLTRESİ) ---
    # Fiyat MA'ların ALTINDAysa hisse kısa/orta vade düşüşte demektir. MA50>MA200
    # (gecikmeli) olsa bile bu, "kırılmış ama göstergeleri henüz dönmemiş" durumu
    # yakalar ve düşen bıçağı almayı engeller. Ağırlıklar strategy.yaml'den gelir.
    price = indicators.get("close")
    tf = cfg.get("trend_filter", {})
    w_long = tf.get("price_vs_ma_long", 0.6)
    w_short = tf.get("price_vs_ma_short", 0.4)
    # Ağırlık 0 ise bileşen hiç eklenmez (skoru sulandırmasın) — böylece
    # trend filtresi config'ten/backtest varyantından tamamen kapatılabilir.
    if price is not None and long is not None and w_long > 0:
        if price >= long:
            components.append(w_long)
        else:
            components.append(-w_long)
            reasons.append("Fiyat 200G ortalamanın altında (trend zayıf)")
    if price is not None and short is not None and w_short > 0:
        components.append(w_short if price >= short else -w_short)

    # --- Yönlü hacim (toplama/dağıtım): hacim fiyat hareketini teyit ediyor mu? ---
    # Ağırlık>0 ise skoru etkiler; her hâlükârda belirgin durumu gerekçe olarak gösterir.
    vd = indicators.get("vol_direction")
    if vd is not None:
        w_vd = cfg["volume_confirmation"].get("direction_weight", 0.3)
        if w_vd > 0:
            components.append(clip(vd, -1, 1) * w_vd)
        if vd <= -0.3:
            reasons.append("Hacim düşüş günlerinde ağır (dağıtım — olumsuz)")
        elif vd >= 0.3:
            reasons.append("Hacim yükseliş günlerinde ağır (toplama — olumlu)")

    if not components:
        return 0.0, reasons

    score = sum(components) / len(components)

    # --- Hacim büyüklüğü teyidi: yüksek hacim sinyali güçlendirir (yönden bağımsız) ---
    vr = indicators.get("volume_ratio")
    min_mult = cfg["volume_confirmation"]["min_multiplier"]
    if vr is not None:
        if vr >= min_mult:
            score *= 1.15
            reasons.append(f"Hacim ortalamanın {vr:.1f}× (teyit)")
        elif vr < 0.7:
            score *= 0.85

    return clip(score, -1, 1), reasons
