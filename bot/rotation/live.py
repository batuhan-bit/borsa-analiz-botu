"""Canlı rotasyon akışı (Görev C.1) — günlük karar üretimi.

Backtest'in gün-gün simülasyonunun canlı karşılığı: TEK bir "bugün" için öneri
üretir. İcra MANUEL'dir (bot yalnız sinyal verir; alım-satımı kullanıcı yapar),
bu yüzden portföyü mutasyona uğratmaz — mevcut pozisyonları (Sheets'ten) okur ve
öneri döndürür.

Her gün:
  - Satış-uyarısı taraması (teknik acil + sıralama çöküşü + temel kırmızı bayrak)
  - Slot doldurma önerisi (boşalan slotlar için, cooldown'a saygılı)   [rotasyon-dışı gün]
  - Günlük gözlem (eylemsiz)
Rotasyon günü (bkz. bot.rotation.calendar) EK OLARAK:
  - Rotasyon önerisi: giren/çıkan/kalan + 💰 sizing + çıkan gerekçesi + rebalans notu

Cooldown deseni backtest ile BİREBİR: TEK AlertCooldown + rank_fn enjeksiyonu.
Cooldown durumu koşular arası kalıcıdır (bot.rotation.cooldown_store). Sıralama-
çöküşü kalıcılığı (persist_days) ise fiyat geçmişinden YENİDEN TÜRETİLİR (son
persist_days işlem gününün sıralaması tekrar oynatılır) — ayrı depo gerekmez.

Saf/test edilebilir: strategy + bars + holdings + cooldown dışarıdan gelir; ağ yok.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Optional, Sequence

import pandas as pd

from ..config import Strategy
from .alerts import (
    AlertCooldown,
    RankingCollapseTracker,
    SellAlert,
    SellTrigger,
    TriggerType,
    check_fundamental_red_flags,
    check_ranking_collapse,
    check_technical_emergency,
    collapse_cutoff,
    collapse_rank_map,
)
from .calendar import is_rotation_day
from .engine import RotationEngine, RotationPlan
from .scoring import make_ranker
from .slots import Observation, daily_observation, slot_candidates

log = logging.getLogger(__name__)

ATR_PERIOD = 14


# ----------------------------------------------------------------------
#  Öneri modelleri
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class BuySuggestion:
    """Alım önerisi (rotasyon girişi veya slot doldurma) — 💰 tutar/adet dahil."""
    symbol: str
    basket: Optional[str]
    theme: Optional[str]
    weight: float
    price: float
    shares: float           # önerilen adet (kesirli mod açıksa ondalıklı)
    value: float            # shares * price
    rank: Optional[int]
    reason: str


@dataclass(frozen=True)
class ExitSuggestion:
    """Rotasyon günü çıkış önerisi (hedeften düşen kalıcı pozisyon)."""
    symbol: str
    basket: Optional[str]
    rank: Optional[int]
    reason: str


@dataclass(frozen=True)
class RebalanceNote:
    symbol: str
    action: str             # "ekle" | "azalt"
    current_weight: float
    target_weight: float
    drift_pct: float


@dataclass
class LiveDecision:
    as_of: date
    frequency: str
    is_rotation_day: bool
    today_index: int = -1        # bugünün takvimdeki işlem-günü indeksi (cooldown persist için)
    sell_alerts: list[SellAlert] = field(default_factory=list)
    newly_cooled: set[str] = field(default_factory=set)
    slot_fills: list[BuySuggestion] = field(default_factory=list)
    observation: Optional[Observation] = None
    # Yalnız rotasyon günü:
    rotation_entries: list[BuySuggestion] = field(default_factory=list)
    rotation_exits: list[ExitSuggestion] = field(default_factory=list)
    rotation_holds: list[str] = field(default_factory=list)
    rebalance_notes: list[RebalanceNote] = field(default_factory=list)
    ranking: list[tuple[str, float]] = field(default_factory=list)
    # Karne (Görev C.2) için: ilgili sembollerin sinyal-günü kapanış fiyatları.
    prices: dict[str, float] = field(default_factory=dict)
    # Aylık özet (portföy vs SPY vs evren al-tut); main rotasyon gününde doldurur.
    monthly_summary: Optional[dict] = None


# ----------------------------------------------------------------------
#  Yardımcılar
# ----------------------------------------------------------------------
def _atr_series(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _latest_at(series: pd.Series, day: pd.Timestamp) -> Optional[float]:
    if series is None or series.empty:
        return None
    s = series.loc[:day]
    if s.empty:
        return None
    val = s.iloc[-1]
    return float(val) if pd.notna(val) else None


def _held_symbols(holdings: Sequence[Mapping]) -> list[str]:
    return [str(h["symbol"]).strip().upper() for h in holdings if h.get("symbol")]


# ----------------------------------------------------------------------
#  Ana akış
# ----------------------------------------------------------------------
def run_live_flow(
    strategy: Strategy,
    bars: Mapping[str, pd.DataFrame],
    holdings: Sequence[Mapping],
    cooldown: AlertCooldown,
    *,
    today: Optional[date] = None,
    portfolio_value: Optional[float] = None,
    cash: Optional[float] = None,
    fundamentals: Optional[Mapping[str, Mapping]] = None,
    observation_lookback: int = 5,
) -> LiveDecision:
    """Bugünün rotasyon/uyarı/gözlem önerilerini üret.

    holdings: Sheets Pozisyonlar satırları (symbol, basket, entry_price, shares,
              entry_date). İcra manuel olduğu için bu okunur, mutasyona uğratılmaz.
    cooldown: koşular arası kalıcı durumdan yeniden kurulan AlertCooldown
              (bot.rotation.cooldown_store.reconstruct_cooldown). Bugün yeni
              kapananlar burada register edilir; çağıran `newly_cooled`'u persist eder.
    portfolio_value: verilirse sizing tabanını doğrudan belirler (test/çağıran
              tam kontrol ister).
    cash: serbest nakit (Sheets NAKİT satırı). portfolio_value yoksa sizing
              tabanı = holdings piyasa değeri + cash olur; all-cash başlangıçta
              taban = cash. İkisi de yoksa config budget_max fallback (yalnız
              gerçek nakit bilinmiyorken). Nakit adaylar arasına hedef ağırlıklara
              göre PRO-RATA dağıtılır (tek adaya yığılmaz).
    """
    rot_cfg = strategy.rotation
    frequency = rot_cfg.get("frequency", "monthly")
    # Canlı broker kesirli hisse destekler (Görev D.2). Bu, backtest'in
    # `rotation_backtest.fractional_shares` (standart koşu tam-sayı) ayarından
    # AYRIDIR — canlı sizing küçük bütçede tek-adet flooring'e takılmasın diye.
    fractional = bool(rot_cfg.get("live_fractional_shares",
                                  strategy.rotation_backtest.get("fractional_shares", False)))
    atr_mult = float(strategy.raw.get("sell_alerts", {}).get("atr_exit_multiple", 3.0))
    top_n = int(rot_cfg.get("top_n", 6))
    fundamentals = fundamentals or {}

    engine = RotationEngine(strategy)
    ranker = make_ranker(strategy, lambda s: bars.get(s, pd.DataFrame()))
    universe = strategy.universe_symbols

    # Skor + ATR panelleri (bir kez)
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

    # Takvim (gerçek işlem günleri) + bugün
    all_index = pd.DatetimeIndex(sorted(set().union(
        *[set(df.index) for df in bars.values()]
    ))) if bars else pd.DatetimeIndex([])
    calendar = list(all_index)
    if not calendar:
        return LiveDecision(as_of=today or date.today(), frequency=frequency,
                            is_rotation_day=False)
    as_of_ts = pd.Timestamp(today).normalize() if today is not None else calendar[-1]
    # bugünü takvime hizala (<= as_of son işlem günü)
    trimmed = [d for d in calendar if d <= as_of_ts]
    if not trimmed:
        return LiveDecision(as_of=as_of_ts.date(), frequency=frequency, is_rotation_day=False)
    as_of_ts = trimmed[-1]
    today_index = len(trimmed) - 1

    def last_close(sym: str, day: pd.Timestamp) -> Optional[float]:
        df = bars.get(sym)
        if df is None:
            return None
        s = df["close"].loc[:day]
        if s.empty:
            return None
        val = s.iloc[-1]
        return float(val) if pd.notna(val) else None

    def ranking_as_of(day: pd.Timestamp) -> list[tuple[str, float]]:
        scored = []
        for sym, series in score_panel.items():
            v = _latest_at(series, day)
            if v is not None:
                scored.append((sym, v))
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def rank_fn_as_of(day: pd.Timestamp, day_index: int):
        """Rotasyon seçim skoru — AlertCooldown TEK doğruluk kaynağı (backtest deseni).

        Bekleme süresindeki semboller elenir → engine.build_plan onları hedef
        seçemez; sıradaki uygun aday otomatik alınır.
        """
        blocked = cooldown.blocked(day_index)

        def fn(symbols):
            out = []
            for s in symbols:
                if s in blocked:
                    continue
                v = _latest_at(score_panel.get(s), day)
                if v is not None:
                    out.append((s, v))
            return out
        return fn

    ranking_today = ranking_as_of(as_of_ts)
    held = _held_symbols(holdings)
    held_set = set(held)
    is_rot = is_rotation_day(as_of_ts, calendar, frequency)

    decision = LiveDecision(
        as_of=as_of_ts.date(), frequency=frequency, is_rotation_day=is_rot,
        today_index=today_index, ranking=ranking_today,
    )

    # --- 1) Satış-uyarısı taraması (her gün) ---
    persist_days = RankingCollapseTracker(strategy).persist_days
    collapsed = _replay_collapse(strategy, ranking_as_of, trimmed, held, today_index, persist_days)
    cutoff = collapse_cutoff(strategy)
    rank_map = collapse_rank_map(strategy, ranking_today)

    hold_by_symbol = {str(h["symbol"]).strip().upper(): h for h in holdings if h.get("symbol")}
    for sym in held:
        h = hold_by_symbol[sym]
        px = last_close(sym, as_of_ts)
        if px is None:
            continue
        triggers: list[SellTrigger] = []
        entry_price = float(h.get("entry_price") or 0.0)
        entry_atr = _entry_atr(atr_panel.get(sym), h.get("entry_date"), as_of_ts)
        t1 = check_technical_emergency(entry_price, px, entry_atr, multiple=atr_mult)
        if t1:
            triggers.append(t1)
        if sym in collapsed:
            t2 = check_ranking_collapse(rank_map.get(sym), cutoff=cutoff)
            if t2:
                triggers.append(t2)
        triggers.extend(check_fundamental_red_flags(
            fundamentals.get(sym, {}), strategy.raw.get("sell_alerts", {}).get("fundamental", {})))
        if triggers:
            decision.sell_alerts.append(SellAlert(
                symbol=sym, triggers=triggers, current_rank=rank_map.get(sym)))

    # Uyarıyla işaretlenen semboller cooldown'a alınır (yeniden-giriş beklemesi).
    decision.newly_cooled = {a.symbol for a in decision.sell_alerts}
    for sym in decision.newly_cooled:
        cooldown.register(sym, today_index)

    # Sizing tabanı: gerçek yatırılabilir sermaye = mevcut pozisyon değeri + serbest
    # nakit (Sheets NAKİT satırından). deployment_pct kadarı dağıtılır. Hedef
    # ağırlıklar (allocation / positions_per_basket) toplamı 1.0 olduğundan
    # target_value = weight × deployable, nakdi adaylar arasında PRO-RATA paylaştırır
    # (tek adaya yığmaz). budget_max yalnız hem holdings hem cash bilinmiyorsa fallback.
    capital = _sizing_capital(strategy, holdings, bars, as_of_ts, portfolio_value, cash)
    deployment_pct = float(strategy.rotation_backtest.get("deployment_pct", 100))
    deployable = capital * deployment_pct / 100.0

    # --- 2) Rotasyon önerisi (yalnız rotasyon günü) ---
    if is_rot:
        _build_rotation(decision, strategy, engine, rank_fn_as_of(as_of_ts, today_index),
                        holdings, held_set, ranking_today, bars, as_of_ts, deployable,
                        fractional, last_close)
    else:
        # --- 3) Slot doldurma (rotasyon-dışı gün) ---
        blocked = cooldown.blocked(today_index)
        cands = slot_candidates(strategy, held, ranking_today, excluded=blocked)
        for c in cands:
            px = last_close(c.symbol, as_of_ts) or 0.0
            w = _target_weight_for(strategy, c.symbol)
            decision.slot_fills.append(_size_buy(
                c.symbol, c.basket, c.theme, w, px, deployable, fractional,
                c.rank, c.reason))

    # --- 4) Günlük gözlem (her gün, eylemsiz) ---
    decision.observation = _build_observation(
        ranking_as_of, trimmed, today_index, held, top_n, observation_lookback)

    # Karne (Görev C.2) için sinyal-günü fiyatları: ilgili tüm semboller
    relevant = set(held) | {a.symbol for a in decision.sell_alerts}
    relevant |= {b.symbol for b in decision.rotation_entries + decision.slot_fills}
    relevant |= {e.symbol for e in decision.rotation_exits}
    for sym in relevant:
        px = last_close(sym, as_of_ts)
        if px is not None:
            decision.prices[sym] = round(px, 4)
    return decision


# ----------------------------------------------------------------------
#  Alt yardımcılar
# ----------------------------------------------------------------------
def _entry_atr(series: Optional[pd.Series], entry_date, as_of_ts: pd.Timestamp) -> float:
    """Giriş tarihindeki ATR (yoksa bugüne kadarki son ATR)."""
    if series is None or series.empty:
        return 0.0
    if entry_date:
        try:
            v = _latest_at(series, pd.Timestamp(entry_date).normalize())
            if v is not None:
                return v
        except (ValueError, TypeError):
            pass
    return _latest_at(series, as_of_ts) or 0.0


def _replay_collapse(strategy, ranking_as_of, calendar, holdings, today_index, persist_days) -> set:
    """Sıralama-çöküşü kalıcılığını fiyat geçmişinden yeniden türet.

    Son `persist_days` işlem gününün sıralamasını tekrar oynatır; art arda eşik
    dışı kalan (kalıcılığı dolan) semboller döner. Ayrı depo gerekmez — bars
    zaten mevcut. Teknik acil tetik bu şarttan MUAF (ayrı yolda değerlendirilir).
    """
    tracker = RankingCollapseTracker(strategy)
    start = max(0, today_index - persist_days + 1)
    collapsed: set = set()
    for i in range(start, today_index + 1):
        ranking = ranking_as_of(calendar[i])
        collapsed = tracker.update(ranking, holdings)
    return collapsed


def _sizing_capital(strategy, holdings, bars, as_of_ts, portfolio_value, cash=None) -> float:
    """Yatırılabilir sermaye tabanı = mevcut pozisyon piyasa değeri + serbest nakit.

    - portfolio_value verilirse doğrudan onu kullan (çağıran tam kontrol ister).
    - Aksi halde holdings piyasa değeri + `cash` (Sheets NAKİT satırı) toplanır.
    - İkisi de bilinmiyorsa (cash=None ve holdings=0) config budget_max fallback.
      budget_max bir TAHMİN'dir; gerçek nakit bilindiğinde ASLA kullanılmaz.
    """
    if portfolio_value is not None:
        return float(portfolio_value)
    total = 0.0
    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        df = bars.get(sym)
        shares = float(h.get("shares") or 0.0)
        if df is not None and shares:
            s = df["close"].loc[:as_of_ts]
            if not s.empty:
                total += shares * float(s.iloc[-1])
    if cash is not None:
        # Serbest nakit bilindiğinde taban = pozisyon değeri + nakit (all-cash
        # başlangıçta = nakit). budget_max fallback'ine DÜŞÜLMEZ.
        return total + float(cash)
    if total > 0:
        return total
    return float(strategy.portfolio.get("budget_max", 5000))


def _target_weight_for(strategy: Strategy, symbol: str) -> float:
    rot = strategy.rotation
    if rot.get("selection") == "global_top_n":
        return 1.0 / int(rot.get("top_n", 6))
    basket = strategy.basket_of(symbol)
    per_basket = int(strategy.portfolio.get("positions_per_basket", 2))
    alloc = strategy.baskets.get(basket, {}).get("allocation_pct", 0) / 100.0
    return alloc / per_basket if per_basket else 0.0


def _size_buy(symbol, basket, theme, weight, price, capital, fractional,
              rank, reason) -> BuySuggestion:
    # target_value = weight × deployable. Ağırlıklar (allocation/positions_per_basket)
    # toplamı 1.0 olduğu için bu, deployable'ı adaylar arasında PRO-RATA paylaştırır;
    # eski `min(target_value, cash)` kapısı (her adayı TÜM nakde kısıtlayıp nakdi tek
    # adaya yığan) kaldırıldı — sermaye tabanı zaten doğru nakit üzerinden hesaplanıyor.
    target_value = weight * capital
    if price <= 0 or target_value <= 0:
        shares = 0.0
    elif fractional:
        # 2 ondalığa AŞAĞI yuvarla — round() yukarı yuvarlayıp önerilen toplamın
        # serbest nakdi aşmasına yol açabiliyordu (nakit-kısıtı ihlali).
        shares = math.floor(target_value / price * 100) / 100.0
    else:
        shares = float(math.floor(target_value / price))
    return BuySuggestion(
        symbol=symbol, basket=basket, theme=theme, weight=round(weight, 4),
        price=round(price, 2), shares=shares, value=round(shares * price, 2),
        rank=rank, reason=reason,
    )


def _build_rotation(decision, strategy, engine, rank_fn, holdings, held_set,
                    ranking_today, bars, as_of_ts, capital, fractional, last_close):
    # Mevcut ağırlıklar (yatırılan değere göre; rebalans notları tavsiyedir)
    values: dict[str, float] = {}
    for h in holdings:
        sym = str(h.get("symbol", "")).strip().upper()
        shares = float(h.get("shares") or 0.0)
        px = last_close(sym, as_of_ts)
        if px and shares:
            values[sym] = shares * px
    total = sum(values.values())
    current_w = {s: v / total for s, v in values.items()} if total > 0 else {}

    plan: RotationPlan = engine.build_plan(rank_fn, current=current_w)
    target_by_symbol = {t.symbol: t for t in plan.targets}
    rank_pos = {sym: i for i, (sym, _) in enumerate(ranking_today, start=1)}

    for sym in plan.entering:
        t = target_by_symbol[sym]
        px = last_close(sym, as_of_ts) or 0.0
        decision.rotation_entries.append(_size_buy(
            sym, t.basket, t.theme, t.weight, px, capital, fractional,
            rank_pos.get(sym), f"yeni giren (sıra #{rank_pos.get(sym, '—')})"))

    for sym in plan.exiting:
        decision.rotation_exits.append(ExitSuggestion(
            symbol=sym, basket=strategy.basket_of(sym), rank=rank_pos.get(sym),
            reason=f"sıra düşüşü — hedef portföy dışı (güncel sıra #{rank_pos.get(sym, '—')})"))

    decision.rotation_holds = list(plan.staying)
    for a in plan.rebalance:
        decision.rebalance_notes.append(RebalanceNote(
            symbol=a.symbol, action=a.action, current_weight=a.current_weight,
            target_weight=a.target_weight, drift_pct=a.drift_pct))


def _build_observation(ranking_as_of, calendar, today_index, holdings, top_n, lookback) -> Observation:
    rank_now = {sym: i for i, (sym, _) in enumerate(ranking_as_of(calendar[today_index]), start=1)}
    past_i = max(0, today_index - lookback)
    rank_past = {sym: i for i, (sym, _) in enumerate(ranking_as_of(calendar[past_i]), start=1)}
    return daily_observation(rank_now, rank_past, holdings, top_n=top_n)
