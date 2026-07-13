"""Al-ve-tut kıyas çizgileri (benchmark) — Görev 1.1.

Stratejinin katma değeri ancak aynı evrenin pasif getirisiyle kıyaslanarak
ölçülebilir (evren bugünden geriye seçildiği için survivorship/hindsight
bias içerir; benchmark da aynı evreni kullandığından bu önyargı kıyasta
büyük ölçüde nötrlenir).

Üç kıyas çizgisi üretilir:
  1. Eşit ağırlık      : evrendeki her sembole eşit sermaye
  2. Sepet ağırlıklı   : sepet dağılımı (%40/%35/%25), sepet içinde eşit
  3. SPY al-ve-tut     : piyasa kıyası

Politika (Görev 1.2 ile tutarlı): dönem başında verisi olmayan sembolün payı
NAKİTTE bekler; sembol, verisi başladığı ilk gün o günkü kapanıştan alınır.
Hiç verisi olmayan semboller düşülür ve ağırlıklar yeniden normalize edilir.
Fiyatlar temettü+bölünme düzeltmelidir (yfinance auto_adjust=True).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from .metrics import (
    cagr_pct,
    calmar_ratio,
    max_drawdown_pct,
    sharpe_ratio,
    total_return_pct,
)


@dataclass
class BenchmarkResult:
    name: str
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    calmar: Optional[float]
    start: str
    end: str
    n_symbols: int
    late_joiners: dict[str, str] = field(default_factory=dict)  # sembol -> katılım tarihi
    equity_curve: pd.Series = field(default=None, repr=False)


def buy_and_hold(
    bars: dict[str, pd.DataFrame],
    weights: dict[str, float],
    initial_capital: float,
    name: str,
) -> Optional[BenchmarkResult]:
    """Verilen ağırlıklarla al-ve-tut portföyünü simüle et.

    bars: sembol -> OHLCV DataFrame (yalnızca simüle edilecek dönemi içermeli).
    weights: sembol -> göreli ağırlık (toplamı 1 olmak zorunda değil; normalize edilir).
    """
    avail = {
        s: df for s, df in bars.items()
        if s in weights and df is not None and not df.empty
    }
    if not avail:
        return None

    weight_sum = sum(weights[s] for s in avail)
    calendar = sorted(set().union(*[set(df.index) for df in avail.values()]))
    calendar_idx = pd.DatetimeIndex(calendar)

    total = pd.Series(0.0, index=calendar_idx)
    late_joiners: dict[str, str] = {}
    period_start = calendar_idx[0]

    for sym, df in avail.items():
        capital = initial_capital * weights[sym] / weight_sum
        close = df["close"].astype(float)
        first_date = close.index[0]
        shares = capital / float(close.iloc[0])
        value = (shares * close).reindex(calendar_idx).ffill()
        # Sembol listelenmeden önce payı nakitte bekler
        value = value.fillna(capital)
        total += value
        if first_date > period_start:
            late_joiners[sym] = str(first_date.date())

    return BenchmarkResult(
        name=name,
        initial_capital=initial_capital,
        final_equity=round(float(total.iloc[-1]), 2),
        total_return_pct=round(total_return_pct(total), 2),
        annualized_return_pct=round(cagr_pct(total), 2),
        max_drawdown_pct=round(max_drawdown_pct(total), 2),
        sharpe=round(sharpe_ratio(total), 2),
        calmar=(lambda c: round(c, 2) if c is not None else None)(calmar_ratio(total)),
        start=str(calendar_idx[0].date()),
        end=str(calendar_idx[-1].date()),
        n_symbols=len(avail),
        late_joiners=late_joiners,
        equity_curve=total,
    )


def benchmark_suite(
    bars: dict[str, pd.DataFrame],
    baskets_cfg: dict[str, Any],
    initial_capital: float,
    *,
    basket_limit: Optional[int] = None,
) -> list[BenchmarkResult]:
    """Üç kıyas çizgisini (eşit ağırlık / sepet ağırlıklı / SPY) hesapla."""
    equal_w: dict[str, float] = {}
    basket_w: dict[str, float] = {}
    for cfg in baskets_cfg.values():
        syms = list(cfg.get("universe", []))
        if basket_limit:
            syms = syms[:basket_limit]
        alloc = float(cfg["allocation_pct"]) / 100.0
        for s in syms:
            equal_w[s] = 1.0
            basket_w[s] = alloc / len(syms)

    results = []
    for weights, name in [
        (equal_w, "Eşit-ağırlık evren (al-tut)"),
        (basket_w, "Sepet-ağırlıklı evren (al-tut)"),
        ({"SPY": 1.0}, "SPY (al-tut)"),
    ]:
        r = buy_and_hold(bars, weights, initial_capital, name)
        if r is not None:
            results.append(r)
    return results
