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
# Portföy nakitteyken kullanıcı 'Pozisyonlar'a bilgi amaçlı bir NAKİT satırı girer;
# serbest nakit USD tutarı bu satırın 'Giriş Fiyatı' hücresinde tutulur (sizing tabanı).
# Türkçe 'İ' büyük harfi ile ASCII 'I' (küçük 'i'.upper()) farkını tolere etmek için
# iki biçim de kabul edilir.
CASH_ROW_LABELS = {"NAKİT", "NAKIT"}
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


class NumberParseError(ValueError):
    """Sheets hücresindeki sayı okunamadı — satır atlanmalı ve uyarı üretilmeli.

    reason: 'belirsiz' (hem nokta hem virgül var — ondalık/binlik ayırıcı
    ayırt edilemez) veya 'geçersiz' (sayıya çevrilemez metin).
    """

    def __init__(self, raw: Any, reason: str) -> None:
        self.raw = raw
        self.reason = reason
        super().__init__(f"{reason}: {raw!r}")


def _parse_number(value: Any) -> Optional[float]:
    """Türkçe ondalık toleransıyla sayı ayrıştır.

    - Boş/None → None (sorun değil; sayı girilmemiş).
    - "70,16" → 70.16 (virgül ondalık ayracı kabul edilir).
    - Hem "." hem "," içeren değer BELİRSİZDİR (ör. "1.234,56" mi 1.23456 mı?):
      tahmin yürütmek yerine NumberParseError('belirsiz') fırlatılır → satır atlanır.
    - Sayıya çevrilemeyen metin → NumberParseError('geçersiz').
    """
    if value in (None, ""):
        return None
    text = str(value).strip()
    if text == "":
        return None
    if "." in text and "," in text:
        raise NumberParseError(text, "belirsiz")
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        raise NumberParseError(text, "geçersiz")


def _to_float(value: Any) -> Optional[float]:
    """Geriye dönük yumuşak ayrıştırıcı: hata/boşta sessizce None döner.

    Sessiz-veri-kaybı önemli olan yerlerde (pozisyon/NAKİT okuma) doğrudan
    _parse_number kullanılıp NumberParseError yakalanır; bu sarmalayıcı yalnız
    hatanın önemsiz olduğu yerler içindir.
    """
    try:
        return _parse_number(value)
    except NumberParseError:
        return None


class SheetsLogger:
    def __init__(self, secrets: Secrets) -> None:
        self._secrets = secrets
        self._sheet = None            # tembel açılır
        self._connect_failed = False
        # Son okuma sırasında ayrıştırılamayan satırların uyarıları (satır no +
        # sorunlu değer). Sessiz-veri-kaybı koruması: çağıran (main) bunları
        # Slack mesajının en üstüne taşır ve öneri üretimini bastırır.
        self.position_warnings: list[str] = []
        self.cash_warnings: list[str] = []

    @property
    def read_warnings(self) -> list[str]:
        """Son pozisyon/NAKİT okumasında biriken tüm ayrıştırma uyarıları."""
        return list(self.position_warnings) + list(self.cash_warnings)

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
        Kullanıcı, portföy tamamen nakitteyken bilgi amaçlı bir "NAKİT" satırı
        girebilir (Adet/Giriş Tarihi boş) — bu gerçek bir pozisyon değildir,
        bu yüzden Adet'i pozitif olmayan (boş/0/NaN) satırlar en başta atlanır.
        """
        self.position_warnings = []
        ws = self._worksheet("Pozisyonlar", POSITION_HEADERS)
        if ws is None:
            return []
        positions = []
        # get_all_records başlık satırını atlar; ilk veri satırı sayfada 2. satırdır.
        for row_no, r in enumerate(ws.get_all_records(), start=2):
            status = str(r.get("Durum", "")).strip().upper()
            if status in ("KAPALI", "CLOSED"):
                continue
            symbol = str(r.get("Sembol", "")).strip().upper()
            if not symbol:
                continue
            if symbol in CASH_ROW_LABELS:
                # NAKİT satırı gerçek pozisyon değildir (serbest nakit taşıyıcısı);
                # Adet hücresine yanlışlıkla sayı yazılsa bile pozisyon sayılmaz.
                continue
            # Adet ayrıştırılamıyorsa satırı SESSİZCE atlamayız: kullanıcı gerçek bir
            # pozisyon girmiş ama sayı bozuk — bu satır uyarıya dönüşür (aşağıda
            # rotasyon önerisini de bastırır). Boş/0 Adet (NAKİT benzeri) uyarısızdır.
            try:
                shares = _parse_number(r.get("Adet"))
            except NumberParseError as exc:
                self.position_warnings.append(
                    f"satır {row_no} ({symbol}): Adet={exc.raw!r} — {exc.reason}")
                continue
            if not shares or shares <= 0:
                continue
            try:
                entry_price = _parse_number(r.get("Giriş Fiyatı"))
            except NumberParseError as exc:
                self.position_warnings.append(
                    f"satır {row_no} ({symbol}): Giriş Fiyatı={exc.raw!r} — {exc.reason}")
                continue
            positions.append({
                "symbol": symbol,
                "basket": str(r.get("Sepet", "")).strip(),
                "entry_date": r.get("Giriş Tarihi"),
                "entry_price": entry_price,
                "shares": shares,
                "status": status or "OPEN",
            })
        return positions

    def get_free_cash(self) -> float:
        """'Pozisyonlar' NAKİT satırından serbest nakit (USD) oku (yoksa 0.0).

        Kullanıcı, serbest nakit USD tutarını NAKİT satırının 'Giriş Fiyatı'
        hücresine yazar (ör. 1000). Bu, canlı sizing tabanına beslenir:
        capital = açık pozisyon değeri + serbest nakit. Nakit, boş slotlara hedef
        sepet ağırlıklarına göre PRO-RATA dağıtılır (bkz. bot.rotation.live).
        Satır yoksa/boşsa 0.0 döner (sizing budget_max fallback'ine düşer).
        """
        self.cash_warnings = []
        ws = self._worksheet("Pozisyonlar", POSITION_HEADERS)
        if ws is None:
            return 0.0
        for row_no, r in enumerate(ws.get_all_records(), start=2):
            if str(r.get("Sembol", "")).strip().upper() in CASH_ROW_LABELS:
                try:
                    return _parse_number(r.get("Giriş Fiyatı")) or 0.0
                except NumberParseError as exc:
                    # NAKİT tutarı okunamazsa sessizce 0'a düşmek sizing tabanını
                    # sessizce bozardı — uyarı üret (öneri bastırma tetiklenir).
                    self.cash_warnings.append(
                        f"NAKİT satırı (satır {row_no}): Giriş Fiyatı={exc.raw!r} — {exc.reason}")
                    return 0.0
        return 0.0

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
