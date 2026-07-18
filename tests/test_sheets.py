"""Google Sheets loglama testleri — ağ/kimlik gerektirmez.

Kimlik bilgisi olmadan modül devre dışı kalmalı ve hiçbir metod çökmemeli.
"""
from __future__ import annotations

from bot.config import Secrets
import pytest

from bot.logging.sheets import (
    SIGNAL_HEADERS,
    NumberParseError,
    SheetsLogger,
    _parse_number,
    _to_float,
)
from bot.models import Basket, Signal, SignalType


def _disabled_logger() -> SheetsLogger:
    # strict=False -> tüm kimlik alanları boş -> devre dışı
    return SheetsLogger(Secrets.load(strict=False))


def test_disabled_get_open_positions_returns_empty():
    assert _disabled_logger().get_open_positions() == []


def test_disabled_log_signals_is_noop():
    sig = Signal("AAA", Basket.LOW_VOLATILITY, SignalType.BUY, 0.5, 100.0, reasons=["x"])
    # Çökmemeli, sessizce atlamalı
    _disabled_logger().log_signals([sig])


def test_disabled_log_performance_is_noop():
    _disabled_logger().log_performance({"date": "2026-07-11", "portfolio_value": 0})


def test_signal_row_matches_headers():
    sig = Signal("AAA", Basket.LOW_VOLATILITY, SignalType.BUY, 0.5, 100.0, reasons=["a", "b"])
    assert len(sig.to_row()) == len(SIGNAL_HEADERS)


def test_to_float_parsing():
    assert _to_float("12.5") == 12.5
    assert _to_float("1,5") == 1.5      # virgüllü ondalık
    assert _to_float("") is None
    assert _to_float(None) is None
    assert _to_float("abc") is None
    assert _to_float("1.234,56") is None  # belirsiz — yumuşak sarmalayıcı None döner


def test_parse_number_turkish_decimal():
    assert _parse_number("70,16") == 70.16      # virgül ondalık ayracı
    assert _parse_number("12.5") == 12.5
    assert _parse_number("  1000 ") == 1000.0
    assert _parse_number("") is None
    assert _parse_number(None) is None


def test_parse_number_ambiguous_raises():
    """Hem nokta hem virgül → belirsiz; tahmin yerine hata (satır atlanır)."""
    with pytest.raises(NumberParseError) as ei:
        _parse_number("1.234,56")
    assert ei.value.reason == "belirsiz"
    assert ei.value.raw == "1.234,56"


def test_parse_number_invalid_raises():
    with pytest.raises(NumberParseError) as ei:
        _parse_number("abc")
    assert ei.value.reason == "geçersiz"


class _FakeWorksheet:
    def __init__(self, records):
        self._records = records

    def get_all_records(self):
        return self._records


def test_get_open_positions_skips_cash_placeholder_row(monkeypatch):
    """'NAKİT' satırı (Adet/Giriş Tarihi boş) gerçek pozisyon değildir — atlanmalı.

    Regresyon: canlı akışta bu satır pozisyon sanılıp sayıya çevrilmeye
    çalışılınca 'cannot convert float NaN to integer' ile çöküyordu.
    """
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "NAKİT", "Sepet": "", "Giriş Tarihi": "", "Giriş Fiyatı": "", "Adet": "", "Durum": ""},
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "5", "Durum": ""},
    ]))
    positions = logger.get_open_positions()
    assert [p["symbol"] for p in positions] == ["AAA"]


def test_get_free_cash_reads_nakit_row_entry_price(monkeypatch):
    """Serbest nakit NAKİT satırının 'Giriş Fiyatı' hücresinden okunur (USD)."""
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "NAKİT", "Sepet": "", "Giriş Tarihi": "", "Giriş Fiyatı": "1000",
         "Adet": "", "Durum": ""},
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "5", "Durum": ""},
    ]))
    assert logger.get_free_cash() == 1000.0


def test_get_free_cash_zero_when_no_nakit_row(monkeypatch):
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "5", "Durum": ""},
    ]))
    assert logger.get_free_cash() == 0.0


def test_nakit_row_never_counts_as_position_even_with_shares(monkeypatch):
    """NAKİT satırına yanlışlıkla Adet yazılsa bile pozisyon sayılmamalı (isimle atlanır)."""
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "NAKİT", "Sepet": "", "Giriş Tarihi": "", "Giriş Fiyatı": "1000",
         "Adet": "1000", "Durum": ""},
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "5", "Durum": ""},
    ]))
    assert [p["symbol"] for p in logger.get_open_positions()] == ["AAA"]


def test_disabled_get_free_cash_returns_zero():
    assert _disabled_logger().get_free_cash() == 0.0


# --- Türkçe ondalık toleransı (virgüllü fiyat/adet/NAKİT) ---
def test_open_positions_accepts_turkish_decimal_price_and_shares(monkeypatch):
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "70,16", "Adet": "3,5", "Durum": ""},
    ]))
    positions = logger.get_open_positions()
    assert positions[0]["entry_price"] == 70.16
    assert positions[0]["shares"] == 3.5
    assert logger.read_warnings == []


def test_free_cash_accepts_turkish_decimal(monkeypatch):
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "NAKİT", "Sepet": "", "Giriş Tarihi": "", "Giriş Fiyatı": "1234,50",
         "Adet": "", "Durum": ""},
    ]))
    assert logger.get_free_cash() == 1234.50
    assert logger.cash_warnings == []


# --- Sessiz-veri-kaybı koruması: okunamayan satır uyarı üretir + atlanır ---
def test_ambiguous_price_skips_row_and_warns(monkeypatch):
    """'1.234,56' belirsizdir: satır sessizce yok sayılmaz, uyarı üretilir."""
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "BAD", "Sepet": "X", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "1.234,56", "Adet": "5", "Durum": ""},
        {"Sembol": "AAA", "Sepet": "Teknoloji", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "5", "Durum": ""},
    ]))
    positions = logger.get_open_positions()
    assert [p["symbol"] for p in positions] == ["AAA"]   # bozuk satır atlandı
    assert len(logger.position_warnings) == 1
    w = logger.position_warnings[0]
    assert "satır 2" in w and "BAD" in w and "1.234,56" in w   # satır no + sorunlu değer


def test_unparseable_shares_warns_not_silently_dropped(monkeypatch):
    """Adet sayı değilse satır SESSİZCE düşmemeli — uyarı üretilmeli."""
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "XYZ", "Sepet": "X", "Giriş Tarihi": "2026-01-01",
         "Giriş Fiyatı": "10.0", "Adet": "on adet", "Durum": ""},
    ]))
    assert logger.get_open_positions() == []
    assert len(logger.position_warnings) == 1
    assert "Adet" in logger.position_warnings[0] and "on adet" in logger.position_warnings[0]


def test_ambiguous_cash_warns_and_returns_zero(monkeypatch):
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "NAKİT", "Sepet": "", "Giriş Tarihi": "", "Giriş Fiyatı": "1.000,50",
         "Adet": "", "Durum": ""},
    ]))
    assert logger.get_free_cash() == 0.0
    assert len(logger.cash_warnings) == 1
    assert "NAKİT" in logger.cash_warnings[0] and "1.000,50" in logger.cash_warnings[0]


def test_position_warnings_reset_between_calls(monkeypatch):
    """Temiz okuma önceki uyarıları temizlemeli (koşular arası birikmez)."""
    logger = _disabled_logger()
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "BAD", "Sepet": "X", "Giriş Tarihi": "", "Giriş Fiyatı": "1.2,3",
         "Adet": "5", "Durum": ""},
    ]))
    logger.get_open_positions()
    assert logger.position_warnings
    monkeypatch.setattr(logger, "_worksheet", lambda title, headers: _FakeWorksheet([
        {"Sembol": "AAA", "Sepet": "X", "Giriş Tarihi": "", "Giriş Fiyatı": "10.0",
         "Adet": "5", "Durum": ""},
    ]))
    logger.get_open_positions()
    assert logger.position_warnings == []
