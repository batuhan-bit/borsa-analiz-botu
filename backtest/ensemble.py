"""Pertürbasyon topluluğu (Görev B.2) — tekil sayı yerine medyan + bant.

v1'in Δ ayrıştırması, tekil bir backtest rakamının yol-bağımlılığı nedeniyle
anlamsız olduğunu kanıtladı. v2'de HİÇBİR sonuç tekil sayıyla raporlanmaz: her
konfigürasyon bir toplulukla koşulur ve medyan + [p_low, p_high] bandı verilir.

Pertürbasyon eksenleri (config'ten):
  - Başlangıç tarihi ±`start_jitter_days` işlem günü (tekdüze).
  - Kayma ±`slippage_jitter_pct` (çarpansal) — run_rotation_backtest slippage_scale.

Benchmark'lar (SPY al-tut, eşit-ağırlık evren, sepet-ağırlıklı evren) AYNI
pencerelerle yan yana raporlanır. Tasarım sağlığı: topluluk bandı genişliği
ayrıca gösterilir; bant medyanın ±`health_band_pct`'inden genişse "yol-bağımlılığı
geri geldi" uyarısı basılır (rotasyon yapısında bant DAR olmalıdır).

Determinizm: aynı `seed` → aynı pertürbasyon çekilişleri → aynı topluluk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from bot.config import Strategy
from backtest.rotation_backtest import run_rotation_backtest


@dataclass
class EnsembleStats:
    label: str
    samples: list[float]
    band_low_pct: int
    band_high_pct: int

    @property
    def median(self) -> float:
        return float(np.median(self.samples)) if self.samples else 0.0

    @property
    def p_low(self) -> float:
        return float(np.percentile(self.samples, self.band_low_pct)) if self.samples else 0.0

    @property
    def p_high(self) -> float:
        return float(np.percentile(self.samples, self.band_high_pct)) if self.samples else 0.0

    @property
    def band_width(self) -> float:
        return self.p_high - self.p_low


@dataclass
class EnsembleReport:
    config_label: str
    window: tuple[str, str]
    runs: int
    strategy_stats: EnsembleStats
    benchmarks: list[EnsembleStats] = field(default_factory=list)
    health_ok: bool = True
    health_threshold: float = 0.0
    health_band_pct: int = 30

    @property
    def health_note(self) -> str:
        if self.health_ok:
            return "bant dar (tasarım sağlıklı)"
        return ("⚠️ bant medyanın ±%{}'inden geniş — yol-bağımlılığı geri geldi"
                .format(self.health_band_pct))


# ----------------------------------------------------------------------
#  Benchmark getirileri (al-tut; maliyetsiz — pertürbasyon yalnız başlangıç)
# ----------------------------------------------------------------------
def _buy_hold(df: pd.DataFrame, start, end) -> Optional[float]:
    if df is None or df.empty:
        return None
    s = df["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    return (s.iloc[-1] / s.iloc[0] - 1.0) * 100.0


def _equal_weight(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[float]:
    rets = [_buy_hold(bars.get(s), start, end) for s in strategy.universe_symbols]
    rets = [r for r in rets if r is not None]
    return float(np.mean(rets)) if rets else None


def _basket_weight(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[float]:
    total = 0.0
    weight_sum = 0.0
    for name, cfg in strategy.baskets.items():
        syms = [s for s in strategy.universe_symbols if strategy.basket_of(s) == name]
        rets = [_buy_hold(bars.get(s), start, end) for s in syms]
        rets = [r for r in rets if r is not None]
        if not rets:
            continue
        alloc = cfg.get("allocation_pct", 0) / 100.0
        total += alloc * float(np.mean(rets))
        weight_sum += alloc
    return total / weight_sum if weight_sum > 0 else None


# ----------------------------------------------------------------------
#  Topluluk koşusu
# ----------------------------------------------------------------------
def _full_calendar(bars: Mapping[str, pd.DataFrame]) -> pd.DatetimeIndex:
    if not bars:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted(set().union(*[set(df.index) for df in bars.values()])))


def run_ensemble(
    strategy: Strategy,
    bars: Mapping[str, pd.DataFrame],
    *,
    start,
    end,
    config_label: str = "config",
) -> EnsembleReport:
    """Bir konfigürasyonu topluluk olarak koş ve medyan + bant raporu üret."""
    ens = strategy.rotation_backtest.get("ensemble", {})
    runs = int(ens.get("runs", 50))
    jitter_days = int(ens.get("start_jitter_days", 10))
    slip_jitter = float(ens.get("slippage_jitter_pct", 50)) / 100.0
    band_low = int(ens.get("band_low_pct", 10))
    band_high = int(ens.get("band_high_pct", 90))
    health_pct = int(ens.get("health_band_pct", 30))
    seed = int(ens.get("seed", 12345))

    calendar = _full_calendar(bars)
    if calendar.empty:
        empty = EnsembleStats(config_label, [], band_low, band_high)
        return EnsembleReport(config_label, (str(start), str(end)), 0, empty)

    # Nominal başlangıcın takvimdeki konumu (jitter buradan kayar)
    ge = calendar[calendar >= pd.Timestamp(start)]
    base_pos = calendar.get_loc(ge[0]) if len(ge) else 0

    rng = np.random.default_rng(seed)
    strat_samples: list[float] = []
    bh_samples: list[float] = []
    ew_samples: list[float] = []
    bw_samples: list[float] = []

    for _ in range(runs):
        offset = int(rng.integers(-jitter_days, jitter_days + 1))
        slip_scale = float(rng.uniform(1.0 - slip_jitter, 1.0 + slip_jitter))
        pos = min(max(base_pos + offset, 0), len(calendar) - 1)
        run_start = calendar[pos]

        r = run_rotation_backtest(strategy, bars, start=run_start, end=end,
                                  apply_costs=True, slippage_scale=slip_scale)
        strat_samples.append(r.total_return_pct)

        bh = _buy_hold(bars.get(strategy.rotation_backtest.get("regime", {}).get("benchmark", "SPY")),
                       run_start, end)
        if bh is not None:
            bh_samples.append(bh)
        ew = _equal_weight(strategy, bars, run_start, end)
        if ew is not None:
            ew_samples.append(ew)
        bw = _basket_weight(strategy, bars, run_start, end)
        if bw is not None:
            bw_samples.append(bw)

    strat_stats = EnsembleStats(config_label, strat_samples, band_low, band_high)
    benchmarks = [
        EnsembleStats("SPY al-tut", bh_samples, band_low, band_high),
        EnsembleStats("Eşit-ağırlık evren", ew_samples, band_low, band_high),
        EnsembleStats("Sepet-ağırlıklı evren", bw_samples, band_low, band_high),
    ]

    # Tasarım sağlığı: bant genişliği medyanın ±health_pct'inden geniş mi?
    threshold = 2.0 * (health_pct / 100.0) * abs(strat_stats.median)
    health_ok = strat_stats.band_width <= threshold if threshold > 0 else False

    return EnsembleReport(
        config_label=config_label, window=(str(start), str(end)), runs=runs,
        strategy_stats=strat_stats, benchmarks=benchmarks,
        health_ok=health_ok, health_threshold=threshold, health_band_pct=health_pct,
    )


# ----------------------------------------------------------------------
#  Markdown render (bantsız rakam YOK — kabul kriteri)
# ----------------------------------------------------------------------
def _fmt(stats: EnsembleStats) -> str:
    """medyan [p_low, p_high] — her rakam bantla birlikte."""
    return f"%{stats.median:+.2f}  [%{stats.p_low:+.2f}, %{stats.p_high:+.2f}]"


def render_report_md(report: EnsembleReport) -> str:
    lines: list[str] = []
    lines.append(f"### {report.config_label}")
    lines.append("")
    lines.append(f"- Pencere: **{report.window[0]} → {report.window[1]}**  "
                 f"({report.runs} koşuluk topluluk; bant [%{report.strategy_stats.band_low_pct}, "
                 f"%{report.strategy_stats.band_high_pct}])")
    lines.append("")
    lines.append("| Seri | Getiri (medyan + bant) |")
    lines.append("|------|------------------------|")
    lines.append(f"| **Strateji** | {_fmt(report.strategy_stats)} |")
    for b in report.benchmarks:
        lines.append(f"| {b.label} | {_fmt(b)} |")
    lines.append("")
    lines.append(f"- Bant genişliği (p{report.strategy_stats.band_high_pct}−p"
                 f"{report.strategy_stats.band_low_pct}): "
                 f"**%{report.strategy_stats.band_width:.2f}** — {report.health_note}")
    lines.append("")
    return "\n".join(lines)
