"""Uçtan uca giriş noktası — GitHub Actions bunu günlük çalıştırır.

Akış:
  1. Konfigürasyonu yükle (sırlar + strateji)
  2. Sinyal motorunu çalıştır (tüm sepetleri tara)
  3. Açık pozisyonlar için stop-loss kontrolü yap        (adım 6'da Sheets'e bağlanacak)
  4. Sinyalleri Google Sheets'e logla                     (adım 6)
  5. Slack'e günlük bildirim gönder                       (adım 5)

Kullanım:
    python -m bot.main
"""
from __future__ import annotations

import logging

from .config import Settings
from .signals import SignalEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def _print_summary(signals) -> None:
    """Slack/Sheets bağlanana kadar sinyalleri konsola özetle."""
    from .models import SignalType

    order = {SignalType.STOP_LOSS: 0, SignalType.BUY: 1, SignalType.SELL: 2, SignalType.HOLD: 3}
    for sig in sorted(signals, key=lambda s: (order.get(s.signal, 9), -s.score)):
        reasons = "; ".join(sig.reasons) if sig.reasons else "-"
        print(f"  {sig.signal.value:9} {sig.symbol:6} [{sig.basket.value:15}] "
              f"skor={sig.score:.2f} ${sig.price:.2f}  {reasons}")


def main() -> None:
    settings = Settings.load(strict=True)
    log.info("Bot başlatıldı. Hedef getiri: %%%s", settings.strategy.portfolio["target_return_pct"])

    engine = SignalEngine(settings)
    signals = engine.run()
    log.info("%d sinyal üretildi.", len(signals))

    # TODO(adım 6): stop-loss kontrolü — açık pozisyonları Sheets'ten oku
    # TODO(adım 6): SheetsLogger(settings.secrets).log_signals(signals)
    # TODO(adım 5): SlackNotifier(settings.secrets.slack_webhook_url).send(signals)

    _print_summary(signals)


if __name__ == "__main__":
    main()
