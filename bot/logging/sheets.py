"""Google Sheets loglama (Service Account ile).

Üç sekme yönetilir:
  - Sinyaller  : bot'un ürettiği her sinyal (bot yazar)
  - Pozisyonlar: açık pozisyonlar (kullanıcı manuel doldurur; bot stop-loss için okur)
  - Performans : günlük portföy anlık görüntüsü (bot yazar)

Kimlik doğrulama: lokalde service_account.json dosyası, GitHub Actions'ta
GOOGLE_SERVICE_ACCOUNT_JSON secret'ı. Kimlik/Sheet ID yoksa modül devre dışı
kalır (uyarı verip atlar) — böylece pipeline çökmez.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from ..config import Secrets
from ..models import Signal

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SIGNAL_HEADERS = ["Zaman", "Sembol", "Sepet", "Sinyal", "Skor", "Fiyat", "Gerekçeler"]
POSITION_HEADERS = ["Sembol", "Sepet", "Giriş Tarihi", "Giriş Fiyatı", "Adet", "Durum"]
PERFORMANCE_HEADERS = [
    "Tarih", "Portföy Değeri", "Açık Pozisyon", "Üretilen Sinyal", "Alış", "Satış", "Stop-Loss",
]


def _to_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


class SheetsLogger:
    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets
        self._sheet = None            # tembel açılır
        self._connect_failed = False

    # --- Bağlantı ---
    def _credentials(self):
        """Service account kimlik bilgisini dosya veya JSON string'ten üret."""
        from google.oauth2.service_account import Credentials

        if self._secrets.google_service_account_json:
            info = json.loads(self._secrets.google_service_account_json)
            return Credentials.from_service_account_info(info, scopes=SCOPES)

        path = Path(self._secrets.google_service_account_file)
        if path.exists():
            return Credentials.from_service_account_file(str(path), scopes=SCOPES)

        return None

    def _get_sheet(self):
        """Spreadsheet'i tembel aç; kimlik/ID yoksa None (devre dışı)."""
        if self._sheet is not None or self._connect_failed:
            return self._sheet

        if not self._secrets.google_sheet_id:
            log.warning("GOOGLE_SHEET_ID boş — Sheets loglama devre dışı.")
            self._connect_failed = True
            return None

        try:
            import gspread

            creds = self._credentials()
            if creds is None:
                log.warning("Google service account kimliği bulunamadı — Sheets loglama devre dışı.")
                self._connect_failed = True
                return None
            client = gspread.authorize(creds)
            self._sheet = client.open_by_key(self._secrets.google_sheet_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("Google Sheets bağlantısı kurulamadı: %s", exc)
            self._connect_failed = True
            return None
        return self._sheet

    def _worksheet(self, title: str, headers: list[str]):
        """Sekmeyi getir; yoksa başlık satırıyla oluştur."""
        sheet = self._get_sheet()
        if sheet is None:
            return None

        import gspread

        try:
            return sheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = sheet.add_worksheet(title=title, rows=1000, cols=max(len(headers), 8))
            ws.append_row(headers, value_input_option="USER_ENTERED")
            return ws

    # --- Yazma / okuma ---
    def log_signals(self, signals: list[Signal]) -> None:
        """Üretilen sinyalleri 'Sinyaller' sekmesine ekle."""
        if not signals:
            return
        ws = self._worksheet("Sinyaller", SIGNAL_HEADERS)
        if ws is None:
            return
        rows = [s.to_row() for s in signals]
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info("%d sinyal Sheets'e loglandı.", len(rows))

    def get_open_positions(self) -> list[dict]:
        """'Pozisyonlar' sekmesinden açık pozisyonları oku (stop-loss için).

        'Durum' sütunu KAPALI/CLOSED olmayan satırlar açık kabul edilir.
        """
        ws = self._worksheet("Pozisyonlar", POSITION_HEADERS)
        if ws is None:
            return []
        positions = []
        for r in ws.get_all_records():
            status = str(r.get("Durum", "")).strip().upper()
            if status in ("KAPALI", "CLOSED"):
                continue
            symbol = str(r.get("Sembol", "")).strip().upper()
            if not symbol:
                continue
            positions.append({
                "symbol": symbol,
                "basket": str(r.get("Sepet", "")).strip(),
                "entry_date": r.get("Giriş Tarihi"),
                "entry_price": _to_float(r.get("Giriş Fiyatı")),
                "shares": _to_float(r.get("Adet")),
                "status": status or "OPEN",
            })
        return positions

    def log_performance(self, snapshot: dict) -> None:
        """Günlük portföy performans anlık görüntüsünü 'Performans' sekmesine ekle."""
        ws = self._worksheet("Performans", PERFORMANCE_HEADERS)
        if ws is None:
            return
        row = [
            snapshot.get("date", ""),
            snapshot.get("portfolio_value", ""),
            snapshot.get("open_positions", ""),
            snapshot.get("signals", ""),
            snapshot.get("buy", ""),
            snapshot.get("sell", ""),
            snapshot.get("stop_loss", ""),
        ]
        ws.append_row(row, value_input_option="USER_ENTERED")
        log.info("Performans anlık görüntüsü Sheets'e loglandı.")
