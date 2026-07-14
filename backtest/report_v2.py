"""Standart topluluk raporu (Görev B.2) — tek komutla üretilir.

    python -m backtest.report_v2                 # tune penceresi (2016-2019)
    python -m backtest.report_v2 --window validate
    python -m backtest.report_v2 --start 2016-01-01 --end 2019-12-31

Aktif `config/strategy.yaml` konfigürasyonunu pertürbasyon topluluğuyla koşar
(bkz. backtest.ensemble), medyan + bant tablosunu ve tasarım-sağlığı satırını
`results/` altına markdown olarak yazar. Hiçbir tabloda bantsız getiri yoktur.

DÖNEM AYRIMI DİSİPLİNİ (CLAUDE.md): validate/final pencereleri geri döndürülemez.
Bu komut yalnız RAPOR üretir; parametre değiştirmez. validate/final penceresine
bakmak insan kararıdır — bu komut o pencerelerde çalıştırıldığında da tek koşuyla
sınırlıdır (aday konfig başına EN FAZLA BİR koşu kuralı çağıran kişinin sorumluluğunda).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.config import ROOT, Strategy
from backtest.ensemble import render_report_md, run_ensemble
from backtest.rotation_backtest import _load_real_bars

log = logging.getLogger("report_v2")
RESULTS_DIR = ROOT / "results"


def config_label(strategy: Strategy) -> str:
    rot = strategy.rotation
    reg = strategy.rotation_backtest.get("regime", {})
    regime = "rejim:açık" if reg.get("enabled") else "rejim:kapalı"
    return (f"{rot.get('score', 's1_technical')} · {rot.get('selection', 'per_basket')} · "
            f"N={rot.get('top_n', 6)} · {rot.get('frequency', 'monthly')} · {regime}")


def window_bounds(strategy: Strategy, name: str) -> tuple[str, str]:
    windows = strategy.rotation_backtest.get("windows", {})
    w = windows.get(name)
    if not w:
        raise SystemExit(f"Bilinmeyen pencere: {name!r}. Seçenekler: {list(windows)}")
    return str(w["start"]), str(w["end"])


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(description="Rotasyon topluluk raporu (Faz B / B.2)")
    parser.add_argument("--window", default="tune", choices=["tune", "validate", "final"],
                        help="Dönem penceresi (varsayılan: tune = 2016-2019)")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD (pencereyi geçersiz kılar)")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD (pencereyi geçersiz kılar)")
    parser.add_argument("--years", type=float, default=11.0, help="yfinance geçmiş uzunluğu")
    parser.add_argument("--no-write", action="store_true", help="dosyaya yazma, yalnız yazdır")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    strategy = Strategy.load()
    if args.start and args.end:
        start, end = args.start, args.end
        win_name = "custom"
    else:
        start, end = window_bounds(strategy, args.window)
        win_name = args.window

    if win_name in ("validate", "final"):
        log.warning("DİKKAT: '%s' penceresi dönem ayrımı disiplinine tabidir "
                    "(aday konfig başına EN FAZLA BİR koşu; CLAUDE.md).", win_name)

    log.info("Barlar yükleniyor (yfinance, ~%.0f yıl)...", args.years)
    bars = _load_real_bars(strategy.universe_symbols, args.years)
    log.info("%d sembol yüklendi. Topluluk koşuluyor...", len(bars))

    report = run_ensemble(strategy, bars, start=start, end=end, config_label=config_label(strategy))
    md = render_report_md(report)
    print("\n" + md)

    if not args.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = RESULTS_DIR / f"rotation_ensemble_{win_name}_{stamp}.md"
        header = (f"# Rotasyon topluluk raporu — {win_name} penceresi\n\n"
                  f"> Üretim: {stamp} · Konfig: `{config_label(strategy)}`\n"
                  f"> Dönem ayrımı disiplini (CLAUDE.md): bu rapor parametre değiştirmez.\n\n")
        path.write_text(header + md, encoding="utf-8")
        log.info("Rapor yazıldı: %s", path)


if __name__ == "__main__":
    main()
