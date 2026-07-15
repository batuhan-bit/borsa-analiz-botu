"""Google Sheets loglama testleri — ağ/kimlik gerektirmez.

Kimlik bilgisi olmadan modül devre dışı kalmalı ve hiçbir metod çökmemeli.
"""
from __future__ import annotations

from bot.config import Secrets
from bot.logging.sheets import (
    SIGNAL_HEADERS,
    SheetsLogger,
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
