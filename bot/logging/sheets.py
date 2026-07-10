"""Google Sheets loglama (Service Account ile).

Loglananlar:
  - Üretilen her sinyal (Signals sekmesi)
  - Gerçekleştirilen/geçilen işlemler (Trades sekmesi)
  - Portföy performansı (Performance sekmesi)

Kimlik doğrulama: lokal geliştirmede service_account.json dosyası,
GitHub Actions'ta GOOGLE_SERVICE_ACCOUNT_JSON secret'ı kullanılır.
"""
from __future__ import annotations

from ..config import Secrets
from ..models import Signal


class SheetsLogger:
    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets
        # TODO(adım 6): gspread ile service account yetkilendirmesi

    def log_signals(self, signals: list[Signal]) -> None:
        """Üretilen sinyalleri 'Signals' sekmesine ekle."""
        raise NotImplementedError("Adım 6'da doldurulacak")

    def get_open_positions(self) -> list[dict]:
        """'Trades' sekmesinden açık pozisyonları oku (stop-loss kontrolü için)."""
        raise NotImplementedError("Adım 6'da doldurulacak")

    def log_performance(self, snapshot: dict) -> None:
        """Günlük portföy performans anlık görüntüsünü ekle."""
        raise NotImplementedError("Adım 6'da doldurulacak")
