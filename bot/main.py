"""Uçtan uca giriş noktası — GitHub Actions bunu günlük çalıştırır.

Akış:
  1. Konfigürasyonu yükle (sırlar + strateji)
  2. Sinyal motorunu çalıştır (tüm sepetleri tara)
  3. Açık pozisyonlar için stop-loss kontrolü yap
  4. Sinyalleri Google Sheets'e logla
  5. Slack'e günlük bildirim gönder

Kullanım:
    python -m bot.main
"""
from __future__ import annotations

import logging

from .config import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")


def main() -> None:
    settings = Settings.load(strict=True)
    log.info("Bot başlatıldı. Hedef getiri: %%%s", settings.strategy.portfolio["target_return_pct"])

    # TODO(adım 3-6): aşağıdaki akışı bağla
    # engine = SignalEngine(settings)
    # signals = engine.run()
    # signals += stop_loss_checks(settings)
    # SheetsLogger(settings.secrets).log_signals(signals)
    # SlackNotifier(settings.secrets.slack_webhook_url).send(signals)

    raise NotImplementedError("Akış adım 3-6'da tamamlanacak")


if __name__ == "__main__":
    main()
