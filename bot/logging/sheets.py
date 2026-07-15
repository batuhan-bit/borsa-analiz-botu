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
# Cooldown durumu (Görev C.1): satış-uyarısıyla kapanan sembolün yeniden-giriş
# beklemesi koşular arası kalıcı olsun (GitHub Actions stateless). Tarih çıpalı
# saklanır (bkz. bot/rotation/cooldown_store.py).
COOLDOWN_HEADERS = ["Sembol", "Uyarı Tarihi", "Bekleme (işlem günü)"]
# Karne (Görev C.2): sinyal takibi + 5/20/60g ileri getiri + sistem/sistem-dışı.
KARNE_HEADERS = [
    "Sinyal Tarihi", "Sembol", "Tür", "Kaynak", "Sinyal Fiyatı",
    "5g Getiri %", "20g Getiri %", "60g Getiri %",
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

    # --- Cooldown durumu (Görev C.1 — koşular arası kalıcı) ---
    def read_cooldown_state(self) -> dict[str, str]:
        """'Cooldown' sekmesinden {sembol: uyarı_tarihi_iso} oku (yoksa {})."""
        ws = self._worksheet("Cooldown", COOLDOWN_HEADERS)
        if ws is None:
            return {}
        out: dict[str, str] = {}
        for r in ws.get_all_records():
            sym = str(r.get("Sembol", "")).strip().upper()
            when = str(r.get("Uyarı Tarihi", "")).strip()
            if sym and when:
                out[sym] = when
        return out

    def write_cooldown_state(self, state: dict, cooldown_days: int) -> None:
        """'Cooldown' sekmesini bekleyen sembollerle tamamen yeniden yaz.

        state: {sembol: date/iso}. Tüm sekme temizlenip yeniden yazılır (yalnız
        hâlâ bekleyen semboller tutulur — depo küçük kalır).
        """
        ws = self._worksheet("Cooldown", COOLDOWN_HEADERS)
        if ws is None:
            return
        ws.clear()
        rows = [COOLDOWN_HEADERS]
        for sym in sorted(state):
            d = state[sym]
            iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
            rows.append([sym, iso, cooldown_days])
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        log.info("Cooldown durumu Sheets'e yazıldı (%d sembol).", len(state))

    # --- Karne (Görev C.2 — sinyal takibi + ileri getiri, tam yeniden yazım) ---
    def read_karne(self) -> list[dict]:
        """'Karne' sekmesindeki tüm satırları ham sözlük olarak oku (yoksa [])."""
        ws = self._worksheet("Karne", KARNE_HEADERS)
        if ws is None:
            return []
        return list(ws.get_all_records())

    def write_karne(self, rows: list[list]) -> None:
        """'Karne' sekmesini başlık + verilen satırlarla tamamen yeniden yaz.

        rows: her biri KARNE_HEADERS sırasında bir liste. İleri getiriler koşular
        arası dolduğu için sekme her koşuda güncel değerlerle yeniden yazılır.
        """
        ws = self._worksheet("Karne", KARNE_HEADERS)
        if ws is None:
            return
        ws.clear()
        ws.append_rows([KARNE_HEADERS] + rows, value_input_option="USER_ENTERED")
        log.info("Karne Sheets'e yazıldı (%d satır).", len(rows))

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
