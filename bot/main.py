"""Uçtan uca giriş noktası — GitHub Actions (daily.yml) bunu günlük çalıştırır.

FAZ C: v1 eşik motoru EMEKLİ (bkz. bot.legacy_engine). Bu akış artık v2 kesitsel
momentum ROTASYONUNU çalıştırır — Faz B'nin doğrulanmış kazananı
(results/competition_winner.json: s2_momentum · per_basket · N=6 · biweekly).

Akış:
  1. Konfigürasyon + fiyat geçmişini yükle (yfinance, evren).
  2. Açık pozisyonları Sheets'ten oku (icra manuel — yalnız okunur).
  3. Cooldown durumunu Sheets'ten yükle → AlertCooldown'ı yeniden kur (koşular arası
     kalıcı yeniden-giriş beklemesi; GitHub Actions stateless).
  4. Günlük kararı üret (bot.rotation.live.run_live_flow): satış-uyarısı taraması +
     slot doldurma + günlük gözlem; rotasyon günü ek olarak rotasyon önerisi.
  5. Güncellenen cooldown durumunu Sheets'e geri yaz.
  6. Slack'e v2 rotasyon bildirimi gönder.

Kullanım:
    python -m bot.main
"""
from __future__ import annotations

import logging

import pandas as pd

from .config import Settings
from .data import YFinanceClient
from .logging import SheetsLogger
from .notify import SlackNotifier
from .reporting import entry_to_row, monthly_summary, update_karne
from .rotation import run_live_flow
from .rotation.cooldown_store import (
    SheetsCooldownStore,
    active_cooldown_dates,
    reconstruct_cooldown,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def _load_bars(strategy, years: float) -> dict[str, pd.DataFrame]:
    """Evrendeki her sembol için günlük (ayarlı) barları yfinance'ten çek."""
    yf = YFinanceClient()
    bars: dict[str, pd.DataFrame] = {}
    for sym in strategy.universe_symbols:
        df = yf.get_daily_bars(sym, years=years)
        if not df.empty:
            bars[sym] = df
    return bars


def _calendar(bars: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    if not bars:
        return []
    idx = pd.DatetimeIndex(sorted(set().union(*[set(df.index) for df in bars.values()])))
    return list(idx)


def _print_summary(decision) -> None:
    """Kararı konsola özetle (loglara ek görünürlük)."""
    print(f"\n📅 {decision.as_of} — "
          f"{'ROTASYON GÜNÜ' if decision.is_rotation_day else 'izleme günü'}")
    if decision.sell_alerts:
        print(f"🚨 Satış uyarıları ({len(decision.sell_alerts)}):")
        for a in decision.sell_alerts:
            trs = "; ".join(t.reason for t in a.triggers)
            print(f"   {a.symbol}: {trs}")
    if decision.is_rotation_day:
        print(f"🟢 Giren: {[b.symbol for b in decision.rotation_entries]}")
        print(f"🔴 Çıkan: {[e.symbol for e in decision.rotation_exits]}")
        print(f"⚪ Kalan: {decision.rotation_holds}")
    else:
        print(f"🟢 Slot adayları: {[b.symbol for b in decision.slot_fills]}")


def main() -> None:
    settings = Settings.load(strict=True)
    strategy = settings.strategy
    log.info("Bot başlatıldı (v2 rotasyon). Konfig: %s · %s · N=%s · %s",
             strategy.rotation.get("score"), strategy.rotation.get("selection"),
             strategy.rotation.get("top_n"), strategy.rotation.get("frequency"))

    sec = settings.secrets
    log.info(
        "Entegrasyonlar — Slack: %s | Google Sheets: %s",
        "açık" if sec.slack_webhook_url else "KAPALI",
        "açık" if sec.google_sheet_id else "KAPALI (loglama/cooldown kalıcılığı yok)",
    )

    # 1. Fiyat geçmişi
    years = float(strategy.rotation.get("live_history_years", 2))
    bars = _load_bars(strategy, years)
    log.info("%d/%d sembol yüklendi (%.0f yıl geçmiş).",
             len(bars), len(strategy.universe_symbols), years)

    # 2. Açık pozisyonlar (Sheets — icra manuel, yalnız okunur)
    logger = SheetsLogger(sec)
    holdings = logger.get_open_positions()
    if holdings:
        log.info("Portföy (%d): %s", len(holdings),
                 ", ".join(h["symbol"] for h in holdings))

    # 3. Cooldown durumu — koşular arası kalıcı; AlertCooldown'ı yeniden kur
    cooldown_days = int(strategy.raw.get("sell_alerts", {}).get("slot_refill_cooldown_days", 5))
    store = SheetsCooldownStore(logger, cooldown_days)
    stored = store.load()
    calendar = _calendar(bars)
    cooldown = reconstruct_cooldown(strategy, stored, calendar)

    # 4. Günlük karar (backtest ile aynı AlertCooldown + rank_fn deseni)
    decision = run_live_flow(strategy, bars, holdings, cooldown)

    # 5. Güncellenen cooldown durumunu geri yaz
    if decision.today_index >= 0:
        new_state = active_cooldown_dates(
            cooldown, stored, decision.newly_cooled, decision.as_of, decision.today_index)
        store.save(new_state)
        if decision.newly_cooled:
            log.info("Cooldown'a alınan (yeni): %s", ", ".join(sorted(decision.newly_cooled)))

    # 5b. Karne (Görev C.2): yeni sinyaller + sistem-dışı pozisyonlar + ileri getiri
    karne = update_karne(logger.read_karne(), decision, bars, holdings)
    logger.write_karne([entry_to_row(e) for e in karne])

    # 5c. Aylık özet (yalnız rotasyon günü) — portföy vs SPY vs evren al-tut
    if decision.is_rotation_day:
        decision.monthly_summary = monthly_summary(
            bars, holdings, strategy.universe_symbols, decision.as_of)
        log.info("Aylık özet: %s", decision.monthly_summary)

    _print_summary(decision)

    # 6. Slack v2 rotasyon bildirimi (webhook yoksa güvenle atlanır)
    SlackNotifier(sec.slack_webhook_url).send(decision)


if __name__ == "__main__":
    main()
