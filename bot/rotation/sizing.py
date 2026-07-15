"""Sizing (v2) — hedef ağırlıkları tutar ve adete çevirir.

Rotasyon motoru pozisyonları ağırlık (portföy kesri) olarak üretir; bu modül
ağırlığı sermaye ve fiyatla birlikte somut tutar/adete dönüştürür. Canlı akış
ve backtest AYNI fonksiyonu kullanır — böylece icra varsayımları tutarlı kalır.

Kesirli hisse ve sabit komisyon Görev D.2'de bu modüle eklenir; şimdilik
`fractional` bayrağı ve tam-sayı yuvarlama desteklenir (varsayılan tam sayı).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class SizedPosition:
    symbol: str
    weight: float          # portföy kesri (0..1)
    price: float
    shares: float          # önerilen adet (kesirli mod açıksa ondalıklı)
    target_value: float    # ağırlık * sermaye (ideal tutar)
    actual_value: float    # shares * price (yuvarlama sonrası gerçek tutar)


def size_positions(
    targets: Iterable,
    capital: float,
    prices: Mapping[str, float],
    *,
    fractional: bool = False,
    shares_decimals: int = 2,
) -> list[SizedPosition]:
    """Hedef pozisyonları (symbol + weight taşıyan nesneler) tutar/adete çevir.

    targets: `symbol` ve `weight` alanlarına sahip nesneler (ör. TargetPosition).
    capital: dağıtılacak toplam sermaye (USD).
    prices:  symbol -> güncel fiyat. Fiyatı olmayan/0 olan sembolde adet 0.
    fractional=True ise adet `shares_decimals` ondalığa yuvarlanır; aksi halde
    aşağı yuvarlanır (tam sayı hisse).
    """
    out: list[SizedPosition] = []
    for t in targets:
        symbol = t.symbol
        weight = float(t.weight)
        price = float(prices.get(symbol, 0.0) or 0.0)
        target_value = weight * capital
        if price <= 0:
            shares = 0.0
        elif fractional:
            shares = round(target_value / price, shares_decimals)
        else:
            shares = float(math.floor(target_value / price))
        out.append(SizedPosition(
            symbol=symbol,
            weight=weight,
            price=price,
            shares=shares,
            target_value=round(target_value, 2),
            actual_value=round(shares * price, 2),
        ))
    return out
