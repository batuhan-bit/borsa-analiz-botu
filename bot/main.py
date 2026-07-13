"""Uçtan uca giriş noktası — GitHub Actions bunu günlük çalıştırır.

Akış:
  1. Konfigürasyonu yükle (sırlar + strateji)
  2. Açık pozisyonları Sheets'ten oku
  3. Sinyal motorunu çalıştır — SELL yalnızca portföydeki semboller için
  4. Açık pozisyonlar için stop-loss kontrolü
  5. Sinyalleri Google Sheets'e logla + performans anlık görüntüsü
  6. Slack'e günlük bildirim gönder

Kullanım:
    python -m bot.main
"""
from __future__ import annotations

import logging
from datetime import date

from .config import Settings
from .logging import SheetsLogger
from .models import Basket, SignalType
from .notify import SlackNotifier
from .risk.risk_manager import check_stop_loss
from .signals import SignalEngine
from .signals.sizing import portfolio_equity, suggested_position

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def _safe_basket(value: str) -> Basket:
    try:
        return Basket(value)
    except ValueError:
        return Basket.LOW_VOLATILITY


def _stop_loss_signals(positions, engine, stop_loss_pct):
    """Verilen açık pozisyonların fiyatlarını çek, stop-loss + portföy değeri hesapla.

    Döndürür: (stop_loss_sinyalleri, portföy_değeri, açık_pozisyon_sayısı).
    """
    stop_signals = []
    holdings_value = 0.0
    invested_cost = 0.0
    for pos in positions:
        price = engine.latest_price(pos["symbol"])
        if price is None:
            continue
        if pos.get("shares"):
            holdings_value += pos["shares"] * price
            if pos.get("entry_price"):
                invested_cost += pos["shares"] * pos["entry_price"]
        if pos.get("entry_price"):
            sl = check_stop_loss(
                pos["symbol"], _safe_basket(pos["basket"]),
                pos["entry_price"], price, stop_loss_pct,
            )
            if sl is not None:
                stop_signals.append(sl)
    return stop_signals, holdings_value, len(positions), invested_cost


def _attach_sizing(signals, settings, holdings_value: float, invested_cost: float,
                   free_cash=None) -> None:
    """BUY sinyallerine Sheets özsermayesinden 'önerilen tutar/adet' ekle.

    Özsermaye = güncel pozisyon değeri + serbest nakit. free_cash Sheets'teki
    NAKİT satırından gelirse kesin; yoksa budget_max çıpalı tahmin (bkz.
    sizing.portfolio_equity). v2 kuralı: hedef ağırlık × özsermaye;
    fractional_shares config'ine saygılı.
    """
    portfolio = settings.strategy.portfolio
    baskets = settings.strategy.baskets
    sizing_cfg = portfolio.get("sizing", {}) or {}
    budget_max = portfolio.get("budget_max", 0)
    ppb = int(portfolio.get("positions_per_basket", 1))
    equity = portfolio_equity(holdings_value, invested_cost, budget_max, free_cash)

    for sig in signals:
        if sig.signal is not SignalType.BUY:
            continue
        basket_cfg = baskets.get(sig.basket.value, {})
        alloc = basket_cfg.get("allocation_pct", 0)
        suggestion = suggested_position(equity, sig.price, alloc, ppb, sizing_cfg,
                                        free_cash=free_cash)
        if suggestion:
            sig.sizing = suggestion


def _format_sizing(sz: dict) -> str:
    """Öneri sözlüğünü tek satırlık okunur metne çevir."""
    capped = sz.get("cash_capped")
    if not sz.get("affordable"):
        reason = "serbest nakit 1 hisseye yetmiyor" if capped else "1 hisse hedefi aşıyor"
        return (f"💰 Öneri: ~${sz['amount']:,.0f} hedef (%{sz['weight_pct']:g} ağırlık) — "
                f"{reason}, atlanabilir")
    shares = sz["shares"]
    shares_txt = f"{shares:g}" if sz.get("fractional") else f"{int(shares)}"
    limit = " · serbest nakitle sınırlı" if capped else ""
    return (f"💰 Öneri: ~${sz['amount']:,.0f} (%{sz['weight_pct']:g} ağırlık{limit}) → "
            f"{shares_txt} adet ≈ ${sz['cost']:,.0f}")


def _print_summary(signals) -> None:
    """Sinyalleri konsola özetle (loglara ek görünürlük)."""
    order = {SignalType.STOP_LOSS: 0, SignalType.BUY: 1, SignalType.SELL: 2, SignalType.HOLD: 3}
    for sig in sorted(signals, key=lambda s: (order.get(s.signal, 9), -s.score)):
        reasons = "; ".join(sig.reasons) if sig.reasons else "-"
        print(f"  {sig.signal.value:9} {sig.symbol:6} [{sig.basket.value:15}] "
              f"skor={sig.score:.2f} ${sig.price:.2f}  {reasons}")
        lv = sig.levels
        if lv:
            rr = f" R/R={lv['risk_reward']}" if lv.get("risk_reward") else ""
            print(f"            🎯 stop=${lv['stop']} destek=${lv['support']} "
                  f"hedef=${lv['target1']}→${lv['target2']}{rr}")
        for note in sig.notes:
            print(f"            {note}")
        if sig.sizing:
            print(f"            {_format_sizing(sig.sizing)}")


def main() -> None:
    settings = Settings.load(strict=True)
    log.info("Bot başlatıldı. Hedef getiri: %%%s", settings.strategy.portfolio["target_return_pct"])

    sec = settings.secrets
    log.info(
        "Entegrasyonlar — Alpaca: %s | Alpha Vantage: %s | Google Sheets: %s",
        "açık" if sec.alpaca_api_key else "KAPALI (yfinance'e düşülüyor)",
        "açık" if sec.alpha_vantage_api_key else "KAPALI (yalnızca teknik)",
        "açık" if sec.google_sheet_id else "KAPALI (loglama yok)",
    )

    engine = SignalEngine(settings)
    logger = SheetsLogger(settings.secrets)
    stop_loss_pct = settings.strategy.risk["position_stop_loss_pct"]

    # Açık pozisyonları bir kez oku — hem SELL filtresi hem stop-loss için
    positions = logger.get_open_positions()
    held_symbols = {str(p["symbol"]).strip().upper() for p in positions if p.get("symbol")}
    if held_symbols:
        log.info("Portföydeki semboller (SELL yalnızca bunlar için): %s", ", ".join(sorted(held_symbols)))

    # 2. Sinyal üretimi — SELL yalnızca portföydeki semboller için üretilir
    signals = engine.run(held_symbols=held_symbols)

    # 3. Stop-loss kontrolü (açık pozisyonlar) — en öne alınır
    stop_signals, portfolio_value, open_count, invested_cost = _stop_loss_signals(
        positions, engine, stop_loss_pct)
    signals = stop_signals + signals
    log.info("%d sinyal (%d stop-loss dahil).", len(signals), len(stop_signals))

    # 3b. BUY sinyallerine önerilen tutar/adet ekle (Sizing v2, ayrı iş).
    #     Serbest nakit Sheets 'Pozisyonlar' sekmesindeki NAKİT satırından okunur.
    free_cash = logger.get_free_cash()
    _attach_sizing(signals, settings, portfolio_value, invested_cost, free_cash)

    # 4. Sheets loglama + performans
    logger.log_signals(signals)
    counts = {t: sum(1 for s in signals if s.signal is t) for t in SignalType}
    logger.log_performance({
        "date": date.today().isoformat(),
        "portfolio_value": round(portfolio_value, 2),
        "open_positions": open_count,
        "signals": len(signals),
        "buy": counts[SignalType.BUY],
        "sell": counts[SignalType.SELL],
        "stop_loss": counts[SignalType.STOP_LOSS],
    })

    _print_summary(signals)

    # 5. Slack bildirimi (webhook yoksa güvenle atlanır)
    SlackNotifier(settings.secrets.slack_webhook_url).send(signals)


if __name__ == "__main__":
    main()
