"""Marketaux parse testleri — ağ gerektirmez."""
from __future__ import annotations

import pytest

from bot.signals.fundamental import parse_marketaux_sentiment


def test_parse_marketaux_sentiment_averages_matching_entities():
    resp = {
        "data": [
            {"entities": [
                {"symbol": "AAPL", "sentiment_score": 0.4},
                {"symbol": "MSFT", "sentiment_score": -0.2},
            ]},
            {"entities": [
                {"symbol": "AAPL", "sentiment_score": 0.2},
            ]},
        ]
    }
    assert parse_marketaux_sentiment(resp, "AAPL") == pytest.approx(0.3)  # (0.4+0.2)/2
    assert parse_marketaux_sentiment(resp, "TSLA") is None


def test_parse_marketaux_sentiment_no_articles():
    assert parse_marketaux_sentiment({"data": []}, "AAPL") is None
    assert parse_marketaux_sentiment({}, "AAPL") is None


def test_parse_marketaux_sentiment_malformed_entity():
    resp = {"data": [{"entities": [{"symbol": "AAPL", "sentiment_score": "abc"}]}]}
    assert parse_marketaux_sentiment(resp, "AAPL") is None
