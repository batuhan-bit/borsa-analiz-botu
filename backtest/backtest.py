"""Backtesting scripti — stratejiyi son 3 yıllık veriyle doğrular.

Canlı motorla AYNI teknik skorlama mantığını (bot.signals.technical) geçmiş
veri üzerinde gün gün çalıştırır, pozisyon bazlı %20 stop-loss'u uygular ve
portföy performansını raporlar.

ÖNEMLİ SINIRLAMA: Backtest yalnızca TEKNİK sinyalleri kullanır. Alpha Vantage
temel verisi (haber duygusu, analist notları) geçmişe dönük / point-in-time
alınamadığı (ve 25/gün limitli olduğu) için temel katman backtest dışıdır.
Canlı çalışmada temel katman skora eklenir (ağırlık = fundamental.weight).

Veri kaynağı: yfinance (anahtar gerektirmez). Sonuçlar backtest/results/
altına yazılır (.gitignore'da).

Kullanım:
    python -m backtest.backtest
    python -m backtest.backtest --basket-limit 3   # her sepetten 3 sembol (hızlı)
"""
from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from bot.config import ROOT, Settings
from bot.models import Basket
from bot.risk.risk_manager import check_stop_loss
from bot.signals.levels import price_levels
from bot.signals.technical import indicator_frame, indicators_from_rows, technical_score

from .benchmark import BenchmarkResult, benchmark_suite
from .data import load_bars
from .metrics import (
    bootstrap_total_return_ci,
    cagr_pct,
    calmar_ratio,
    ci_overlap,
    max_drawdown_pct,
    sharpe_ratio,
)

log = logging.getLogger("backtest")

RESULTS_DIR = ROOT / "backtest" / "results"


def _build_signal_frame(
    df: pd.DataFrame, tech_cfg: dict, buy: float, sell: float,
    *, min_rr: float = 0.0, max_loss_pct: float = 20.0,
) -> pd.DataFrame:
    """Her gün için (close, score, decision) üret — canlı skorlama mantığıyla.

    min_rr > 0 ise BUY günlerinde R/R kapısı uygulanır (canlı motorla tutarlı).
    """
    frame = indicator_frame(df, tech_cfg)
    if frame.empty:
        return pd.DataFrame()

    rows = []
    prev = None
    for i, (_, row) in enumerate(frame.iterrows()):
        ind = indicators_from_rows(row, prev)
        score, _ = technical_score(ind, tech_cfg)
        decision = "BUY" if score >= buy else "SELL" if score <= sell else "HOLD"
        if decision == "BUY" and min_rr > 0 and i >= 20:
            lv = price_levels(df.iloc[: i + 1], float(row["close"]), max_loss_pct=max_loss_pct)
            rr = lv.get("risk_reward")
            if rr is not None and rr < min_rr:
                decision = "HOLD"
        rows.append((row["close"], score, decision))
        prev = row
    return pd.DataFrame(rows, index=frame.index, columns=["close", "score", "decision"])


# ----------------------------------------------------------------------
#  Simülasyon
# ----------------------------------------------------------------------
@dataclass
class Position:
    shares: float
    entry_price: float
    entry_date: pd.Timestamp
    basket: Basket


@dataclass
class Trade:
    symbol: str
    basket: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    return_pct: float
    reason: str


@dataclass
class BacktestResult:
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    num_trades: int
    start: str
    end: str
    target_quarterly_pct: float = 6.5
    benchmark_return_pct: Optional[float] = None
    sharpe: float = 0.0
    calmar: Optional[float] = None
    # İstatistiksel dürüstlük (Görev 1.3)
    num_closed_trades: int = 0
    avg_trade_return_pct: Optional[float] = None
    ci_low_pct: Optional[float] = None      # toplam getiri bootstrap GA alt sınırı
    ci_high_pct: Optional[float] = None     # üst sınırı
    ci_confidence: float = 0.90
    label: str = "Strateji"
    coverage: dict = field(default_factory=dict, repr=False)
    equity_curve: pd.Series = field(default=None, repr=False)
    trades: list[Trade] = field(default_factory=list, repr=False)


def _resolve_window(strat, start: Optional[str], end: Optional[str]):
    """Backtest penceresini çöz (Görev 1.2).

    Dönüş: (range_mode, start_ts, end_ts, fetch_start).
    start/end argümanları config'teki backtest.start_date/end_date'i ezer;
    hiçbiri yoksa range_mode=False (eski davranış: son lookback_years yıl).
    """
    bt = strat.backtest
    start = start or bt.get("start_date")
    end = end or bt.get("end_date")
    if not start and not end:
        return False, None, None, None
    years = bt["lookback_years"]
    end_ts = pd.Timestamp(end) if end else pd.Timestamp(pd.Timestamp.today().date())
    start_ts = pd.Timestamp(start) if start else end_ts - pd.Timedelta(days=int(years * 365))
    warmup = int(bt.get("warmup_days", 400))
    fetch_start = start_ts - pd.Timedelta(days=warmup)
    return True, start_ts, end_ts, fetch_start


def run_backtest(
    settings: Optional[Settings] = None,
    *,
    basket_limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    disable_trend_filter: bool = False,
    disable_volume_direction: bool = False,
    disable_rr_gate: bool = False,
    label: str = "Strateji",
    verbose: bool = True,
) -> BacktestResult:
    """Backtest çalıştır ve özet metrikleri döndür.

    start/end (YYYY-MM-DD): dönem sınırları (Görev 1.2). Verilirse göstergeler
    dönem başından warmup_days önce başlayan veriyle ısıtılır, işlem yalnızca
    pencere içinde yapılır. disable_* anahtarları koruyucu özellikleri geçici
    kapatır (konfigürasyon varyantları için — strategy.yaml'a DOKUNMAZ).
    """
    import copy

    settings = settings or Settings.load(strict=False)
    strat = settings.strategy
    tech_cfg = copy.deepcopy(strat.technical)
    years = strat.backtest["lookback_years"]
    initial = float(strat.backtest["initial_capital"])
    stop_loss_pct = strat.risk["position_stop_loss_pct"]
    buy = strat.raw.get("signals", {}).get("buy_threshold", 0.30)
    sell = strat.raw.get("signals", {}).get("sell_threshold", -0.30)
    min_rr = strat.raw.get("signals", {}).get("min_risk_reward", 0.0)
    positions_per_basket = strat.portfolio["positions_per_basket"]

    if disable_trend_filter:
        tech_cfg["trend_filter"] = {"price_vs_ma_long": 0.0, "price_vs_ma_short": 0.0}
    if disable_volume_direction:
        tech_cfg["volume_confirmation"]["direction_weight"] = 0.0
    if disable_rr_gate:
        min_rr = 0.0

    range_mode, start_ts, end_ts, fetch_start = _resolve_window(strat, start, end)

    # Sembol -> sepet ve sepet başına pozisyon büyüklüğü oranı
    symbol_basket: dict[str, Basket] = {}
    per_pos_frac: dict[Basket, float] = {}
    universe: dict[Basket, list[str]] = {}
    for name, cfg in strat.baskets.items():
        basket = Basket(name)
        syms = list(cfg.get("universe", []))
        if basket_limit:
            syms = syms[:basket_limit]
        universe[basket] = syms
        per_pos_frac[basket] = cfg["allocation_pct"] / 100.0 / positions_per_basket
        for s in syms:
            symbol_basket[s] = basket

    # Her sembol için sinyal çerçevesi (veri yoksa atla). Politika (Görev 1.2):
    # verisi dönemin ortasında başlayan sembol, verisi başladığı gün evrene
    # katılır; öncesinde yok sayılır. Kapsam raporu sepet bazında tutulur.
    sig_frames: dict[str, pd.DataFrame] = {}
    first_bar: dict[str, pd.Timestamp] = {}
    skipped: dict[Basket, list[str]] = {b: [] for b in universe}
    for basket, syms in universe.items():
        for sym in syms:
            if range_mode:
                df = load_bars(sym, start=str(fetch_start.date()), end=str(end_ts.date()))
            else:
                df = load_bars(sym, years=years)
            if df.empty or len(df) < tech_cfg["moving_averages"]["long"] + 5:
                log.warning("Yetersiz veri, atlanıyor: %s", sym)
                skipped[basket].append(sym)
                continue
            sf = _build_signal_frame(df, tech_cfg, buy, sell,
                                     min_rr=min_rr, max_loss_pct=stop_loss_pct)
            if not sf.empty:
                sig_frames[sym] = sf
                first_bar[sym] = df.index[0]
            else:
                skipped[basket].append(sym)
    if verbose:
        log.info("%d sembol yüklendi.", len(sig_frames))
    if not sig_frames:
        raise RuntimeError("Hiçbir sembol için veri yüklenemedi — dönem/ağ kontrol edin.")

    # Ana takvim = tüm sembollerin tarih birleşimi; range modunda pencereyle sınırlı
    all_dates = sorted(set().union(*[set(sf.index) for sf in sig_frames.values()]))
    if range_mode:
        all_dates = [d for d in all_dates if start_ts <= d <= end_ts]
    if not all_dates:
        raise RuntimeError("Seçilen pencerede işlem günü yok.")

    # Kapsam raporu: dönem başında kaç sembol aktifti, kim sonradan katıldı
    window_start = all_dates[0]
    coverage: dict[str, dict] = {}
    for basket, syms in universe.items():
        active, late = [], {}
        for sym in syms:
            fb = first_bar.get(sym)
            if fb is None:
                continue
            if fb <= window_start + pd.Timedelta(days=10):
                active.append(sym)
            else:
                join = next((d for d in sig_frames[sym].index if d >= window_start), None)
                late[sym] = str(pd.Timestamp(join).date()) if join is not None else "-"
        coverage[basket.value] = {
            "total": len(syms),
            "active_at_start": len(active),
            "late_joiners": late,
            "no_data": skipped[basket],
        }

    positions: dict[str, Position] = {}
    cash = initial
    last_price: dict[str, float] = {}
    trades: list[Trade] = []
    equity_dates, equity_vals = [], []

    def lookup(sym: str, dt) -> Optional[pd.Series]:
        sf = sig_frames.get(sym)
        if sf is None or dt not in sf.index:
            return None
        return sf.loc[dt]

    def close_position(sym: str, price: float, dt, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(sym)
        proceeds = pos.shares * price
        cash += proceeds
        pnl = proceeds - pos.shares * pos.entry_price
        ret = (price - pos.entry_price) / pos.entry_price * 100.0
        trades.append(Trade(
            symbol=sym, basket=pos.basket.value,
            entry_date=str(pos.entry_date.date()), exit_date=str(pd.Timestamp(dt).date()),
            entry_price=round(pos.entry_price, 2), exit_price=round(price, 2),
            shares=round(pos.shares, 4), pnl=round(pnl, 2), return_pct=round(ret, 2),
            reason=reason,
        ))

    for dt in all_dates:
        # Fiyatları güncelle
        for sym in sig_frames:
            row = lookup(sym, dt)
            if row is not None:
                last_price[sym] = float(row["close"])

        # 1) Stop-loss ve SELL sinyalleri (açık pozisyonlar)
        for sym in list(positions.keys()):
            price = last_price.get(sym)
            if price is None:
                continue
            pos = positions[sym]
            sl = check_stop_loss(sym, pos.basket, pos.entry_price, price, stop_loss_pct)
            row = lookup(sym, dt)
            if sl is not None:
                close_position(sym, price, dt, "stop_loss")
            elif row is not None and row["decision"] == "SELL":
                close_position(sym, price, dt, "signal_sell")

        # 2) BUY: her sepette boş slotları en yüksek skorlu adaylarla doldur
        equity = cash + sum(positions[s].shares * last_price.get(s, positions[s].entry_price)
                            for s in positions)
        for basket, syms in universe.items():
            held = [s for s in positions if positions[s].basket == basket]
            slots = positions_per_basket - len(held)
            if slots <= 0:
                continue
            candidates = []
            for sym in syms:
                if sym in positions:
                    continue
                row = lookup(sym, dt)
                if row is not None and row["decision"] == "BUY":
                    candidates.append((sym, float(row["score"])))
            candidates.sort(key=lambda x: x[1], reverse=True)
            for sym, _score in candidates[:slots]:
                price = last_price.get(sym)
                if not price:
                    continue
                target_value = per_pos_frac[basket] * equity
                budget = min(target_value, cash)
                shares = math.floor(budget / price)
                if shares <= 0:
                    continue
                cash -= shares * price
                positions[sym] = Position(shares, price, pd.Timestamp(dt), basket)

        # Günlük özsermaye
        equity = cash + sum(positions[s].shares * last_price.get(s, positions[s].entry_price)
                            for s in positions)
        equity_dates.append(pd.Timestamp(dt))
        equity_vals.append(equity)

    # Kalan pozisyonları son fiyattan kapat
    for sym in list(positions.keys()):
        close_position(sym, last_price[sym], all_dates[-1], "backtest_end")

    equity_curve = pd.Series(equity_vals, index=equity_dates, name="equity")
    target = float(strat.portfolio["target_return_pct"])
    boot_cfg = strat.backtest.get("bootstrap", {}) or {}
    result = _metrics(
        equity_curve, trades, initial, years, sig_frames, target=target,
        bootstrap_samples=int(boot_cfg.get("samples", 10_000)),
        bootstrap_confidence=float(boot_cfg.get("confidence", 0.90)),
    )
    result.label = label
    result.coverage = coverage
    return result


def _metrics(equity: pd.Series, trades: list[Trade], initial: float, years: float,
             sig_frames: dict[str, pd.DataFrame], *, target: float = 6.5,
             bootstrap_samples: int = 10_000,
             bootstrap_confidence: float = 0.90) -> BacktestResult:
    final = float(equity.iloc[-1]) if not equity.empty else initial
    total_return = (final / initial - 1) * 100.0

    annualized = cagr_pct(equity) if len(equity) > 1 else 0.0
    max_dd = max_drawdown_pct(equity)

    closed = [t for t in trades if t.reason != "backtest_end"] or trades
    wins = [t for t in closed if t.pnl > 0]
    win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0

    # Görev 1.3: işlem başına ortalama getiri + toplam getirinin bootstrap GA'sı
    avg_trade = (sum(t.return_pct for t in closed) / len(closed)) if closed else None
    ci = bootstrap_total_return_ci(
        [t.pnl for t in closed], initial,
        samples=bootstrap_samples, confidence=bootstrap_confidence,
    )

    # Benchmark: SPY al-tut (varsa) — stratejinin işlem penceresiyle sınırlı
    benchmark = None
    spy = sig_frames.get("SPY")
    if spy is not None and len(spy) > 1 and not equity.empty:
        spy_close = spy["close"].loc[equity.index[0]: equity.index[-1]]
        if len(spy_close) > 1:
            benchmark = (spy_close.iloc[-1] / spy_close.iloc[0] - 1) * 100.0

    return BacktestResult(
        initial_capital=initial,
        final_equity=round(final, 2),
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(annualized, 2),
        max_drawdown_pct=round(max_dd, 2),
        win_rate_pct=round(win_rate, 1),
        num_trades=len(trades),
        start=str(equity.index[0].date()) if len(equity) else "-",
        end=str(equity.index[-1].date()) if len(equity) else "-",
        target_quarterly_pct=target,
        benchmark_return_pct=round(benchmark, 2) if benchmark is not None else None,
        sharpe=round(sharpe_ratio(equity), 2),
        calmar=(lambda c: round(c, 2) if c is not None else None)(calmar_ratio(equity)),
        num_closed_trades=len(closed),
        avg_trade_return_pct=round(avg_trade, 2) if avg_trade is not None else None,
        ci_low_pct=round(ci[0], 2) if ci else None,
        ci_high_pct=round(ci[1], 2) if ci else None,
        ci_confidence=bootstrap_confidence,
        equity_curve=equity,
        trades=trades,
    )


def _print_report(r: BacktestResult) -> None:
    print("\n" + "=" * 56)
    print("  BACKTEST SONUCU (yalnızca teknik sinyaller)")
    print("=" * 56)
    print(f"  Dönem                : {r.start} → {r.end}")
    print(f"  Başlangıç sermayesi  : ${r.initial_capital:,.0f}")
    print(f"  Bitiş özsermayesi    : ${r.final_equity:,.2f}")
    print(f"  Toplam getiri        : %{r.total_return_pct:+.2f}")
    print(f"  Yıllık getiri (CAGR) : %{r.annualized_return_pct:+.2f}")
    print(f"  Maks. düşüş (DD)     : %{r.max_drawdown_pct:.2f}")
    print(f"  Sharpe (rf=0)        : {r.sharpe:.2f}")
    if r.calmar is not None:
        print(f"  Calmar               : {r.calmar:.2f}")
    print(f"  Kazanma oranı        : %{r.win_rate_pct:.1f}  ({r.num_trades} işlem)")
    # Görev 1.3: ham getiri asla işlem sayısı ve güven aralığı olmadan sunulmaz
    if r.avg_trade_return_pct is not None:
        print(f"  İşlem başına ort.    : %{r.avg_trade_return_pct:+.2f}  ({r.num_closed_trades} kapanmış işlem)")
    if r.ci_low_pct is not None:
        pct = int(r.ci_confidence * 100)
        print(f"  Toplam getiri %{pct} GA : [%{r.ci_low_pct:+.2f} … %{r.ci_high_pct:+.2f}]"
              f"  (bootstrap, işlem örneklemesi)")
        if r.num_closed_trades < 30:
            print(f"  ⚠ Örneklem küçük ({r.num_closed_trades} işlem) — sonuçlar gürültüye açık.")
    if r.benchmark_return_pct is not None:
        print(f"  Benchmark (SPY al-tut): %{r.benchmark_return_pct:+.2f}")
    # Hedef: 3 ayda %15. Gerçekleşen çeyreklik-eşdeğer getiri ile karşılaştır.
    print("-" * 56)
    quarters = max((pd.Timestamp(r.end) - pd.Timestamp(r.start)).days / 91.25, 1e-9)
    realized_q = ((1 + r.total_return_pct / 100.0) ** (1 / quarters) - 1) * 100.0
    target = r.target_quarterly_pct
    verdict = "ULAŞILDI ✓" if realized_q >= target else "ULAŞILAMADI ✗"
    print(f"  Gerçekleşen çeyreklik getiri: %{realized_q:+.2f}  (hedef %{target:g}) → {verdict}")
    print("=" * 56 + "\n")


def sample_noise_warning(a: BacktestResult, b: BacktestResult) -> Optional[str]:
    """İki konfigürasyonun GA'ları çakışıyorsa uyarı metni döndür (Görev 1.3)."""
    overlap = ci_overlap(
        (a.ci_low_pct, a.ci_high_pct) if a.ci_low_pct is not None else None,
        (b.ci_low_pct, b.ci_high_pct) if b.ci_low_pct is not None else None,
    )
    if overlap is None:
        return (f"'{a.label}' vs '{b.label}': güven aralığı hesaplanamadı "
                f"(yetersiz işlem sayısı) — fark yorumlanamaz.")
    if overlap:
        return (f"'{a.label}' vs '{b.label}': güven aralıkları çakışıyor — "
                f"fark örneklem gürültüsünden ayırt edilemiyor.")
    return None


def _print_coverage(r: BacktestResult) -> None:
    """Sepet bazında kapsam raporu (Görev 1.2): dönem başında kaç sembol aktifti."""
    if not r.coverage:
        return
    print("  KAPSAM RAPORU (dönem başında aktif sembol / evren)")
    for basket, cov in r.coverage.items():
        print(f"  - {basket:16s}: {cov['active_at_start']}/{cov['total']} aktif", end="")
        if cov["late_joiners"]:
            joins = ", ".join(f"{s} ({d})" for s, d in sorted(cov["late_joiners"].items()))
            print(f"; sonradan katılan: {joins}", end="")
        if cov["no_data"]:
            print(f"; verisi yok: {', '.join(cov['no_data'])}", end="")
        print()
    print()


def comparison_rows(r: BacktestResult, benchmarks: list[BenchmarkResult]) -> list[dict]:
    """Strateji + kıyas çizgilerini tek tablo satırları halinde döndür (Görev 1.1)."""
    rows = [{
        "name": "Strateji",
        "total_return_pct": r.total_return_pct,
        "annualized_return_pct": r.annualized_return_pct,
        "max_drawdown_pct": r.max_drawdown_pct,
        "sharpe": r.sharpe,
        "calmar": r.calmar,
    }]
    for b in benchmarks:
        rows.append({
            "name": b.name,
            "total_return_pct": b.total_return_pct,
            "annualized_return_pct": b.annualized_return_pct,
            "max_drawdown_pct": b.max_drawdown_pct,
            "sharpe": b.sharpe,
            "calmar": b.calmar,
        })
    return rows


def _print_comparison(r: BacktestResult, benchmarks: list[BenchmarkResult]) -> None:
    print("  KIYAS TABLOSU (aynı dönem, aynı evren, al-ve-tut)")
    print("  " + "-" * 78)
    print(f"  {'':32s} {'Toplam%':>9s} {'Yıllık%':>9s} {'MaksDD%':>9s} {'Sharpe':>7s} {'Calmar':>7s}")
    for row in comparison_rows(r, benchmarks):
        calmar = f"{row['calmar']:.2f}" if row["calmar"] is not None else "-"
        print(f"  {row['name']:32s} {row['total_return_pct']:>+9.2f} "
              f"{row['annualized_return_pct']:>+9.2f} {row['max_drawdown_pct']:>9.2f} "
              f"{row['sharpe']:>7.2f} {calmar:>7s}")
    # Alfa: stratejinin kıyas çizgilerine göre farkı (toplam getiri üzerinden)
    for b in benchmarks:
        alpha = r.total_return_pct - b.total_return_pct
        print(f"  Alfa vs {b.name:41s}: {alpha:+.2f} puan")
    print("  " + "-" * 78 + "\n")


def run_benchmarks(
    settings: Settings,
    *,
    basket_limit: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> list[BenchmarkResult]:
    """Stratejiyle aynı dönem/veri için kıyas çizgilerini üret (Görev 1.1).

    Range modunda barlar stratejiyle AYNI cache anahtarıyla (warmup dahil)
    yüklenir, sonra al-tut penceresine kırpılır — çifte indirme olmaz.
    """
    strat = settings.strategy
    years = strat.backtest["lookback_years"]
    initial = float(strat.backtest["initial_capital"])
    symbols = {s for cfg in strat.baskets.values() for s in cfg.get("universe", [])}
    symbols.add("SPY")

    range_mode, start_ts, end_ts, fetch_start = _resolve_window(strat, start, end)
    bars: dict[str, pd.DataFrame] = {}
    for sym in sorted(symbols):
        if range_mode:
            df = load_bars(sym, start=str(fetch_start.date()), end=str(end_ts.date()))
            df = df.loc[start_ts:end_ts] if not df.empty else df
        else:
            df = load_bars(sym, years=years)
        bars[sym] = df
    return benchmark_suite(bars, strat.baskets, initial, basket_limit=basket_limit)


def _save_results(r: BacktestResult) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if r.equity_curve is not None and not r.equity_curve.empty:
        r.equity_curve.to_csv(RESULTS_DIR / "equity_curve.csv", header=True)
    if r.trades:
        pd.DataFrame([t.__dict__ for t in r.trades]).to_csv(RESULTS_DIR / "trades.csv", index=False)


def main() -> None:
    import sys
    try:  # Windows konsolunda Türkçe/ok karakterleri için
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    parser = argparse.ArgumentParser(description="Strateji backtest")
    parser.add_argument("--basket-limit", type=int, default=None,
                        help="Her sepetten en fazla N sembol (hızlı deneme için)")
    parser.add_argument("--no-benchmark", action="store_true",
                        help="Al-ve-tut kıyas tablosunu atla")
    parser.add_argument("--start", default=None, metavar="YYYY-MM-DD",
                        help="Dönem başlangıcı (config backtest.start_date'i ezer)")
    parser.add_argument("--end", default=None, metavar="YYYY-MM-DD",
                        help="Dönem bitişi (config backtest.end_date'i ezer)")
    parser.add_argument("--no-trend-filter", action="store_true",
                        help="Trend filtresini kapat (varyant testi)")
    parser.add_argument("--no-volume-direction", action="store_true",
                        help="Yönlü hacim bileşenini kapat (varyant testi)")
    parser.add_argument("--no-rr-gate", action="store_true",
                        help="Risk/Ödül kapısını kapat (varyant testi)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.load(strict=False)
    result = run_backtest(
        settings,
        basket_limit=args.basket_limit,
        start=args.start,
        end=args.end,
        disable_trend_filter=args.no_trend_filter,
        disable_volume_direction=args.no_volume_direction,
        disable_rr_gate=args.no_rr_gate,
    )
    _print_report(result)
    _print_coverage(result)
    if not args.no_benchmark:
        benchmarks = run_benchmarks(settings, basket_limit=args.basket_limit,
                                    start=args.start, end=args.end)
        _print_comparison(result, benchmarks)
    _save_results(result)


if __name__ == "__main__":
    main()
