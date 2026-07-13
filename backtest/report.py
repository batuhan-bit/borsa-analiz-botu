"""Faz 1 doğrulama raporu üretici (Görev 1.1 + 1.2 + 1.3).

Tek komutla şu koşuları yapar ve results/rapor.md'ye özet tablo yazar:
  1. Ana dönem (config'teki son lookback_years yıl): strateji (mevcut
     dondurulmuş config) + al-ve-tut kıyas çizgileri.
  2. 2016-2022 (out-of-sample; parametreler 2023+ verisine bakılarak
     ayarlandığı için): üç konfigürasyon varyantı —
       (a) trend filtresi kapalı (yönlü hacim ve R/R kapısı da kapalı),
       (b) yalnız trend filtresi açık,
       (c) trend + yönlü hacim + R/R kapısı (mevcut config)
     + aynı dönemin kıyas çizgileri.
  3. Rejim bazlı alt-rapor: config'teki regime_windows pencerelerinde
     strateji vs benchmark getirisi ve maksimum düşüşü.
  4. Görev 1.3 istatistikleri: işlem sayısı, işlem başına ortalama getiri,
     bootstrap %90 GA ve varyantlar arası gürültü uyarıları.

Kullanım:
    python -m backtest.report [--basket-limit N]
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime

import pandas as pd

from bot.config import ROOT, Settings

from .backtest import (
    BacktestResult,
    run_backtest,
    run_benchmarks,
    sample_noise_warning,
)
from .benchmark import BenchmarkResult
from .metrics import max_drawdown_pct

log = logging.getLogger("backtest.report")

REPORT_DIR = ROOT / "results"

# 2016-2022 out-of-sample dönemi (Görev 1.2). Parametreler 2023-2026'ya
# bakılarak ayarlandığı için bu pencere fiilen görülmemiş veridir.
OOS_START = "2016-01-01"
OOS_END = "2022-12-31"

VARIANTS = [
    ("(a) Trend filtresi kapalı", dict(disable_trend_filter=True,
                                       disable_volume_direction=True,
                                       disable_rr_gate=True)),
    ("(b) Trend filtresi açık", dict(disable_volume_direction=True,
                                     disable_rr_gate=True)),
    ("(c) Trend + yönlü hacim + R/R", {}),
]


def _fmt(v, plus: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}" if plus else f"{v:.2f}"


def _strategy_row(r: BacktestResult) -> str:
    ci = (f"[{_fmt(r.ci_low_pct)} … {_fmt(r.ci_high_pct)}]"
          if r.ci_low_pct is not None else "—")
    calmar = _fmt(r.calmar, plus=False)
    return (f"| {r.label} | {_fmt(r.total_return_pct)} | {_fmt(r.annualized_return_pct)} | "
            f"{r.max_drawdown_pct:.2f} | {r.sharpe:.2f} | {calmar} | "
            f"{r.num_closed_trades} | {_fmt(r.avg_trade_return_pct)} | {ci} |")


def _benchmark_row(b: BenchmarkResult) -> str:
    calmar = _fmt(b.calmar, plus=False)
    return (f"| {b.name} | {_fmt(b.total_return_pct)} | {_fmt(b.annualized_return_pct)} | "
            f"{b.max_drawdown_pct:.2f} | {b.sharpe:.2f} | {calmar} | — | — | — |")


TABLE_HEADER = (
    "| Konfigürasyon | Toplam % | Yıllık % | Maks DD % | Sharpe | Calmar "
    "| İşlem | Ort. işlem % | Toplam getiri %90 GA |\n"
    "|---|---|---|---|---|---|---|---|---|"
)


def _comparison_table(strategies: list[BacktestResult],
                      benchmarks: list[BenchmarkResult]) -> list[str]:
    lines = [TABLE_HEADER]
    lines += [_strategy_row(r) for r in strategies]
    lines += [_benchmark_row(b) for b in benchmarks]
    return lines


def _alpha_lines(strategies: list[BacktestResult],
                 benchmarks: list[BenchmarkResult]) -> list[str]:
    lines = []
    for r in strategies:
        parts = [f"{r.total_return_pct - b.total_return_pct:+.1f} puan vs {b.name}"
                 for b in benchmarks]
        lines.append(f"- **{r.label}** alfa: " + "; ".join(parts))
    return lines


def _coverage_section(r: BacktestResult) -> list[str]:
    lines = ["| Sepet | Dönem başında aktif | Sonradan katılan | Verisi yok |",
             "|---|---|---|---|"]
    for basket, cov in r.coverage.items():
        late = ", ".join(f"{s} ({d})" for s, d in sorted(cov["late_joiners"].items())) or "—"
        nodata = ", ".join(cov["no_data"]) or "—"
        lines.append(f"| {basket} | {cov['active_at_start']}/{cov['total']} | {late} | {nodata} |")
    return lines


def _window_stats(curve: pd.Series, ws: pd.Timestamp, we: pd.Timestamp):
    """Pencere içi toplam getiri (%) ve maks. düşüş (%). Veri yoksa (None, None)."""
    if curve is None or curve.empty:
        return None, None
    sl = curve.loc[(curve.index >= ws) & (curve.index <= we)]
    if len(sl) < 2:
        return None, None
    ret = (float(sl.iloc[-1]) / float(sl.iloc[0]) - 1) * 100.0
    return ret, max_drawdown_pct(sl)


def _regime_section(windows: list[dict], strategies: list[BacktestResult],
                    benchmarks: list[BenchmarkResult]) -> list[str]:
    lines = []
    for w in windows:
        ws, we = pd.Timestamp(w["start"]), pd.Timestamp(w["end"])
        lines.append(f"\n**{w['name']}** ({w['start']} → {w['end']})\n")
        lines.append("| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |")
        lines.append("|---|---|---|")
        for r in strategies:
            ret, dd = _window_stats(r.equity_curve, ws, we)
            lines.append(f"| {r.label} | {_fmt(ret)} | {_fmt(dd, plus=False)} |")
        for b in benchmarks:
            ret, dd = _window_stats(b.equity_curve, ws, we)
            lines.append(f"| {b.name} | {_fmt(ret)} | {_fmt(dd, plus=False)} |")
    return lines


def build_report(basket_limit: int | None = None) -> str:
    settings = Settings.load(strict=False)
    strat = settings.strategy
    lookback = strat.backtest["lookback_years"]
    boot_pct = int(float(strat.backtest.get("bootstrap", {}).get("confidence", 0.9)) * 100)

    # --- 1) Ana dönem: mevcut config + kıyas çizgileri ---
    log.info("Ana dönem (son %s yıl) koşuluyor...", lookback)
    main_run = run_backtest(settings, basket_limit=basket_limit,
                            label="Strateji (mevcut config)", verbose=False)
    main_bench = run_benchmarks(settings, basket_limit=basket_limit)

    # --- 2) 2016-2022 out-of-sample: üç varyant + kıyas çizgileri ---
    oos_runs: list[BacktestResult] = []
    for label, flags in VARIANTS:
        log.info("2016-2022 varyantı koşuluyor: %s", label)
        oos_runs.append(run_backtest(settings, basket_limit=basket_limit,
                                     start=OOS_START, end=OOS_END,
                                     label=label, verbose=False, **flags))
    oos_bench = run_benchmarks(settings, basket_limit=basket_limit,
                               start=OOS_START, end=OOS_END)

    # --- 3) Gürültü uyarıları (Görev 1.3) ---
    warnings = []
    for i in range(len(oos_runs)):
        for j in range(i + 1, len(oos_runs)):
            msg = sample_noise_warning(oos_runs[i], oos_runs[j])
            if msg:
                warnings.append(msg)

    # --- Markdown ---
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L: list[str] = []
    L.append("# Backtest Doğrulama Raporu — Faz 1 (Görev 1.1, 1.2, 1.3)")
    L.append(f"\n_Üretim: {now} · `python -m backtest.report` · "
             "strategy.yaml parametreleri DONDURULMUŞ (Faz 1 kuralı)_\n")

    L.append("## 1) Ana dönem: son 3 yıl (in-sample)")
    L.append(f"\nDönem: **{main_run.start} → {main_run.end}** · "
             f"Başlangıç sermayesi: ${main_run.initial_capital:,.0f} · "
             "Yalnızca teknik sinyaller (temel katman backtest dışı).\n")
    L += _comparison_table([main_run], main_bench)
    L.append("")
    L += _alpha_lines([main_run], main_bench)
    L.append("\n> Not: Evren bugünden geriye seçildiği için bu dönem hindsight bias "
             "içerir; benchmark aynı evreni kullandığından alfa kıyası yine de anlamlıdır. "
             "Parametreler bu döneme bakılarak ayarlandığı için bu tablo IN-SAMPLE'dır.")

    L.append("\n## 2) 2016-2022 dönemi (fiilen out-of-sample)")
    L.append("\nParametreler 2023-2026 verisine bakılarak ayarlandı; 2016-2022 "
             "görülmemiş veridir. Üç konfigürasyon varyantı, aynı dondurulmuş eşiklerle:\n")
    L += _comparison_table(oos_runs, oos_bench)
    L.append("")
    L += _alpha_lines(oos_runs, oos_bench)

    L.append(f"\n### İstatistiksel değerlendirme (bootstrap %{boot_pct} GA, Görev 1.3)")
    if warnings:
        L.append("")
        for w in warnings:
            L.append(f"- ⚠ {w}")
    else:
        L.append("\n- Varyant güven aralıkları ayrışıyor (çakışma yok).")

    L.append("\n### Kapsam raporu (Görev 1.2 politikası: sembol, verisi başladığı gün katılır)")
    L.append("")
    L += _coverage_section(oos_runs[-1])

    L.append("\n## 3) Rejim bazlı alt-rapor: ayı piyasalarında koruma")
    L.append("\nSoru: koruyucu özellikler (trend filtresi, yönlü hacim, R/R kapısı) "
             "düşüş rejimlerinde gerçekten koruyor mu? (2016-2022 koşularının "
             "pencere içi kesitleri)")
    windows = strat.backtest.get("regime_windows", [])
    L += _regime_section(windows, oos_runs, oos_bench)

    L.append("\n## Sınırlamalar (dürüstlük notları)")
    L.append("""
- **Evren önyargısı:** 60 sembol bugünden geriye seçildi (survivorship/hindsight
  bias). Benchmark aynı evreni kullandığı için alfa ölçümü bu önyargıyı büyük
  ölçüde nötrler, ama mutlak getiriler şişkin okunmalıdır.
- **Dolgu fiyatı:** Mevcut backtest sinyal günü kapanışından dolduruyor;
  ertesi-gün-açılış dolgusu ve komisyon/kayma Görev 2.1'de ele alınacak.
- **Temel katman backtest dışı:** Bu rapor yalnızca teknik sinyalleri ölçer;
  canlıdaki %35 ağırlıklı temel katman point-in-time test edilemedi (Görev 3.1).
- **Küçük örneklem:** İşlem sayıları düşük; GA'lar geniş. GA'ları çakışan
  konfigürasyonlar arasında üstünlük iddia edilemez.""")

    return "\n".join(L) + "\n"


def main() -> None:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Faz 1 doğrulama raporu")
    parser.add_argument("--basket-limit", type=int, default=None,
                        help="Her sepetten en fazla N sembol (hızlı deneme)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    report = build_report(basket_limit=args.basket_limit)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "rapor.md"
    out.write_text(report, encoding="utf-8")
    print(f"\nRapor yazıldı: {out}")


if __name__ == "__main__":
    main()
