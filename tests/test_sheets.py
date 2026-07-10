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
