"""Temel analiz skoru.

Girdiler: haber duygusu, kazanç sürprizleri, analist yükseltme/düşürmeleri
(Alpha Vantage + web). Çıktı: [-1, 1] skor + gerekçeler.
"""
from __future__ import annotations

from typing import Any


def fundamental_score(data: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Temel verilerden [-1, 1] arası skor ve gerekçeleri üret."""
    raise NotImplementedError("Adım 3'te doldurulacak")
