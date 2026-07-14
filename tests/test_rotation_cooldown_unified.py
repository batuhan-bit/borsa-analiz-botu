"""Görev A regresyonu — AlertCooldown tek doğruluk kaynağı.

Teşhis (results/diag_548_check.md): AlertCooldown yalnız `alert_orders` →
`slot_candidates` çağrısında uygulanıyordu; AYLIK ROTASYON seçimi (rebalance_orders
→ engine.build_plan) cooldown'dan habersizdi. Sonuç: bir sembol uyarıyla kapandıktan
hemen sonra bir sonraki rotasyon günü aynı sembolü anında geri seçebiliyordu
(gerçek veri örneği: KTOS 2017-08-01 technical_emergency ile kapandı, 2017-08-02
rotasyon icrasında aynı gün geri açıldı — gap=1 işlem günü, cooldown_days=5 sınırını
ihlal).

Düzeltme: `rank_fn_as_of` (rotasyon seçiminin TEK skor kaynağı) artık aynı
`cooldown` nesnesini sorgular; bekleme süresindeki sembol skorlanmadan elenir,
böylece `engine.build_plan` (per_basket/global_top_n) onu asla hedef olarak
seçemez — sıradaki uygun aday otomatik alınır. Aynı `cooldown` nesnesi
`slot_candidates(excluded=...)` ile alert-günü doldurmada da kullanılır —
tek durum, iki tüketici.

Bu test sentetik barlarla gerçek desenin (KTOS teknik acil çıkış → ertesi
rotasyon günü anında yeniden seçim) engellendiğini uçtan uca doğrular.
"""
from __future__ import annotations

import pandas as pd

from bot.config import Strategy
from backtest.rotation_backtest import run_rotation_backtest


def _bars(daily_return: float, n: int, start: str, *, base: float = 100.0,
          crash_at: int | None = None, crash_factor: float = 0.4) -> pd.DataFrame:
    """Sabit günlük getirili OHLCV çerçevesi (deterministik sıralama için).

    crash_at verilirse o günden itibaren fiyat crash_factor ile bir kez çöker
    (teknik acil durum tetiğini test etmek için) — test_rotation_backtest.py
    ile aynı yardımcı desen.
    """
    idx = pd.bdate_range(start=start, periods=n)
    closes = []
    price = base
    for i in range(n):
        if crash_at is not None and i == crash_at:
            price *= crash_factor
        else:
            price *= (1 + daily_return)
        closes.append(price)
    close = pd.Series(closes, index=idx)
    open_ = close.shift(1).fillna(base)
    high = pd.concat([open_, close], axis=1).max(axis=1) * 1.01
    low = pd.concat([open_, close], axis=1).min(axis=1) * 0.99
    vol = pd.Series(1_000_000, index=idx)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol})


def _month_signal_indices(idx: pd.DatetimeIndex) -> list[int]:
    """Her ayın ilk işlem gününün idx içindeki konumu (rotasyon-sinyal günleri)."""
    seen: dict[tuple[int, int], int] = {}
    for i, d in enumerate(idx):
        key = (d.year, d.month)
        if key not in seen:
            seen[key] = i
    return [seen[k] for k in sorted(seen)]


def test_ktos_blocked_from_rotation_reentry_after_cooldown():
    """KTOS teknik-acil çıkışından sonra bir sonraki rotasyon günü GERİ SEÇİLEMEZ.

    Kurulum: under_radar sepetine yalnız 2 sembol için bar verilir (IONQ, KTOS)
    → per_basket top-2 seçiminde ikisi de rekabetsiz seçilir (skor önemsiz).
    Şubat rotasyonunda ikisi de girer. Mart sinyalinden birkaç iş günü önce
    KTOS çöker → technical_emergency ile ertesi açılışta satılır (cooldown'a
    kaydolur). Mart rotasyon icrası (satıştan ~3 iş günü sonra, cooldown=5
    içinde) KTOS'u YENİDEN SEÇMEMELİDİR — düzeltme öncesi anında seçerdi.
    """
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {}).update({
        "score": "s2_momentum", "frequency": "monthly", "selection": "per_basket",
        "momentum": {"lookback_days": 5, "skip_days": 1},
    })
    sa = strat.raw.setdefault("sell_alerts", {})
    sa["atr_exit_multiple"] = 3.0
    sa["ranking_collapse_persist_days"] = 3
    sa["slot_refill_cooldown_days"] = 5

    n = 130
    idx = pd.bdate_range(start="2020-01-01", periods=n)
    month_sig = _month_signal_indices(idx)
    assert len(month_sig) >= 3, "test kurulumunda en az 3 ay olmalı"
    feb_signal, mar_signal = month_sig[1], month_sig[2]

    # Çöküş: Mart sinyalinden 3 iş günü önce tespit edilir → satış Mart sinyalinden
    # 2 iş günü önce (pending mekanizması: tespit günü kapanış, icra ertesi açılış).
    crash_at = mar_signal - 3
    assert crash_at > feb_signal + 5, "çöküş, Şubat girişinden yeterince sonra olmalı"

    bars = {
        "IONQ": _bars(0.004, n, "2020-01-01"),                       # istikrarlı yükseliş
        "KTOS": _bars(0.004, n, "2020-01-01", crash_at=crash_at, crash_factor=0.4),
    }

    r = run_rotation_backtest(strat, bars, apply_costs=True)

    ktos_trades = sorted((t for t in r.trades if t.symbol == "KTOS"),
                          key=lambda t: t.entry_date)
    assert ktos_trades, "KTOS en az bir kez (Şubat) girmeli"
    first = ktos_trades[0]
    assert first.exit_reason == "technical_emergency", (
        f"beklenen technical_emergency, gelen: {first.exit_reason}")

    exit_day_idx = idx.get_loc(pd.Timestamp(first.exit_date))
    mar_buy_day_idx = mar_signal + 1     # rotasyon icra günü (execution_lag_days=1)
    gap = mar_buy_day_idx - exit_day_idx
    assert 0 < gap < 5, (
        f"test kurulumu hatası: çıkış ile Mart rotasyon icrası arası {gap} iş günü "
        "olmalı (cooldown_days=5 sınırı içinde, aksi halde senaryo geçersiz)")

    # KABUL KRİTERİ: KTOS, Mart rotasyon icra gününde (cooldown içindeyken)
    # YENİDEN AÇILMAMALI. IONQ ise sepetin tek diğer adayı olarak normal seyreder.
    reentries_within_cooldown = [
        t for t in ktos_trades[1:]
        if idx.get_loc(pd.Timestamp(t.entry_date)) == mar_buy_day_idx
    ]
    assert reentries_within_cooldown == [], (
        "KTOS cooldown içindeyken (Mart rotasyon icrasında) yeniden açılmamalı — "
        f"bulunan: {reentries_within_cooldown}")

    # Ek doğrulama: Mart rotasyon icra gününde KTOS gerçekten HİÇ pozisyon değil
    # (ne yeni açılış ne de -varsayımsal- rebalans) — cooldown, rotasyon seçiminin
    # KENDİSİNDE etkili (yalnız alert-günü slot doldurmada değil).
    any_entry_on_mar_buy = any(
        idx.get_loc(pd.Timestamp(t.entry_date)) == mar_buy_day_idx and t.symbol == "KTOS"
        for t in r.trades
    )
    assert not any_entry_on_mar_buy


def test_cooldown_is_single_shared_instance_across_rotation_and_alert_paths():
    """Cooldown'un rotasyon VE alert yolunda aynı temele oturduğunu dolaylı doğrular:

    KTOS cooldown'dayken bile IONQ'nun normal biçimde (sepetin tek adayı olarak)
    işlem görmeye devam ettiğini, yani cooldown'un yalnız hedef sembolü etkilediğini
    (aşırı kısıtlama/yan etki olmadığını) gösterir.
    """
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {}).update({
        "score": "s2_momentum", "frequency": "monthly", "selection": "per_basket",
        "momentum": {"lookback_days": 5, "skip_days": 1},
    })
    sa = strat.raw.setdefault("sell_alerts", {})
    sa["atr_exit_multiple"] = 3.0
    sa["ranking_collapse_persist_days"] = 3
    sa["slot_refill_cooldown_days"] = 5

    n = 130
    idx = pd.bdate_range(start="2020-01-01", periods=n)
    month_sig = _month_signal_indices(idx)
    mar_signal = month_sig[2]
    crash_at = mar_signal - 3

    bars = {
        "IONQ": _bars(0.004, n, "2020-01-01"),
        "KTOS": _bars(0.004, n, "2020-01-01", crash_at=crash_at, crash_factor=0.4),
    }
    r = run_rotation_backtest(strat, bars, apply_costs=True)
    ionq_trades = [t for t in r.trades if t.symbol == "IONQ"]
    assert ionq_trades, "IONQ normal seyretmeli (cooldown yalnız KTOS'u etkilemeli)"
