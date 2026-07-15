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
    strategy_maxdd: Optional[EnsembleStats] = None
    strategy_trades: Optional[EnsembleStats] = None
    strategy_cost: Optional[EnsembleStats] = None
    benchmark_maxdd: list[EnsembleStats] = field(default_factory=list)
    # Küçük bütçe uyumu (Görev D.2): yıllık toplam maliyet / ortalama sermaye.
    # Ölçek cezasını görünür kılar — küçük bütçede sabit komisyon oranı büyür.
    strategy_avg_capital: Optional[EnsembleStats] = None
    strategy_cost_ratio_pct: Optional[EnsembleStats] = None

    @property
    def health_note(self) -> str:
        if self.health_ok:
            return "bant dar (tasarım sağlıklı)"
        return ("⚠️ bant medyanın ±%{}'inden geniş — yol-bağımlılığı geri geldi"
                .format(self.health_band_pct))


# ----------------------------------------------------------------------
#  Benchmark getirileri (al-tut; maliyetsiz — pertürbasyon yalnız başlangıç)
# ----------------------------------------------------------------------
def _normalized_curve(df: Optional[pd.DataFrame], start, end) -> Optional[pd.Series]:
    """Kapanış fiyatını pencere başında 100'e endeksler (MaxDD için ortak taban)."""
    if df is None or df.empty:
        return None
    s = df["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]
    if len(s) < 2 or s.iloc[0] <= 0:
        return None
    return s / s.iloc[0] * 100.0


def _max_dd_pct(curve: Optional[pd.Series]) -> Optional[float]:
    if curve is None or curve.empty:
        return None
    running_max = curve.cummax()
    dd = (curve - running_max) / running_max
    return float(dd.min() * 100.0)


def _composite_curve(curves: list[pd.Series]) -> Optional[pd.Series]:
    """Birden çok normalize eğrinin gün-bazlı eşit ortalaması (hizalı takvim, ffill)."""
    curves = [c for c in curves if c is not None]
    if not curves:
        return None
    df = pd.concat(curves, axis=1).sort_index().ffill()
    return df.mean(axis=1)


def _buy_hold(df: pd.DataFrame, start, end) -> Optional[float]:
    curve = _normalized_curve(df, start, end)
    if curve is None:
        return None
    return float(curve.iloc[-1] - 100.0)


def _equal_weight_curve(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[pd.Series]:
    curves = [_normalized_curve(bars.get(s), start, end) for s in strategy.universe_symbols]
    return _composite_curve(curves)


def _equal_weight(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[float]:
    curve = _equal_weight_curve(strategy, bars, start, end)
    return float(curve.iloc[-1] - 100.0) if curve is not None else None


def _basket_weight_curve(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[pd.Series]:
    weighted: list[pd.Series] = []
    weight_sum = 0.0
    for name, cfg in strategy.baskets.items():
        syms = [s for s in strategy.universe_symbols if strategy.basket_of(s) == name]
        curves = [_normalized_curve(bars.get(s), start, end) for s in syms]
        basket_curve = _composite_curve(curves)
        if basket_curve is None:
            continue
        alloc = cfg.get("allocation_pct", 0) / 100.0
        weighted.append(basket_curve * alloc)
        weight_sum += alloc
    if not weighted or weight_sum <= 0:
        return None
    df = pd.concat(weighted, axis=1).sort_index().ffill()
    return df.sum(axis=1) / weight_sum


def _basket_weight(strategy: Strategy, bars: Mapping[str, pd.DataFrame], start, end) -> Optional[float]:
    curve = _basket_weight_curve(strategy, bars, start, end)
    return float(curve.iloc[-1] - 100.0) if curve is not None else None


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
    strat_dd_samples: list[float] = []
    strat_trade_samples: list[float] = []
    strat_cost_samples: list[float] = []
    strat_avgcap_samples: list[float] = []
    strat_costratio_samples: list[float] = []
    bh_samples: list[float] = []
    bh_dd_samples: list[float] = []
    ew_samples: list[float] = []
    ew_dd_samples: list[float] = []
    bw_samples: list[float] = []
    bw_dd_samples: list[float] = []

    benchmark_symbol = strategy.rotation_backtest.get("regime", {}).get("benchmark", "SPY")
    for _ in range(runs):
        offset = int(rng.integers(-jitter_days, jitter_days + 1))
        slip_scale = float(rng.uniform(1.0 - slip_jitter, 1.0 + slip_jitter))
        pos = min(max(base_pos + offset, 0), len(calendar) - 1)
        run_start = calendar[pos]

        r = run_rotation_backtest(strategy, bars, start=run_start, end=end,
                                  apply_costs=True, slippage_scale=slip_scale)
        strat_samples.append(r.total_return_pct)
        strat_dd_samples.append(r.max_drawdown_pct)
        strat_trade_samples.append(float(r.num_trades))
        strat_cost_samples.append(r.total_cost)
        # Yıllık maliyet / ortalama sermaye (D.2): ortalama sermaye = özsermaye
        # eğrisinin zaman-ortalaması (dağıtılmış sermaye); yıllık maliyet = toplam
        # maliyet / pencere yılı. Oran, küçük bütçede sabit-komisyon sürüklemesini
        # görünür kılar (aynı config, yalnız bütçe mekaniği değiştiğinde kıyaslanır).
        eq = r.equity_curve
        if eq is not None and not eq.empty:
            avg_cap = float(eq.mean())
            span_years = max((eq.index[-1] - eq.index[0]).days / 365.25, 1e-9)
        else:
            avg_cap = float(r.initial_capital)
            span_years = 1e-9
        strat_avgcap_samples.append(avg_cap)
        annual_cost = r.total_cost / span_years
        strat_costratio_samples.append(annual_cost / avg_cap * 100.0 if avg_cap > 0 else 0.0)

        bh_curve = _normalized_curve(bars.get(benchmark_symbol), run_start, end)
        if bh_curve is not None:
            bh_samples.append(float(bh_curve.iloc[-1] - 100.0))
            bh_dd_samples.append(_max_dd_pct(bh_curve))
        ew_curve = _equal_weight_curve(strategy, bars, run_start, end)
        if ew_curve is not None:
            ew_samples.append(float(ew_curve.iloc[-1] - 100.0))
            ew_dd_samples.append(_max_dd_pct(ew_curve))
        bw_curve = _basket_weight_curve(strategy, bars, run_start, end)
        if bw_curve is not None:
            bw_samples.append(float(bw_curve.iloc[-1] - 100.0))
            bw_dd_samples.append(_max_dd_pct(bw_curve))

    strat_stats = EnsembleStats(config_label, strat_samples, band_low, band_high)
    benchmarks = [
        EnsembleStats("SPY al-tut", bh_samples, band_low, band_high),
        EnsembleStats("Eşit-ağırlık evren", ew_samples, band_low, band_high),
        EnsembleStats("Sepet-ağırlıklı evren", bw_samples, band_low, band_high),
    ]
    benchmark_maxdd = [
        EnsembleStats("SPY al-tut", bh_dd_samples, band_low, band_high),
        EnsembleStats("Eşit-ağırlık evren", ew_dd_samples, band_low, band_high),
        EnsembleStats("Sepet-ağırlıklı evren", bw_dd_samples, band_low, band_high),
    ]

    # Tasarım sağlığı: bant genişliği medyanın ±health_pct'inden geniş mi?
    threshold = 2.0 * (health_pct / 100.0) * abs(strat_stats.median)
    health_ok = strat_stats.band_width <= threshold if threshold > 0 else False

    return EnsembleReport(
        config_label=config_label, window=(str(start), str(end)), runs=runs,
        strategy_stats=strat_stats, benchmarks=benchmarks,
        health_ok=health_ok, health_threshold=threshold, health_band_pct=health_pct,
        strategy_maxdd=EnsembleStats(config_label, strat_dd_samples, band_low, band_high),
        strategy_trades=EnsembleStats(config_label, strat_trade_samples, band_low, band_high),
        strategy_cost=EnsembleStats(config_label, strat_cost_samples, band_low, band_high),
        benchmark_maxdd=benchmark_maxdd,
        strategy_avg_capital=EnsembleStats(config_label, strat_avgcap_samples, band_low, band_high),
        strategy_cost_ratio_pct=EnsembleStats(config_label, strat_costratio_samples, band_low, band_high),
    )


# ----------------------------------------------------------------------
#  Markdown render (bantsız rakam YOK — kabul kriteri)
# ----------------------------------------------------------------------
def _fmt(stats: EnsembleStats) -> str:
    """medyan [p_low, p_high] — her rakam bantla birlikte."""
    return f"%{stats.median:+.2f}  [%{stats.p_low:+.2f}, %{stats.p_high:+.2f}]"


def _fmt_dd(stats: Optional[EnsembleStats]) -> str:
    if stats is None or not stats.samples:
        return "—"
    return f"%{stats.median:.2f}  [%{stats.p_low:.2f}, %{stats.p_high:.2f}]"


def _fmt_count(stats: Optional[EnsembleStats]) -> str:
    if stats is None or not stats.samples:
        return "—"
    return f"{stats.median:.0f}  [{stats.p_low:.0f}, {stats.p_high:.0f}]"


def _fmt_cost(stats: Optional[EnsembleStats]) -> str:
    if stats is None or not stats.samples:
        return "—"
    return f"${stats.median:,.2f}  [${stats.p_low:,.2f}, ${stats.p_high:,.2f}]"


def render_report_md(report: EnsembleReport) -> str:
    lines: list[str] = []
    lines.append(f"### {report.config_label}")
    lines.append("")
    lines.append(f"- Pencere: **{report.window[0]} → {report.window[1]}**  "
                 f"({report.runs} koşuluk topluluk; bant [%{report.strategy_stats.band_low_pct}, "
                 f"%{report.strategy_stats.band_high_pct}])")
    lines.append("")
    lines.append("| Seri | Getiri (medyan + bant) | MaxDD (medyan + bant) | "
                 "İşlem sayısı (medyan + bant) | Toplam maliyet (medyan + bant) |")
    lines.append("|------|------------------------|------------------------|"
                 "------------------------------|--------------------------------|")
    lines.append(f"| **Strateji** | {_fmt(report.strategy_stats)} | {_fmt_dd(report.strategy_maxdd)} | "
                 f"{_fmt_count(report.strategy_trades)} | {_fmt_cost(report.strategy_cost)} |")
    dd_by_label = {b.label: b for b in report.benchmark_maxdd}
    for b in report.benchmarks:
        lines.append(f"| {b.label} | {_fmt(b)} | {_fmt_dd(dd_by_label.get(b.label))} | — | — |")
    lines.append("")
    lines.append(f"- Bant genişliği (p{report.strategy_stats.band_high_pct}−p"
                 f"{report.strategy_stats.band_low_pct}): "
                 f"**%{report.strategy_stats.band_width:.2f}** — {report.health_note}")
    lines.append("")
    return "\n".join(lines)
