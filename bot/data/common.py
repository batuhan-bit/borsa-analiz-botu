"""Veri istemcileri arasında paylaşılan yardımcılar.

Tüm istemciler günlük barları AYNI sözleşmeyle döndürür:
  - DatetimeIndex (tz-naive, artan sıralı), adı 'date'
  - Kolonlar: open, high, low, close, volume  (küçük harf, float/int)

Böylece sinyal motoru veriyi hangi kaynaktan geldiğini bilmeden işleyebilir.
"""
from __future__ import annotations

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def normalize_ohlcv(df: pd.DataFrame, rename: dict[str, str] | None = None) -> pd.DataFrame:
    """Ham bar DataFrame'ini standart OHLCV sözleşmesine getir.

    rename: kaynak kolon adlarını -> standart adlara eşleyen sözlük
            (ör. {"Open": "open", ...}). Verilmezse kolonlar küçük harfe çevrilir.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS)

    out = df.rename(columns=rename) if rename else df.rename(columns=str.lower)

    missing = [c for c in OHLCV_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"OHLCV kolonları eksik: {missing}. Mevcut: {list(out.columns)}")

    out = out[OHLCV_COLUMNS].copy()

    # Index'i tz-naive DatetimeIndex yap, adını 'date' ver, artan sırala
    idx = pd.to_datetime(out.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    out.index = idx.normalize()
    out.index.name = "date"
    out = out[~out.index.duplicated(keep="last")].sort_index()

    # Tipleri sayısala zorla, tümü NaN olan satırları at
    for col in OHLCV_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(how="all")
