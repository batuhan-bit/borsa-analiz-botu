"""Rotasyon backtest'i (Görev B.1) — aylık kesitsel rotasyonu gün gün simüle eder.

v1 eşik motorunun backtest'inden (backtest/backtest.py) AYRI bir motordur; v2
rotasyon çekirdeğini (bot.rotation) geçmiş veri üzerinde deterministik koşturur.

İcra sözleşmesi (bak-önden-yok):
  - Rotasyon sinyali ayın ilk işlem günü KAPANIŞ verisiyle üretilir.
  - İcra ERTESİ işlem günü AÇILIŞ fiyatından yapılır (execution_lag_days).
  - Maliyet ilk günden: komisyon (bps) + sabit komisyon + sepet-bazlı kayma (bps).
  - Satış-uyarısı tetikleri (Görev A.3) backtest'te de uygulanır: tetik → ertesi
    açılışta satış + slot doldurma (yoksa canlı davranış test edilmemiş olur).

Kapsam politikası v1'deki gibi: sembol verisi (skoru) oluştuğu gün evrene katılır;
sepet bazlı kapsam raporu döndürülür.

Determinizm (kabul kriteri): aynı `bars`, aynı pencere, aynı ayar → bit-bazında
aynı sonuç. Skorlar bir kez panele kurulur (scoring.Ranker.score_series), sıralama
daima (-skor, sembol) ile yapılır, sözlük sırası korunur.

Fiyat verisi dışarıdan `bars: Mapping[symbol -> OHLCV DataFrame]` ile enjekte edilir;
bu modül veri kaynağı bilmez (test edilebilir, ağsız). CLI koşusu (real-data)
`main()` içinde yfinance'ten yükler.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional

import pandas as pd

from bot.config import Strategy
from bot.rotation.alerts import (
    AlertCooldown,
    RankingCollapseTracker,
    check_technical_emergency,
)
from bot.rotation.engine import RotationEngine
from bot.rotation.scoring import make_ranker
from bot.rotation.slots import slot_candidates

log = logging.getLogger("rotation_backtest")

# ATR periyodu — levels._atr / A.3 compute_atr ile aynı yerleşik konvansiyon (14).
# Ayarlanabilir bir strateji parametresi değildir; modüller arası sabit bir kabuldür.
ATR_PERIOD = 14
TRADING_DAYS_PER_YEAR = 252


# ----------------------------------------------------------------------
#  Sonuç modelleri
# ----------------------------------------------------------------------
@dataclass
class RotationTrade:
    symbol: str
    basket: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    gross_pnl: float
    cost: float           # bu işleme (alış+satış) atfedilen toplam maliyet
    net_pnl: float
    return_pct: float
    exit_reason: str      # rotation | technical_emergency | ranking_collapse | backtest_end


@dataclass
class RotationBacktestResult:
    initial_capital: float
    final_equity: float
    total_return_pct: float
    annualized_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    num_trades: int
    total_cost: float
    start: str
    end: str
    apply_costs: bool
    equity_curve: pd.Series = field(default=None, repr=False)
    trades: list[RotationTrade] = field(default_factory=list, repr=False)
    coverage: dict[str, tuple[int, int]] = field(default_factory=dict)  # basket -> (kapsanan, toplam)


# ----------------------------------------------------------------------
#  Yardımcılar
# ----------------------------------------------------------------------
def _atr_series(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """Her tarih için ATR (levels._atr ile aynı hesap; tek sayı yerine seri)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _in_window(index: pd.DatetimeIndex, start, end) -> pd.DatetimeIndex:
    lo = pd.Timestamp(start) if start is not None else index.min()
    hi = pd.Timestamp(end) if end is not None else index.max()
    return index[(index >= lo) & (index <= hi)]


def _rotation_days(calendar: list[pd.Timestamp], frequency: str) -> set[pd.Timestamp]:
    """Rotasyon sinyal günleri.

    monthly  : her ayın ilk işlem günü.
    biweekly : her ayın ilk işlem günü + o ayda 15'inden sonraki ilk işlem günü.
    """
    days: set[pd.Timestamp] = set()
    seen_month: set[tuple[int, int]] = set()
    seen_half: set[tuple[int, int]] = set()
    for d in calendar:
        key = (d.year, d.month)
        if key not in seen_month:
            seen_month.add(key)
            days.add(d)
        if frequency == "biweekly" and d.day >= 15 and key not in seen_half:
            seen_half.add(key)
            days.add(d)
    return days


def _latest_at(series: pd.Series, day: pd.Timestamp) -> Optional[float]:
    """Seride `day` gününe (dahil) kadarki son değeri döndür (yoksa None)."""
    s = series.loc[:day]
    if s.empty:
        return None
    val = s.iloc[-1]
    return float(val) if pd.notna(val) else None


# ----------------------------------------------------------------------
#  Simülasyon
# ----------------------------------------------------------------------
@dataclass
class _Pos:
    shares: float
    entry_price: float
    entry_date: pd.Timestamp
    basket: str
    entry_atr: float
    cost_paid: float          # alışta ödenen maliyet (net_pnl için taşınır)


def run_rotation_backtest(
    strategy: Strategy,
    bars: Mapping[str, pd.DataFrame],
    *,
    start=None,
    end=None,
    apply_costs: bool = True,
    slippage_scale: float = 1.0,
) -> RotationBacktestResult:
    """Rotasyonu gün gün simüle et ve özet metrikleri döndür.

    slippage_scale: pertürbasyon topluluğu (B.2) kayma çarpanı; 1.0 = ayarlı kayma.
    apply_costs=False ise komisyon/kayma sıfırlanır (maliyetsiz/maliyetli fark için).
    """
    rot_cfg = strategy.rotation
    bt_cfg = strategy.rotation_backtest
    frequency = rot_cfg.get("frequency", "monthly")
    fractional = bool(bt_cfg.get("fractional_shares", False))

    initial = float(bt_cfg.get("initial_capital", 3000))
    commission_bps = float(bt_cfg.get("commission_bps", 0)) if apply_costs else 0.0
    commission_fixed = float(bt_cfg.get("commission_fixed_usd", 0)) if apply_costs else 0.0
    slippage_bps_cfg = dict(bt_cfg.get("slippage_bps", {})) if apply_costs else {}
    deployment = float(bt_cfg.get("deployment_pct", 100)) / 100.0

    reg = bt_cfg.get("regime", {}) or {}
    regime_on = bool(reg.get("enabled", False))
    regime_bench = reg.get("benchmark", "SPY")
    regime_ma = int(reg.get("ma_days", 200))
    regime_deploy = float(reg.get("deployment_pct", deployment * 100)) / 100.0

    engine = RotationEngine(strategy)
    ranker = make_ranker(strategy, lambda s: bars.get(s, pd.DataFrame()))
    top_n = int(rot_cfg.get("top_n", 6))
    atr_mult = float(strategy.raw.get("sell_alerts", {}).get("atr_exit_multiple", 3.0))
    # Ping-pong (aç-kapa) koruması — teşhis: results/diag_1923_trades.md.
    #  - collapse_tracker: taban-hizalı (per_basket: sepet-içi) + kalıcılık şartlı
    #    (art arda N işlem günü). Teknik acil tetik bu şarttan MUAF (aşağıda ayrı).
    #  - cooldown: uyarıyla kapanan sembol N işlem günü slot adayı olamaz.
    collapse_tracker = RankingCollapseTracker(strategy)
    cooldown = AlertCooldown(strategy)

    universe = strategy.universe_symbols or [
        s for cfg in strategy.baskets.values() for s in cfg.get("universe", [])
    ]

    # --- Panelleri kur: skor serisi + ATR serisi (bir kez) ---
    score_panel: dict[str, pd.Series] = {}
    atr_panel: dict[str, pd.Series] = {}
    for sym in universe:
        df = bars.get(sym)
        if df is None or df.empty:
            continue
        ss = ranker.score_series(df)
        if not ss.empty:
            score_panel[sym] = ss
            atr_panel[sym] = _atr_series(df)

    # Rejim benchmark'ının MA serisi
    regime_ma_series = None
    if regime_on and regime_bench in bars and not bars[regime_bench].empty:
        regime_ma_series = bars[regime_bench]["close"].rolling(regime_ma).mean()

    def slippage_for(basket: str) -> float:
        return float(slippage_bps_cfg.get(basket, 0.0)) * slippage_scale

    # --- Takvim ve rotasyon günleri ---
    all_index = pd.DatetimeIndex(sorted(set().union(
        *[set(df.index) for df in bars.values()]
    ))) if bars else pd.DatetimeIndex([])
    calendar = list(_in_window(all_index, start, end))
    if not calendar:
        return _empty_result(strategy, initial, apply_costs, universe)
    rotation_days = _rotation_days(calendar, frequency)

    # --- Portföy durumu ---
    cash = initial
    positions: dict[str, _Pos] = {}
    trades: list[RotationTrade] = []
    total_cost = 0.0
    equity_dates: list[pd.Timestamp] = []
    equity_vals: list[float] = []
    # Ertesi açılışta icra edilecek emirler: ("sell", sym) | ("buy", sym, weight)
    pending: list[tuple] = []

    def price_on(sym: str, day: pd.Timestamp, field_name: str) -> Optional[float]:
        df = bars.get(sym)
        if df is None or day not in df.index:
            return None
        val = df.loc[day, field_name]
        return float(val) if pd.notna(val) else None

    def last_close(sym: str, day: pd.Timestamp) -> Optional[float]:
        df = bars.get(sym)
        if df is None:
            return None
        s = df["close"].loc[:day]
        return float(s.iloc[-1]) if not s.empty else None

    def trade_cost(basket: str, notional: float) -> float:
        rate = (commission_bps + slippage_for(basket)) / 10000.0
        return notional * rate + commission_fixed

    def ranking_as_of(day: pd.Timestamp) -> list[tuple[str, float]]:
        scored = []
        for sym, series in score_panel.items():
            v = _latest_at(series, day)
            if v is not None:
                scored.append((sym, v))
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def rank_fn_as_of(day: pd.Timestamp):
        def fn(symbols):
            out = []
            for s in symbols:
                series = score_panel.get(s)
                if series is None:
                    continue
                v = _latest_at(series, day)
                if v is not None:
                    out.append((s, v))
            return out
        return fn

    def do_sell(sym: str, price: float, day: pd.Timestamp, reason: str) -> None:
        nonlocal cash, total_cost
        pos = positions.pop(sym)
        notional = pos.shares * price
        cost = trade_cost(pos.basket, notional)
        total_cost += cost
        cash += notional - cost
        gross = notional - pos.shares * pos.entry_price
        total_trade_cost = pos.cost_paid + cost
        net = gross - total_trade_cost
        ret = (price - pos.entry_price) / pos.entry_price * 100.0 if pos.entry_price else 0.0
        trades.append(RotationTrade(
            symbol=sym, basket=pos.basket,
            entry_date=str(pos.entry_date.date()), exit_date=str(day.date()),
            entry_price=round(pos.entry_price, 4), exit_price=round(price, 4),
            shares=round(pos.shares, 4), gross_pnl=round(gross, 2),
            cost=round(total_trade_cost, 2), net_pnl=round(net, 2),
            return_pct=round(ret, 2), exit_reason=reason,
        ))

    def do_buy(sym: str, weight: float, capital: float, price: float,
               day: pd.Timestamp, basket: str) -> None:
        nonlocal cash, total_cost
        if price <= 0 or weight <= 0:
            return
        target_value = min(weight * capital, cash)
        shares = round(target_value / price, 2) if fractional else float(math.floor(target_value / price))
        if shares <= 0:
            return
        notional = shares * price
        cost = trade_cost(basket, notional)
        if notional + cost > cash:      # maliyet dahil nakit yetmezse bir adım küçült
            shares = round((cash - commission_fixed) / (price * (1 + (commission_bps + slippage_for(basket)) / 10000.0)), 2) if fractional \
                else float(math.floor((cash - commission_fixed) / (price * (1 + (commission_bps + slippage_for(basket)) / 10000.0))))
            if shares <= 0:
                return
            notional = shares * price
            cost = trade_cost(basket, notional)
        total_cost += cost
        cash -= notional + cost
        atr = _latest_at(atr_panel.get(sym, pd.Series(dtype=float)), day) or 0.0
        positions[sym] = _Pos(shares, price, day, basket, atr, cost)

    def deployment_frac(day: pd.Timestamp) -> float:
        if not regime_on or regime_ma_series is None:
            return deployment
        spy_close = last_close(regime_bench, day)
        ma = _latest_at(regime_ma_series, day)
        if spy_close is not None and ma is not None and spy_close < ma:
            return regime_deploy
        return deployment

    def execute_pending(day: pd.Timestamp) -> None:
        """Dünkü kararların emirlerini bugünün AÇILIŞ'ında icra et."""
        nonlocal pending
        if not pending:
            return
        carry: list[tuple] = []
        # Önce satışlar (nakit serbest kalsın), sonra alışlar
        sells = [o for o in pending if o[0] == "sell"]
        buys = [o for o in pending if o[0] == "buy"]
        # equity'yi açılış öncesi son kapanışla tahmin et (sizing için)
        equity = cash + sum(
            positions[s].shares * (last_close(s, day) or positions[s].entry_price)
            for s in positions
        )
        capital = equity * deployment_frac(day)
        for o in sells:
            sym = o[1]
            if sym not in positions:
                continue
            px = price_on(sym, day, "open")
            if px is None:
                carry.append(o)
                continue
            do_sell(sym, px, day, o[2])
        for o in buys:
            _, sym, weight, basket = o
            if sym in positions:
                continue
            px = price_on(sym, day, "open")
            if px is None:
                carry.append(o)
                continue
            do_buy(sym, weight, capital, px, day, basket)
        pending = carry

    def rebalance_orders(day: pd.Timestamp) -> list[tuple]:
        """Rotasyon günü: hedef portföye çekecek emirleri üret (ertesi açılış)."""
        equity = cash + sum(
            positions[s].shares * (last_close(s, day) or positions[s].entry_price)
            for s in positions
        )
        current_w = {}
        if equity > 0:
            for s, p in positions.items():
                current_w[s] = (p.shares * (last_close(s, day) or p.entry_price)) / equity
        plan = engine.build_plan(rank_fn_as_of(day), current=current_w)
        weights = plan.weights
        basket_of_target = {t.symbol: t.basket for t in plan.targets}
        orders: list[tuple] = []
        for sym in plan.exiting:
            orders.append(("sell", sym, "rotation"))
        rebal_syms = {a.symbol for a in plan.rebalance}
        for sym in plan.staying:
            if sym in rebal_syms:          # yalnız bant dışı sapmada işlem (churn/maliyet kontrolü)
                orders.append(("sell", sym, "rotation"))       # kapat ve hedef ağırlıkla yeniden aç
                orders.append(("buy", sym, weights[sym], basket_of_target[sym]))
        for sym in plan.entering:
            orders.append(("buy", sym, weights[sym], basket_of_target[sym]))
        return orders

    def alert_orders(day: pd.Timestamp, day_index: int) -> list[tuple]:
        """Rotasyon dışı gün: satış-uyarısı tetikleri + slot doldurma (ertesi açılış).

        - Teknik acil: ani fiyat olayı; kalıcılık şartından MUAF, ilk günden tetikler.
        - Sıralama çöküşü: taban-hizalı + kalıcılık şartlı (collapse_tracker).
        - Uyarıyla kapanan sembol cooldown'a alınır ve aynı gün (ve N gün) slot
          adayı olamaz → aç-kapa döngüsü yapısal olarak kurulamaz.
        """
        if not positions:
            return []
        ranking = ranking_as_of(day)
        # Kalıcılık şartını her alert gününde güncelle; çöküşü dolan semboller:
        collapsed = collapse_tracker.update(ranking, list(positions.keys()))
        orders: list[tuple] = []
        for sym in list(positions.keys()):
            pos = positions[sym]
            px = last_close(sym, day)
            if px is None:
                continue
            t1 = check_technical_emergency(pos.entry_price, px, pos.entry_atr, multiple=atr_mult)
            reason = None
            if t1:
                reason = "technical_emergency"      # MUAF: kalıcılık aranmaz
            elif sym in collapsed:
                reason = "ranking_collapse"         # taban-hizalı + N gün kalıcı
            if reason:
                orders.append(("sell", sym, reason))
        if orders:
            selling = {o[1] for o in orders}
            # Kapanan sembolleri cooldown'a al; bu gün aday havuzundan dışla
            for sym in selling:
                cooldown.register(sym, day_index)
            blocked = cooldown.blocked(day_index)
            remaining = [s for s in positions if s not in selling]
            cands = slot_candidates(strategy, remaining, ranking, excluded=blocked)
            # yalnız boşalan slot sayısı kadar aday; her biri hedef ağırlıkla alınır
            for c in cands[: len(orders)]:
                w = _target_weight_for(strategy, engine, c.symbol)
                orders.append(("buy", c.symbol, w, c.basket or ""))
        return orders

    # --- Ana döngü ---
    for day_index, day in enumerate(calendar):
        execute_pending(day)                      # 1) dünün emirleri: bugünün açılışı
        # 2) MTM özsermaye (bugünün kapanışı)
        equity = cash + sum(
            positions[s].shares * (last_close(s, day) or positions[s].entry_price)
            for s in positions
        )
        equity_dates.append(day)
        equity_vals.append(equity)
        # 3) Kararlar (bugünün kapanışı) -> ertesi açılış emirleri
        if day in rotation_days:
            pending = rebalance_orders(day)
        else:
            pending = alert_orders(day, day_index)

    # Kalan pozisyonları son gün kapanışından kapat
    last_day = calendar[-1]
    for sym in list(positions.keys()):
        px = last_close(sym, last_day) or positions[sym].entry_price
        do_sell(sym, px, last_day, "backtest_end")

    equity_curve = pd.Series(equity_vals, index=equity_dates, name="equity")
    coverage = _coverage(strategy, score_panel, universe)
    return _metrics(equity_curve, trades, initial, total_cost, apply_costs, coverage)


def _target_weight_for(strategy: Strategy, engine: RotationEngine, symbol: str) -> float:
    """Bir slot adayının hedef ağırlığı (seçim moduna göre)."""
    rot = strategy.rotation
    if rot.get("selection") == "global_top_n":
        return 1.0 / int(rot.get("top_n", 6))
    basket = strategy.basket_of(symbol)
    per_basket = int(strategy.portfolio.get("positions_per_basket", 2))
    alloc = strategy.baskets.get(basket, {}).get("allocation_pct", 0) / 100.0
    return alloc / per_basket if per_basket else 0.0


def _coverage(strategy: Strategy, score_panel: dict, universe: list[str]) -> dict[str, tuple[int, int]]:
    cov: dict[str, list[int]] = {}
    for sym in universe:
        b = strategy.basket_of(sym) or "?"
        c = cov.setdefault(b, [0, 0])
        c[1] += 1
        if sym in score_panel:
            c[0] += 1
    return {b: (v[0], v[1]) for b, v in cov.items()}


def _empty_result(strategy, initial, apply_costs, universe) -> RotationBacktestResult:
    return RotationBacktestResult(
        initial_capital=initial, final_equity=initial, total_return_pct=0.0,
        annualized_return_pct=0.0, max_drawdown_pct=0.0, win_rate_pct=0.0,
        num_trades=0, total_cost=0.0, start="-", end="-", apply_costs=apply_costs,
        equity_curve=pd.Series(dtype=float), trades=[],
        coverage=_coverage(strategy, {}, universe),
    )


def _metrics(equity: pd.Series, trades, initial, total_cost, apply_costs, coverage) -> RotationBacktestResult:
    final = float(equity.iloc[-1]) if not equity.empty else initial
    total_return = (final / initial - 1) * 100.0
    span_years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1e-9) if len(equity) > 1 else 1e-9
    annualized = ((final / initial) ** (1 / span_years) - 1) * 100.0 if final > 0 else -100.0
    running_max = equity.cummax()
    dd = (equity - running_max) / running_max
    max_dd = float(dd.min() * 100.0) if not equity.empty else 0.0
    closed = [t for t in trades if t.exit_reason != "backtest_end"] or trades
    wins = [t for t in closed if t.net_pnl > 0]
    win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
    return RotationBacktestResult(
        initial_capital=initial, final_equity=round(final, 2),
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(annualized, 2),
        max_drawdown_pct=round(max_dd, 2), win_rate_pct=round(win_rate, 1),
        num_trades=len(trades), total_cost=round(total_cost, 2),
        start=str(equity.index[0].date()) if len(equity) else "-",
        end=str(equity.index[-1].date()) if len(equity) else "-",
        apply_costs=apply_costs, equity_curve=equity, trades=trades, coverage=coverage,
    )


# ----------------------------------------------------------------------
#  CLI (gerçek veri — yfinance)
# ----------------------------------------------------------------------
def _load_real_bars(symbols: list[str], years: float) -> dict[str, pd.DataFrame]:
    """yfinance'ten barları yükle (backtest/backtest.py ile aynı cache mantığı)."""
    from backtest.backtest import _load_bars
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        df = _load_bars(s, years)
        if not df.empty:
            out[s] = df
    return out


def main() -> None:
    import argparse
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    parser = argparse.ArgumentParser(description="Rotasyon backtest (Faz B / B.1)")
    parser.add_argument("--start", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="YYYY-MM-DD")
    parser.add_argument("--years", type=float, default=11.0, help="yfinance geçmiş uzunluğu")
    parser.add_argument("--no-costs", action="store_true", help="maliyetsiz koşu")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    strategy = Strategy.load()
    bars = _load_real_bars(strategy.universe_symbols, args.years)
    log.info("%d sembol yüklendi.", len(bars))
    r = run_rotation_backtest(strategy, bars, start=args.start, end=args.end,
                              apply_costs=not args.no_costs)
    print(f"\nDönem {r.start} → {r.end} | maliyet={'açık' if r.apply_costs else 'kapalı'}")
    print(f"Toplam getiri %{r.total_return_pct:+.2f} | CAGR %{r.annualized_return_pct:+.2f} "
          f"| MaxDD %{r.max_drawdown_pct:.2f} | işlem {r.num_trades} | maliyet ${r.total_cost:,.2f}")
    print("Kapsam:", {b: f"{c}/{t}" for b, (c, t) in r.coverage.items()})


if __name__ == "__main__":
    main()
