"""Finnhub istemcisi ve parse testleri — ağ gerektirmez."""
from __future__ import annotations

import pytest

from bot.signals.fundamental import parse_finnhub_sentiment


def test_parse_finnhub_sentiment_bullish():
    resp = {"sentiment": {"bullishPercent": 0.8, "bearishPercent": 0.2}, "symbol": "AAPL"}
    assert parse_finnhub_sentiment(resp) == pytest.approx(0.6)


def test_parse_finnhub_sentiment_bearish():
    resp = {"sentiment": {"bullishPercent": 0.1, "bearishPercent": 0.9}, "symbol": "XYZ"}
    assert parse_finnhub_sentiment(resp) == pytest.approx(-0.8)


def test_parse_finnhub_sentiment_missing_fields():
    assert parse_finnhub_sentiment({"symbol": "AAPL"}) is None
    assert parse_finnhub_sentiment({}) is None


def test_parse_finnhub_sentiment_malformed_values():
    resp = {"sentiment": {"bullishPercent": "abc", "bearishPercent": 0.2}}
    assert parse_finnhub_sentiment(resp) is None
