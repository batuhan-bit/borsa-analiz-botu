"""Konfigürasyon yarışması (Görev B.3) — dönem ayrımı disipliniyle.

DÖNEM AYRIMI DİSİPLİNİ (CLAUDE.md — İHLAL EDİLEMEZ):
  1. Izgara YALNIZ **tune** (2016-2019) penceresinde koşulur ve karşılaştırılır.
  2. tune'dan EN FAZLA `max_candidates` aday seçilir.
  3. Adaylar **validate** (2020-2022) penceresinde BİRER kez doğrulanır.
  4. Doğrulamayı geçen TEK konfig, nihai raporda **final** (2023-2026)'ya BİR kez bakar.

Bu akış üç AYRI faza bölünmüştür (`--phase tune|validate|final`); her faz kararını
diskteki bir devir dosyasına (`results/competition_*.json`) yazar ve bir sonraki
faz onu okur. Böylece "hangi karar hangi pencereden ÖNCE verildi" hem raporda hem
commit geçmişinde okunur; bir fazın çıktısına bakıp önceki fazın parametresini
değiştirmek bu yapıda MÜMKÜN DEĞİLDİR (faz sınırı = commit sınırı).

Izgara ekseni: skor (S1/S2) · seçim (per_basket/global_top_n) · N (6/8) ·
ritim (aylık/iki haftalık) · rejim anahtarı (açık/kapalı). Eksenler config'ten.
"""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Mapping

import pandas as pd

from bot.config import ROOT, Strategy
from backtest.ensemble import EnsembleReport, render_report_md, run_ensemble

log = logging.getLogger("competition")
RESULTS_DIR = ROOT / "results"


# ----------------------------------------------------------------------
#  Izgara noktası
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class GridPoint:
    score: str
    selection: str
    top_n: int
    frequency: str
    regime: bool

    @property
    def label(self) -> str:
        return (f"{self.score}·{self.selection}·N={self.top_n}·{self.frequency}·"
                f"rejim{'A' if self.regime else 'K'}")

    def apply(self, base: Strategy) -> Strategy:
        """Bu ızgara noktasını uygulayan YENİ bir Strategy üret (base değişmez)."""
        raw = copy.deepcopy(base.raw)
        raw.setdefault("rotation", {}).update(
            {"score": self.score, "selection": self.selection,
             "top_n": self.top_n, "frequency": self.frequency}
        )
        raw.setdefault("rotation_backtest", {}).setdefault("regime", {})["enabled"] = self.regime
        return Strategy(raw=raw, universe=copy.deepcopy(base.universe))


def build_grid(strategy: Strategy) -> list[GridPoint]:
    """config'teki eksenlerin kartezyen çarpımından ızgara noktalarını üret."""
    grid = strategy.rotation_backtest.get("competition", {}).get("grid", {})
    scores = grid.get("score", ["s1_technical"])
    selections = grid.get("selection", ["per_basket"])
    top_ns = grid.get("top_n", [6])
    freqs = grid.get("frequency", ["monthly"])
    regimes = grid.get("regime", [False])
    points = [
        GridPoint(sc, sel, int(n), fr, bool(rg))
        for sc, sel, n, fr, rg in product(scores, selections, top_ns, freqs, regimes)
    ]
    return points


# ----------------------------------------------------------------------
#  Faz koşuları
# ----------------------------------------------------------------------
def _window_bounds(strategy: Strategy, name: str) -> tuple[str, str]:
    w = strategy.rotation_backtest.get("windows", {}).get(name)
    if not w:
        raise SystemExit(f"Bilinmeyen pencere: {name!r}")
    return str(w["start"]), str(w["end"])


def run_config_ensemble(
    base: Strategy, point: GridPoint, bars: Mapping[str, pd.DataFrame],
    window: str,
) -> EnsembleReport:
    """Tek bir ızgara noktasını verilen pencerede topluluk olarak koş."""
    strat = point.apply(base)
    start, end = _window_bounds(base, window)
    return run_ensemble(strat, bars, start=start, end=end, config_label=point.label)


def run_tune_grid(
    base: Strategy, bars: Mapping[str, pd.DataFrame],
) -> list[tuple[GridPoint, EnsembleReport]]:
    """Izgaranın tamamını TUNE penceresinde koş (serbestçe tekrarlanabilir)."""
    out = []
    points = build_grid(base)
    for i, p in enumerate(points, start=1):
        log.info("[%d/%d] %s", i, len(points), p.label)
        out.append((p, run_config_ensemble(base, p, bars, "tune")))
    return out


def select_candidates(
    ranked: list[tuple[GridPoint, EnsembleReport]], max_candidates: int,
) -> list[tuple[GridPoint, EnsembleReport]]:
    """Adayları seç: önce topluluk medyanı (yüksek), eşitlikte dar bant.

    Nihai insan kararına (rejim davranışı dahil) girdi olacak sıralamayı üretir;
    yapı EN FAZLA `max_candidates` aday döndürür (dönem ayrımı: fazla aday yasak).
    """
    order = sorted(
        ranked,
        key=lambda pr: (-pr[1].strategy_stats.median, pr[1].strategy_stats.band_width, pr[0].label),
    )
    return order[:max_candidates]


# ----------------------------------------------------------------------
#  Devir dosyaları (faz sınırı = karar sınırı)
# ----------------------------------------------------------------------
def _save_json(name: str, data: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_json(name: str) -> dict:
    path = RESULTS_DIR / name
    if not path.exists():
        raise SystemExit(f"Devir dosyası yok: {path}. Önceki fazı çalıştırın.")
    return json.loads(path.read_text(encoding="utf-8"))


def _stats_row(rep: EnsembleReport) -> dict:
    s = rep.strategy_stats
    return {"median": round(s.median, 2), "p_low": round(s.p_low, 2),
            "p_high": round(s.p_high, 2), "band_width": round(s.band_width, 2),
            "health_ok": rep.health_ok}


# ----------------------------------------------------------------------
#  Markdown render (üç pencere ayrı bölümlerde)
# ----------------------------------------------------------------------
def render_grid_table(ranked: list[tuple[GridPoint, EnsembleReport]]) -> str:
    lines = ["| Konfig | Medyan + bant | Bant gen. | Sağlık |",
             "|--------|---------------|-----------|--------|"]
    order = sorted(ranked, key=lambda pr: -pr[1].strategy_stats.median)
    for p, rep in order:
        s = rep.strategy_stats
        lines.append(f"| {p.label} | %{s.median:+.2f} [%{s.p_low:+.2f}, %{s.p_high:+.2f}] "
                     f"| %{s.band_width:.2f} | {'✓' if rep.health_ok else '⚠️'} |")
    return "\n".join(lines)


# ----------------------------------------------------------------------
#  CLI — fazlı, disiplin korumalı
# ----------------------------------------------------------------------
def main() -> None:
    import argparse
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(description="Konfig yarışması (Faz B / B.3)")
    parser.add_argument("--phase", required=True, choices=["tune", "validate", "final"])
    parser.add_argument("--years", type=float, default=11.0)
    parser.add_argument("--i-understand-window-discipline", action="store_true",
                        help="validate/final için zorunlu: dönem ayrımı disiplinini onayla")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from backtest.rotation_backtest import _load_real_bars
    base = Strategy.load()

    if args.phase in ("validate", "final") and not args.i_understand_window_discipline:
        raise SystemExit(
            f"'{args.phase}' penceresi dönem ayrımı disiplinine tabidir (CLAUDE.md).\n"
            "Bu pencereye BİR kez bakılır ve sonucuna göre parametre DEĞİŞTİRİLMEZ.\n"
            "Devam etmek için --i-understand-window-discipline bayrağını ekleyin."
        )

    log.info("Barlar yükleniyor (yfinance, ~%.0f yıl)...", args.years)
    bars = _load_real_bars(base.universe_symbols, args.years)
    log.info("%d sembol yüklendi.", len(bars))

    if args.phase == "tune":
        _phase_tune(base, bars)
    elif args.phase == "validate":
        _phase_validate(base, bars)
    else:
        _phase_final(base, bars)


def _phase_tune(base: Strategy, bars) -> None:
    ranked = run_tune_grid(base, bars)
    max_c = int(base.rotation_backtest.get("competition", {}).get("max_candidates", 2))
    candidates = select_candidates(ranked, max_c)

    md = ["# Konfig yarışması — TUNE penceresi (2016-2019)", "",
          "> Parametre ayarı YALNIZ bu pencerede yapılır (CLAUDE.md).", "",
          "## Izgara sonuçları (topluluk medyanı sırasıyla)", "",
          render_grid_table(ranked), "",
          f"## Seçilen adaylar (en fazla {max_c})", ""]
    for p, rep in candidates:
        md.append(f"- **{p.label}** — {render_report_md(rep).splitlines()[0]} "
                  f"medyan %{rep.strategy_stats.median:+.2f}, bant %{rep.strategy_stats.band_width:.2f}")
    _save_json("competition_candidates.json", {
        "phase": "tune",
        "candidates": [asdict(p) | {"tune": _stats_row(rep)} for p, rep in candidates],
    })
    (RESULTS_DIR / "competition_tune.md").write_text("\n".join(md), encoding="utf-8")
    log.info("TUNE tamam. Adaylar: %s", [p.label for p, _ in candidates])
    log.info("Sıradaki: insan onayıyla `--phase validate --i-understand-window-discipline`.")


def _phase_validate(base: Strategy, bars) -> None:
    handoff = _load_json("competition_candidates.json")
    results = []
    for c in handoff["candidates"]:
        p = GridPoint(c["score"], c["selection"], c["top_n"], c["frequency"], c["regime"])
        rep = run_config_ensemble(base, p, bars, "validate")   # aday başına BİR koşu
        results.append((p, rep))
        log.info("VALIDATE %s -> medyan %%%.2f", p.label, rep.strategy_stats.median)
    # Doğrulamayı geçen tek konfig: SPY'ı topluluk-medyanında geçen, en yüksek medyan
    passed = [(p, rep) for p, rep in results
              if rep.strategy_stats.median > _spy_median(rep)]
    winner = max(passed, key=lambda pr: pr[1].strategy_stats.median, default=None)

    md = ["# Konfig yarışması — VALIDATE penceresi (2020-2022)", "",
          "> Aday başına BİR koşu; sonuca göre parametre DEĞİŞTİRİLMEZ (CLAUDE.md).", ""]
    for p, rep in results:
        md.append(render_report_md(rep))
    if winner:
        md.append(f"\n## Kazanan: **{winner[0].label}** (final penceresine BİR kez bakacak)")
    else:
        md.append("\n## Kazanan YOK — hiçbir aday SPY'ı topluluk-medyanında geçemedi. "
                  "Tasarım masasına dönülür (Faz C'ye geçilmez).")
    (RESULTS_DIR / "competition_validate.md").write_text("\n".join(md), encoding="utf-8")
    _save_json("competition_winner.json",
               {"phase": "validate", "winner": asdict(winner[0]) if winner else None})
    log.info("VALIDATE tamam. Kazanan: %s", winner[0].label if winner else "YOK")


def _phase_final(base: Strategy, bars) -> None:
    handoff = _load_json("competition_winner.json")
    if not handoff.get("winner"):
        raise SystemExit("Kazanan yok — final penceresine bakılmaz (validate'i geçen konfig yok).")
    c = handoff["winner"]
    p = GridPoint(c["score"], c["selection"], c["top_n"], c["frequency"], c["regime"])
    rep = run_config_ensemble(base, p, bars, "final")          # TEK koşu, TEK bakış
    md = ["# Konfig yarışması — FINAL penceresi (2023-2026)", "",
          "> Nihai rapor: TEK konfig, TEK bakış (CLAUDE.md). İnsan değerlendirmesine sunulur.",
          "> ⏸ FAZ B SONUNDA DUR — Faz C kararı bu rapora bağlıdır.", "",
          render_report_md(rep)]
    (RESULTS_DIR / "competition_final.md").write_text("\n".join(md), encoding="utf-8")
    log.info("FINAL tamam. Rapor: results/competition_final.md")


def _spy_median(rep: EnsembleReport) -> float:
    for b in rep.benchmarks:
        if b.label == "SPY al-tut":
            return b.median
    return 0.0


if __name__ == "__main__":
    main()
