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
from .metrics import cagr_pct, calmar_ratio, max_drawdown_pct, sharpe_ratio

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
    equity_curve: pd.Series = field(default=None, repr=False)
    trades: list[Trade] = field(default_factory=list, repr=False)


def run_backtest(
    settings: Optional[Settings] = None,
    *,
    basket_limit: Optional[int] = None,
    verbose: bool = True,
) -> BacktestResult:
    """Backtest çalıştır ve özet metrikleri döndür."""
    settings = settings or Settings.load(strict=False)
    strat = settings.strategy
    tech_cfg = strat.technical
    years = strat.backtest["lookback_years"]
    initial = float(strat.backtest["initial_capital"])
    stop_loss_pct = strat.risk["position_stop_loss_pct"]
    buy = strat.raw.get("signals", {}).get("buy_threshold", 0.30)
    sell = strat.raw.get("signals", {}).get("sell_threshold", -0.30)
    min_rr = strat.raw.get("signals", {}).get("min_risk_reward", 0.0)
    positions_per_basket = strat.portfolio["positions_per_basket"]

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

    # Her sembol için sinyal çerçevesi (veri yoksa atla)
    sig_frames: dict[str, pd.DataFrame] = {}
    for basket, syms in universe.items():
        for sym in syms:
            df = load_bars(sym, years=years)
            if df.empty or len(df) < tech_cfg["moving_averages"]["long"] + 5:
                log.warning("Yetersiz veri, atlanıyor: %s", sym)
                continue
            sf = _build_signal_frame(df, tech_cfg, buy, sell,
                                     min_rr=min_rr, max_loss_pct=stop_loss_pct)
            if not sf.empty:
                sig_frames[sym] = sf
    if verbose:
        log.info("%d sembol yüklendi.", len(sig_frames))

    # Ana takvim = tüm sembollerin tarih birleşimi
    all_dates = sorted(set().union(*[set(sf.index) for sf in sig_frames.values()]))

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
    return _metrics(equity_curve, trades, initial, years, sig_frames, target=target)


def _metrics(equity: pd.Series, trades: list[Trade], initial: float, years: float,
             sig_frames: dict[str, pd.DataFrame], *, target: float = 6.5) -> BacktestResult:
    final = float(equity.iloc[-1]) if not equity.empty else initial
    total_return = (final / initial - 1) * 100.0

    annualized = cagr_pct(equity) if len(equity) > 1 else 0.0
    max_dd = max_drawdown_pct(equity)

    closed = [t for t in trades if t.reason != "backtest_end"] or trades
    wins = [t for t in closed if t.pnl > 0]
    win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0

    # Benchmark: SPY al-tut (varsa)
    benchmark = None
    spy = sig_frames.get("SPY")
    if spy is not None and len(spy) > 1:
        benchmark = (spy["close"].iloc[-1] / spy["close"].iloc[0] - 1) * 100.0

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


def run_benchmarks(settings: Settings, *, basket_limit: Optional[int] = None) -> list[BenchmarkResult]:
    """Stratejiyle aynı dönem/veri için kıyas çizgilerini üret (Görev 1.1)."""
    strat = settings.strategy
    years = strat.backtest["lookback_years"]
    initial = float(strat.backtest["initial_capital"])
    symbols = {s for cfg in strat.baskets.values() for s in cfg.get("universe", [])}
    symbols.add("SPY")
    bars = {sym: load_bars(sym, years=years) for sym in sorted(symbols)}
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
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.load(strict=False)
    result = run_backtest(settings, basket_limit=args.basket_limit)
    _print_report(result)
    if not args.no_benchmark:
        benchmarks = run_benchmarks(settings, basket_limit=args.basket_limit)
        _print_comparison(result, benchmarks)
    _save_results(result)


if __name__ == "__main__":
    main()
