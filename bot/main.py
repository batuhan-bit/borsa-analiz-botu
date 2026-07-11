"""Uçtan uca giriş noktası — GitHub Actions bunu günlük çalıştırır.

Akış:
  1. Konfigürasyonu yükle (sırlar + strateji)
  2. Sinyal motorunu çalıştır (tüm sepetleri tara)
  3. Açık pozisyonlar için stop-loss kontrolü (Sheets'ten okunan pozisyonlar)
  4. Sinyalleri Google Sheets'e logla + performans anlık görüntüsü
  5. Slack'e günlük bildirim gönder

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def _safe_basket(value: str) -> Basket:
    try:
        return Basket(value)
    except ValueError:
        return Basket.LOW_VOLATILITY


def _stop_loss_signals(engine, logger, stop_loss_pct):
    """Açık pozisyonları oku, fiyatlarını çek, stop-loss + portföy değeri hesapla.

    Döndürür: (stop_loss_sinyalleri, portföy_değeri, açık_pozisyon_sayısı).
    """
    positions = logger.get_open_positions()
    stop_signals = []
    holdings_value = 0.0
    for pos in positions:
        price = engine.latest_price(pos["symbol"])
        if price is None:
            continue
        if pos.get("shares"):
            holdings_value += pos["shares"] * price
        if pos.get("entry_price"):
            sl = check_stop_loss(
                pos["symbol"], _safe_basket(pos["basket"]),
                pos["entry_price"], price, stop_loss_pct,
            )
            if sl is not None:
                stop_signals.append(sl)
    return stop_signals, holdings_value, len(positions)


def _print_summary(signals) -> None:
    """Sinyalleri konsola özetle (loglara ek görünürlük)."""
    order = {SignalType.STOP_LOSS: 0, SignalType.BUY: 1, SignalType.SELL: 2, SignalType.HOLD: 3}
    for sig in sorted(signals, key=lambda s: (order.get(s.signal, 9), -s.score)):
        reasons = "; ".join(sig.reasons) if sig.reasons else "-"
        print(f"  {sig.signal.value:9} {sig.symbol:6} [{sig.basket.value:15}] "
              f"skor={sig.score:.2f} ${sig.price:.2f}  {reasons}")


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

    # 2. Sinyal üretimi
    signals = engine.run()

    # 3. Stop-loss kontrolü (açık pozisyonlar) — en öne alınır
    stop_signals, portfolio_value, open_count = _stop_loss_signals(engine, logger, stop_loss_pct)
    signals = stop_signals + signals
    log.info("%d sinyal (%d stop-loss dahil).", len(signals), len(stop_signals))

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
