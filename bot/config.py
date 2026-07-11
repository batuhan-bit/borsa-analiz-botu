"""Konfigürasyon yükleme: ortam değişkenleri (.env) + strateji YAML.

Sırlar (API anahtarları) ortam değişkenlerinden, strateji parametreleri
config/strategy.yaml dosyasından okunur. İki kaynak da tek bir Settings
nesnesinde toplanır.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Proje kök dizini (bu dosya bot/ altında)
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STRATEGY_PATH = ROOT / "config" / "strategy.yaml"

# .env dosyasını yükle (varsa). GitHub Actions'ta env'ler zaten set olacağı
# için dosya olmasa da sorun değil.
load_dotenv(ROOT / ".env")


def _require(name: str) -> str:
    """Zorunlu bir ortam değişkenini oku; yoksa açıklayıcı hata ver."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Zorunlu ortam değişkeni eksik: {name}. "
            f".env dosyanızı veya GitHub Secrets ayarını kontrol edin."
        )
    return value


@dataclass(frozen=True)
class Secrets:
    """API anahtarları ve kimlik bilgileri (ortam değişkenlerinden)."""

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_data_url: str
    alpha_vantage_api_key: str
    slack_webhook_url: str
    google_service_account_file: str
    google_service_account_json: str
    google_sheet_id: str

    @classmethod
    def load(cls, *, strict: bool = False) -> "Secrets":
        """Ortam değişkenlerinden sırları yükle.

        strict=True ise yalnızca GERÇEKTEN zorunlu değişkenlerde hata verir.
        Zorunlu tek şey SLACK_WEBHOOK_URL'dir (botun tek çıktısı bildirim).
        Diğer tüm entegrasyonlar zarifçe devre dışı kalabilir:
          - Alpaca yoksa  -> yfinance'e düşülür (anahtar gerekmez)
          - Alpha Vantage yoksa -> yalnızca teknik analiz
          - Google Sheets yoksa -> loglama/stop-loss atlanır
        Böylece bir sağlayıcıdaki kesinti (ör. Alpaca) botu durdurmaz.
        """
        req = _require if strict else (lambda n: os.getenv(n, ""))

        def opt(name: str, default: str = "") -> str:
            return os.getenv(name, default)

        return cls(
            alpaca_api_key=opt("ALPACA_API_KEY"),
            alpaca_secret_key=opt("ALPACA_SECRET_KEY"),
            alpaca_data_url=opt("ALPACA_DATA_URL", "https://data.alpaca.markets"),
            alpha_vantage_api_key=opt("ALPHA_VANTAGE_API_KEY"),
            slack_webhook_url=req("SLACK_WEBHOOK_URL"),
            google_service_account_file=opt("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"),
            google_service_account_json=opt("GOOGLE_SERVICE_ACCOUNT_JSON"),
            google_sheet_id=opt("GOOGLE_SHEET_ID"),
        )


@dataclass(frozen=True)
class Strategy:
    """config/strategy.yaml içeriğini saran ince bir sarmalayıcı."""

    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str = DEFAULT_STRATEGY_PATH) -> "Strategy":
        with open(path, "r", encoding="utf-8") as f:
            return cls(raw=yaml.safe_load(f))

    # Kolay erişim için kısayollar
    @property
    def portfolio(self) -> dict[str, Any]:
        return self.raw["portfolio"]

    @property
    def baskets(self) -> dict[str, Any]:
        return self.raw["baskets"]

    @property
    def technical(self) -> dict[str, Any]:
        return self.raw["technical"]

    @property
    def fundamental(self) -> dict[str, Any]:
        return self.raw["fundamental"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.raw["risk"]

    @property
    def notification(self) -> dict[str, Any]:
        return self.raw["notification"]

    @property
    def backtest(self) -> dict[str, Any]:
        return self.raw["backtest"]


@dataclass(frozen=True)
class Settings:
    """Sırlar + strateji tek bir yerde."""

    secrets: Secrets
    strategy: Strategy

    @classmethod
    def load(cls, *, strict: bool = False, strategy_path: Path | str = DEFAULT_STRATEGY_PATH) -> "Settings":
        return cls(
            secrets=Secrets.load(strict=strict),
            strategy=Strategy.load(strategy_path),
        )


if __name__ == "__main__":
    # Hızlı doğrulama: strateji dosyası okunuyor mu?
    s = Strategy.load()
    print("Sepetler:", list(s.baskets.keys()))
    print("Hedef getiri (%):", s.portfolio["target_return_pct"])
