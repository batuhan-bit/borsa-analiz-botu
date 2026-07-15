"""Küçük bütçe uyumu (Görev D.2) — $1.000 gerçeğinde ölçek cezasını görünür kıl.

Faz B KAZANAN konfigürasyonunu (results/competition_winner.json:
s2_momentum · per_basket · N=6 · biweekly · rejim kapalı) İKİ ayrı bütçe
mekaniğiyle aynı pencere üzerinde topluluk (B.2 altyapısı, 50 koşu) olarak koşar:

  - Standart: initial_capital $3.000, sabit komisyon $0, tam-sayı hisse.
  - Küçük:    initial_capital $1.000, sabit komisyon $1.50, kesirli hisse.
                (config: rotation_backtest.small_budget)

Sonuç yan yana raporlanır (getiri, MaxDD, işlem sayısı, toplam maliyet — hepsi
medyan + bant) ve ZORUNLU ek satır olarak "yıllık toplam maliyet / ortalama
sermaye" oranı gösterilir. Bu koşunun ASIL amacı bu oranı görünür kılmaktır:
$1.50 sabit ücret ~$167'lik pozisyonda tek yön ~%0.9'dur, küçük bütçede maliyet
sürüklemesi standartın kat kat üstüne çıkar.

DÖNEM AYRIMI DİSİPLİNİ (CLAUDE.md): Bu bir DOĞRULAMA/ÖLÇÜM koşusudur, parametre
SEÇMEZ. Kazananın hiçbir rotasyon parametresine dokunulmaz (aşağıdaki bekçi
kontrolü bunu zorlar); yalnız bütçe mekaniği (sermaye/komisyon/kesirlilik)
değişir. Final penceresine "yeni bir bakış" DEĞİLDİR: aynı donmuş kazanan config,
zaten incelenmiş final penceresinde, ölçüm sütunu eklemek için deterministik
biçimde yeniden koşulur (bkz. competition_final.md'ye MaxDD/maliyet sütunu
eklenirken uygulanan aynı emsal). Getiri sayıları hiçbir parametre kararına
girdi DEĞİLDİR.

    python -m backtest.small_budget                 # final penceresi (varsayılan)
    python -m backtest.small_budget --window tune
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from bot.config import ROOT, Strategy
from backtest.ensemble import EnsembleReport, EnsembleStats, run_ensemble, _fmt, _fmt_dd, _fmt_count, _fmt_cost
from backtest.rotation_backtest import _load_real_bars

log = logging.getLogger("small_budget")
RESULTS_DIR = ROOT / "results"
WINNER_PATH = RESULTS_DIR / "competition_winner.json"


def _assert_winner_config(strategy: Strategy) -> dict:
    """Dönem-ayrımı bekçisi: aktif rotasyon config'i Faz B kazananıyla BİREBİR mi?

    Kazananın parametreleri yeniden doğrulama yapılmadan değişmişse bu koşu
    anlamsızdır (küçük bütçe kıyası donmuş kazanan üzerinde yapılır). test_live_config
    ile aynı ruhta; burada koşu-zamanı da doğrularız ki yanlış config'le rapor üretilmesin.
    """
    winner = json.loads(WINNER_PATH.read_text(encoding="utf-8"))["winner"]
    rot = strategy.rotation
    reg = strategy.rotation_backtest.get("regime", {})
    active = {
        "score": rot.get("score"),
        "selection": rot.get("selection"),
        "top_n": int(rot.get("top_n", 0)),
        "frequency": rot.get("frequency"),
        "regime": bool(reg.get("enabled", False)),
    }
    expected = {
        "score": winner["score"], "selection": winner["selection"],
        "top_n": int(winner["top_n"]), "frequency": winner["frequency"],
        "regime": bool(winner["regime"]),
    }
    if active != expected:
        raise SystemExit(
            "Aktif rotasyon config'i Faz B kazananıyla eşleşmiyor — küçük bütçe "
            f"koşusu DURDURULDU (dönem ayrımı).\n  aktif:   {active}\n  kazanan: {expected}"
        )
    return active


def _with_small_budget(base: Strategy) -> Strategy:
    """Kazananın rotasyon ayarlarına DOKUNMADAN yalnız bütçe mekaniğini değiştir."""
    sb = base.rotation_backtest.get("small_budget", {})
    if not sb:
        raise SystemExit("config: rotation_backtest.small_budget bulunamadı (Görev D.2).")
    raw = copy.deepcopy(base.raw)
    bt = raw.setdefault("rotation_backtest", {})
    bt["initial_capital"] = sb["initial_capital"]
    bt["commission_fixed_usd"] = sb["commission_fixed_usd"]
    bt["fractional_shares"] = sb["fractional_shares"]
    return Strategy(raw=raw, universe=copy.deepcopy(base.universe))


def _window_bounds(strategy: Strategy, name: str) -> tuple[str, str]:
    w = strategy.rotation_backtest.get("windows", {}).get(name)
    if not w:
        raise SystemExit(f"Bilinmeyen pencere: {name!r}")
    return str(w["start"]), str(w["end"])


def _fmt_ratio(stats: EnsembleStats | None) -> str:
    if stats is None or not stats.samples:
        return "—"
    return f"%{stats.median:.2f}  [%{stats.p_low:.2f}, %{stats.p_high:.2f}]"


def render_comparison_md(std: EnsembleReport, small: EnsembleReport,
                         std_label: str, small_label: str) -> str:
    """İki koşuyu yan yana + zorunlu maliyet/sermaye oranı satırı (bantsız rakam yok)."""
    lines: list[str] = []
    lines.append(f"- Pencere: **{std.window[0]} → {std.window[1]}**  "
                 f"({std.runs} koşuluk topluluk; bant [%{std.strategy_stats.band_low_pct}, "
                 f"%{std.strategy_stats.band_high_pct}])")
    lines.append("- Konfig (ORTAK, donmuş Faz B kazananı): "
                 f"`{std.config_label}` — yalnız bütçe mekaniği değişir.")
    lines.append("")
    lines.append(f"| Ölçüt (medyan + bant) | {std_label} | {small_label} |")
    lines.append("|------------------------|" + "-" * len(std_label) + "|" + "-" * len(small_label) + "|")
    lines.append(f"| Getiri | {_fmt(std.strategy_stats)} | {_fmt(small.strategy_stats)} |")
    lines.append(f"| MaxDD | {_fmt_dd(std.strategy_maxdd)} | {_fmt_dd(small.strategy_maxdd)} |")
    lines.append(f"| İşlem sayısı | {_fmt_count(std.strategy_trades)} | {_fmt_count(small.strategy_trades)} |")
    lines.append(f"| Toplam maliyet | {_fmt_cost(std.strategy_cost)} | {_fmt_cost(small.strategy_cost)} |")
    lines.append(f"| Ortalama sermaye | {_fmt_cost(std.strategy_avg_capital)} | {_fmt_cost(small.strategy_avg_capital)} |")
    lines.append(f"| **Yıllık maliyet / ort. sermaye** | "
                 f"**{_fmt_ratio(std.strategy_cost_ratio_pct)}** | "
                 f"**{_fmt_ratio(small.strategy_cost_ratio_pct)}** |")
    lines.append("")
    # Sürükleme farkı (medyan oranlar) — tek cümlelik okunur özet
    r_std = std.strategy_cost_ratio_pct.median if std.strategy_cost_ratio_pct else 0.0
    r_small = small.strategy_cost_ratio_pct.median if small.strategy_cost_ratio_pct else 0.0
    factor = (r_small / r_std) if r_std > 0 else 0.0
    lines.append(f"> **Maliyet sürüklemesi:** küçük bütçede yıllık maliyet/sermaye oranı "
                 f"medyan **%{r_small:.2f}**, standartta **%{r_std:.2f}** — "
                 f"küçük bütçe **{factor:.2f}×** daha ağır maliyet sürüklemesi taşır. "
                 f"Kaynak: $1.50 sabit ücret küçük pozisyonda (~$125-200) oransal olarak büyür.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(description="Küçük bütçe uyumu topluluk kıyası (Faz D / D.2)")
    parser.add_argument("--window", default="final", choices=["tune", "validate", "final"],
                        help="Dönem penceresi (varsayılan: final = kazananın standart raporuyla aynı pencere)")
    parser.add_argument("--years", type=float, default=11.0, help="yfinance geçmiş uzunluğu")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    strategy = Strategy.load()
    active = _assert_winner_config(strategy)
    log.info("Kazanan config doğrulandı: %s", active)

    small_strategy = _with_small_budget(strategy)
    start, end = _window_bounds(strategy, args.window)

    from backtest.report_v2 import config_label
    label = config_label(strategy)
    std_cap = int(strategy.rotation_backtest.get("initial_capital", 3000))
    small_cap = int(small_strategy.rotation_backtest.get("initial_capital", 1000))
    std_label = f"Standart (${std_cap:,}, sabit $0, tam hisse)"
    small_label = f"Küçük (${small_cap:,}, sabit $1.50, kesirli)"

    log.info("Barlar yükleniyor (yfinance, ~%.0f yıl)...", args.years)
    bars = _load_real_bars(strategy.universe_symbols, args.years)
    log.info("%d sembol yüklendi. İki topluluk koşuluyor (%s penceresi)...", len(bars), args.window)

    std_report = run_ensemble(strategy, bars, start=start, end=end, config_label=label)
    small_report = run_ensemble(small_strategy, bars, start=start, end=end, config_label=label)

    md = render_comparison_md(std_report, small_report, std_label, small_label)
    print("\n" + md)

    if not args.no_write:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        header = (
            f"# Küçük bütçe uyumu — $1.000 gerçeği (Görev D.2)\n\n"
            f"> Üretim: {stamp} · Pencere: **{args.window}** ({start} → {end})\n"
            f"> Konfig (ORTAK): `{label}` — Faz B kazananı, donmuş.\n"
            f"> **Dönem ayrımı (CLAUDE.md):** ölçüm koşusu; parametre SEÇMEZ. Kazananın\n"
            f"> rotasyon ayarları AYNEN kullanıldı (koşu-zamanı bekçisi doğruladı); yalnız\n"
            f"> bütçe mekaniği (sermaye/komisyon/kesirlilik) değişti. Getiri sayıları\n"
            f"> hiçbir parametre kararına girdi değildir.\n\n"
        )
        path = RESULTS_DIR / "small_budget_1000.md"
        path.write_text(header + md, encoding="utf-8")
        log.info("Rapor yazıldı: %s", path)


if __name__ == "__main__":
    main()
