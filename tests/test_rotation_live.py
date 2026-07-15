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


def test_free_cash_shared_pro_rata_no_candidate_zero_rotation_day():
    """Regresyon: $1.000 serbest nakit + 6 boş slot → hiçbir aday $0 ALMAMALI.

    Kök neden (düzeltildi): canlı sizing gerçek nakdi okumayıp budget_max ($5.000)
    tahminine düşüyor, üstelik tam-sayı flooring küçük hedefleri $0'a yuvarlıyordu →
    yalnız ucuz bir sembol adet alıyor, kalanlar '💰 0 adet ≈ $0.00'. Beklenen:
    nakit hedef sepet ağırlıklarına (allocation/positions_per_basket) göre PRO-RATA
    paylaşılır ve toplam deployment_pct sınırını aşmaz.

    deployment_pct=95 KASITLI seçildi (config varsayılanı 100 DEĞİL): tavan $950,
    çarpansız sonuçtan (~$979) STRİKT düşük → deployment_pct pro-rata hesaba
    uygulanmazsa toplam $950'yi aşar ve test kırılır (çarpanın uygulandığını ispatlar).
    """
    strat = _strat()
    strat.rotation_backtest["deployment_pct"] = 95      # tavan $950 < çarpansız ~$979
    d = run_live_flow(strat, _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                      today=ROT_DAY, cash=1000.0)
    assert d.is_rotation_day
    assert len(d.rotation_entries) == 6            # 3 sepet × 2 pozisyon
    for b in d.rotation_entries:
        assert b.shares > 0, f"{b.symbol} sıfır adet aldı (nakit-tükenmesi/flooring)"
        assert b.value > 0, f"{b.symbol} ${0:.2f} tutar aldı"
    total = sum(b.value for b in d.rotation_entries)
    limit = 1000.0 * 95 / 100.0                    # = $950 tavan
    assert total <= limit + 1e-6, (
        f"toplam ${total:.2f} > deployment tavanı ${limit:.2f} "
        f"(deployment_pct pro-rata hesaba uygulanmıyor)")
    # Sermaye anlamlı ölçüde dağıtıldı (tek adaya yığılma / atıl nakit değil).
    assert total > 0.9 * limit, f"toplam ${total:.2f} deployment tavanının çok altında"


def test_free_cash_shared_pro_rata_no_candidate_zero_watch_day():
    """Aynı regresyon izleme (slot doldurma) yolunda: boş slotlar → aday başına >$0."""
    strat = _strat()
    # low_volatility'de yalnız SPY tutuluyor → 5 boş slot (low_vol 1 + high_vol 2 + under 2)
    holdings = [_holding("SPY", "low_volatility", 100, 2)]
    d = run_live_flow(strat, _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, cash=1000.0)
    assert not d.is_rotation_day
    assert d.slot_fills, "boş slotlar için aday üretilmedi"
    for b in d.slot_fills:
        assert b.shares > 0 and b.value > 0, f"{b.symbol} sıfır adet/tutar aldı"


def test_all_cash_start_ignores_budget_max_uses_free_cash():
    """all-cash başlangıçta sizing tabanı budget_max ($5.000) DEĞİL, serbest nakit olmalı.

    Aynı boş portföyü bir kez cash=1000, bir kez cash=budget_max ($5.000) ile koş;
    entry değerleri nakitle orantılı ölçeklenmeli (5×). Bu, 'budget_max fallback'
    gerçek nakit bilinirken devreye girerse kırılır.
    """
    strat = _strat()
    d1 = run_live_flow(strat, _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                       today=ROT_DAY, cash=1000.0)
    d5 = run_live_flow(strat, _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                       today=ROT_DAY, cash=5000.0)
    t1 = sum(b.value for b in d1.rotation_entries)
    t5 = sum(b.value for b in d5.rotation_entries)
    assert t1 <= 1000.0 + 1e-6 and t5 <= 5000.0 + 1e-6
    assert t5 > 4 * t1              # ~5× ölçek (flooring toleransıyla)


def test_deployment_pct_scales_pro_rata_total():
    """deployment_pct pro-rata toplamı DOĞRUDAN ölçekler: %50 tavan, %100'ün yarısı.

    Aynı nakit/portföyü iki deployment_pct ile koş; toplam oranı ≈ dp oranı olmalı.
    deployment çarpanı hiç uygulanmasa iki toplam eşit çıkar → test kırılır.
    """
    strat100 = _strat(); strat100.rotation_backtest["deployment_pct"] = 100
    strat50 = _strat(); strat50.rotation_backtest["deployment_pct"] = 50
    d100 = run_live_flow(strat100, _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                         today=ROT_DAY, cash=1000.0)
    d50 = run_live_flow(strat50, _bars(), holdings=[], cooldown=AlertCooldown(cooldown_days=5),
                        today=ROT_DAY, cash=1000.0)
    t100 = sum(b.value for b in d100.rotation_entries)
    t50 = sum(b.value for b in d50.rotation_entries)
    assert t100 <= 1000.0 + 1e-6 and t50 <= 500.0 + 1e-6
    # ~yarısı (flooring toleransıyla): 0.45–0.55 bandı
    assert 0.45 * t100 <= t50 <= 0.55 * t100, f"t50=${t50:.2f} t100=${t100:.2f} (deployment ölçeklemiyor)"


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


def test_slot_fill_handles_nan_close_without_crashing():
    """Adayın son kapanışı NaN ise (eksik/kısmi bar) çökmemeli, fiyat 0 sayılmalı.

    Regresyon: last_close NaN'ı None yerine olduğu gibi döndürüyordu; `nan or 0.0`
    NaN'ı gerçek (truthy) sayıp fallback'i atlıyor, `_size_buy` içinde
    math.floor(target_value / nan) 'cannot convert float NaN to integer' ile
    çöküyordu.
    """
    bars = _bars()
    bars["XLU"] = bars["XLU"].copy()
    bars["XLU"].loc[NON_ROT_DAY, "close"] = float("nan")
    holdings = [_holding("SPY", "low_volatility", 100, 2)]
    d = run_live_flow(_strat(), bars, holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, portfolio_value=5000)
    fills = {b.symbol: b for b in d.slot_fills}
    assert "XLU" in fills
    assert fills["XLU"].price == 0
    assert fills["XLU"].shares == 0


def test_healthy_portfolio_has_no_sell_alerts():
    holdings = [_holding("SPY", "low_volatility", entry_price=100, shares=2),
                _holding("NVDA", "high_volatility", entry_price=100, shares=2)]
    d = run_live_flow(_strat(), _bars(), holdings=holdings, cooldown=AlertCooldown(cooldown_days=5),
                      today=NON_ROT_DAY, portfolio_value=5000)
    assert d.sell_alerts == []
    assert d.newly_cooled == set()
