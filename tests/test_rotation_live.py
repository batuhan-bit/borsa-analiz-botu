"""Canlı rotasyon akışı testleri (Görev C.1) — ağ gerektirmez.

Bars sentetik ve geometriktir: price[t] = base * r**t → momentum skoru r'ye göre
monoton, bu yüzden sıralama tümüyle kontrol edilebilir/deterministik. Winner
konfig s2_momentum (lookback 126, skip 21) olduğundan her sembole ~210 işlem
günü verilir.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from bot.config import Strategy
from bot.rotation import run_live_flow
from bot.rotation.alerts import AlertCooldown, TriggerType

# Sepet başına 3 sembol (winner: per_basket, sepet başına 2 pozisyon seçilir)
RATES = {
    "SPY": 1.005, "XLU": 1.004, "XLP": 1.003,        # low_volatility
    "NVDA": 1.006, "AMD": 1.005, "SMCI": 1.004,      # high_volatility
    "IONQ": 1.005, "RGTI": 1.004, "RKLB": 1.003,     # under_radar
}
INDEX = pd.bdate_range(end="2022-06-30", periods=210)
ROT_DAY = pd.Timestamp("2022-06-01")     # haziranın ilk işlem günü -> rotasyon
NON_ROT_DAY = pd.Timestamp("2022-06-08")  # ay ortası, 15 öncesi -> rotasyon değil


def _geom_bars(rate: float, base: float = 100.0) -> pd.DataFrame:
    close = pd.Series([base * (rate ** i) for i in range(len(INDEX))], index=INDEX)
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000,
    }, index=INDEX)


def _bars() -> dict:
    return {sym: _geom_bars(r) for sym, r in RATES.items()}


def _strat(**sell_alert_overrides) -> Strategy:
    s = Strategy.load()
    if sell_alert_overrides:
        s.raw.setdefault("sell_alerts", {}).update(sell_alert_overrides)
    return s


def _holding(symbol, basket, entry_price=1.0, shares=1.0, entry_date=None):
    return {"symbol": symbol, "basket": basket, "entry_price": entry_price,
            "shares": shares, "entry_date": entry_date}


# ---------------------------------------------------------------------------
#  Rotasyon günü
# ---------------------------------------------------------------------------
def test_rotation_day_proposes_two_per_basket_with_sizing():
    d = run_live_flow(_strat(), _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                      today=ROT_DAY, portfolio_value=5000)
    assert d.is_rotation_day
    entered = {b.symbol for b in d.rotation_entries}
    # Her sepetten en yüksek momentumlu 2 sembol
    assert entered == {"SPY", "XLU", "NVDA", "AMD", "IONQ", "RGTI"}
    for b in d.rotation_entries:
        assert b.shares > 0 and b.value > 0 and b.price > 0


def test_rotation_entries_respect_cooldown_block():
    cd = AlertCooldown(cooldown_days=5)
    # NVDA'yı bloke et: high_vol top-2 AMD + SMCI olmalı
    # today_index = son işlem günü indeksi (bugüne kadar) -> blok bugünü kapsasın
    today_index = len([d for d in INDEX if d <= ROT_DAY]) - 1
    cd.register("NVDA", today_index)
    d = run_live_flow(_strat(), _bars(), holdings=[], cooldown=cd,
                      today=ROT_DAY, portfolio_value=5000)
    entered = {b.symbol for b in d.rotation_entries}
    assert "NVDA" not in entered
    assert {"AMD", "SMCI"} <= entered


def test_rotation_exit_reason_is_rank_drop():
    # SMCI elde ama hedef değil (high_vol top-2 NVDA,AMD) -> çıkış önerisi
    holdings = [_holding("SMCI", "high_volatility", entry_price=100, shares=5)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=ROT_DAY, portfolio_value=5000)
    exits = {e.symbol: e for e in d.rotation_exits}
    assert "SMCI" in exits
    assert "sıra düşüşü" in exits["SMCI"].reason


# ---------------------------------------------------------------------------
#  Rotasyon-dışı gün
# ---------------------------------------------------------------------------
def test_non_rotation_day_no_rotation_but_has_observation():
    d = run_live_flow(_strat(), _bars(), holdings=[_holding("SPY", "low_volatility", 100, 2)],
                      cooldown=AlertCooldown(cooldown_days=5), today=NON_ROT_DAY,
                      portfolio_value=5000)
    assert not d.is_rotation_day
    assert d.rotation_entries == []
    assert d.observation is not None
    # SPY portföyde -> gözlemde güncel sırası görünür
    assert "SPY" in d.observation.portfolio_ranks


def test_non_rotation_day_slot_fill_for_short_basket():
    # low_volatility'de yalnız SPY tutuluyor (2 slottan 1 boş) -> XLU önerilmeli
    holdings = [_holding("SPY", "low_volatility", 100, 2)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, portfolio_value=5000)
    fills = {b.symbol for b in d.slot_fills}
    assert "XLU" in fills            # low_vol'ün en yüksek portföy-dışı adayı
    for b in d.slot_fills:
        assert b.shares >= 0


def test_slot_fill_excludes_cooldown_blocked_symbol():
    cd = AlertCooldown(cooldown_days=5)
    today_index = len([d for d in INDEX if d <= NON_ROT_DAY]) - 1
    cd.register("XLU", today_index)   # XLU beklemede -> aday olamaz
    holdings = [_holding("SPY", "low_volatility", 100, 2)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=cd,
                      today=NON_ROT_DAY, portfolio_value=5000)
    fills = {b.symbol for b in d.slot_fills}
    assert "XLU" not in fills
    assert "XLP" in fills             # sıradaki uygun aday


# ---------------------------------------------------------------------------
#  Satış-uyarısı taraması
# ---------------------------------------------------------------------------
def test_technical_emergency_triggers_and_arms_cooldown():
    cd = AlertCooldown(cooldown_days=5)
    # entry_price çok yüksek -> current << entry - 3*ATR -> teknik acil
    holdings = [_holding("SPY", "low_volatility", entry_price=10000, shares=1)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=cd,
                      today=NON_ROT_DAY, portfolio_value=5000)
    alerts = {a.symbol: a for a in d.sell_alerts}
    assert "SPY" in alerts
    assert any(t.type is TriggerType.TECHNICAL for t in alerts["SPY"].triggers)
    assert "SPY" in d.newly_cooled
    # cooldown bugünden itibaren SPY'ı bloklamalı
    today_index = len([x for x in INDEX if x <= NON_ROT_DAY]) - 1
    assert cd.is_blocked("SPY", today_index)


def test_ranking_collapse_persist_fires_for_persistently_low_symbol():
    # cutoff küçült: per_basket cutoff = multiple × positions_per_basket = 1×2 = 2
    strat = _strat(ranking_collapse_multiple=1)
    # XLP low_vol'de sepet-içi 3. (rank 3 > 2), momentum sabit -> persist boyunca çökük
    holdings = [_holding("XLP", "low_volatility", entry_price=100, shares=5),
                _holding("SPY", "low_volatility", entry_price=100, shares=5)]
    d = run_live_flow(strat, _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, portfolio_value=5000)
    alerts = {a.symbol: a for a in d.sell_alerts}
    assert "XLP" in alerts
    assert any(t.type is TriggerType.RANKING for t in alerts["XLP"].triggers)
    # SPY sepet-içi 1. -> çöküş yok
    assert "SPY" not in alerts


def test_healthy_portfolio_has_no_sell_alerts():
    holdings = [_holding("SPY", "low_volatility", entry_price=100, shares=2),
                _holding("NVDA", "high_volatility", entry_price=100, shares=2)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, portfolio_value=5000)
    assert d.sell_alerts == []
    assert d.newly_cooled == set()
