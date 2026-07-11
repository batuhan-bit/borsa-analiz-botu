"""Sinyal motoru birim testleri — ağ/anahtar gerektirmez."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bot.config import Strategy
from bot.models import Basket, SignalType
from bot.risk.risk_manager import check_stop_loss
from bot.signals.fundamental import (
    fundamental_score,
    parse_analyst_upside,
    parse_earnings_surprise,
    parse_news_sentiment,
)
from bot.signals.technical import compute_indicators, technical_score

TECH_CFG = Strategy.load().technical
FUND_CFG = Strategy.load().fundamental


# --------------------------- teknik skor ---------------------------

def test_technical_score_strong_bullish():
    ind = {
        "rsi": 25,                 # aşırı satım -> boğa
        "macd": 1.0, "macd_prev": -0.5,        # yukarı kesişim
        "macd_signal": 0.5, "macd_signal_prev": 0.0,
        "ma_short": 110, "ma_short_prev": 99,  # altın çaprazı
        "ma_long": 100, "ma_long_prev": 100,
        "volume_ratio": 2.0,       # hacim teyidi
    }
    score, reasons = technical_score(ind, TECH_CFG)
    assert score > 0.7
    assert any("Altın çaprazı" in r for r in reasons)
    assert any("aşırı satım" in r for r in reasons)


def test_technical_score_strong_bearish():
    ind = {
        "rsi": 80,                 # aşırı alım -> ayı
        "macd": -1.0, "macd_prev": 0.5,        # aşağı kesişim
        "macd_signal": -0.5, "macd_signal_prev": 0.0,
        "ma_short": 90, "ma_short_prev": 101,  # ölüm çaprazı
        "ma_long": 100, "ma_long_prev": 100,
        "volume_ratio": 2.0,
    }
    score, reasons = technical_score(ind, TECH_CFG)
    assert score < -0.7
    assert any("Ölüm çaprazı" in r for r in reasons)


def test_technical_score_empty_indicators():
    assert technical_score({}, TECH_CFG) == (0.0, [])


def test_compute_indicators_on_uptrend():
    # 260 günlük hafif yukarı trend + gürültü (200G MA için yeterli)
    n = 260
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0.3, 1.0, n))
    idx = pd.bdate_range("2023-01-01", periods=n)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, n)},
        index=idx,
    )
    ind = compute_indicators(df, TECH_CFG)
    assert ind["n_bars"] == n
    assert ind["ma_long"] is not None          # 200G hesaplanabildi
    assert ind["ma_short"] > ind["ma_long"]    # yukarı trend
    assert ind["rsi"] is not None


# --------------------------- temel skor ---------------------------

def test_fundamental_score_positive():
    data = {
        "news_sentiment_score": 0.30,       # güçlü pozitif
        "earnings_surprise_pct": 8.0,       # +%8 sürpriz
        "analyst_target_upside_pct": 20.0,  # +%20 potansiyel
    }
    score, reasons = fundamental_score(data, FUND_CFG)
    assert score > 0.5
    assert len(reasons) == 3


def test_fundamental_score_empty():
    assert fundamental_score({}, FUND_CFG) == (0.0, [])


def test_fundamental_score_includes_web_sentiment():
    data = {"web_sentiment_score": 0.5}
    score, reasons = fundamental_score(data, FUND_CFG)
    assert score == pytest.approx(0.5)
    assert any("Marketaux" in r for r in reasons)


def test_fundamental_score_flags_source_disagreement():
    # AV pozitif (+0.30/0.35≈+0.86 norm), Marketaux net negatif (-0.5) -> çelişki
    data = {"news_sentiment_score": 0.30, "web_sentiment_score": -0.5}
    _, reasons = fundamental_score(data, FUND_CFG)
    assert any("çelişkili" in r for r in reasons)


def test_fundamental_score_no_disagreement_when_aligned():
    data = {"news_sentiment_score": 0.20, "web_sentiment_score": 0.5}
    _, reasons = fundamental_score(data, FUND_CFG)
    assert not any("çelişkili" in r for r in reasons)


def test_parse_news_sentiment():
    resp = {
        "feed": [
            {"ticker_sentiment": [
                {"ticker": "AAPL", "ticker_sentiment_score": "0.4"},
                {"ticker": "MSFT", "ticker_sentiment_score": "-0.2"},
            ]},
            {"ticker_sentiment": [
                {"ticker": "AAPL", "ticker_sentiment_score": "0.2"},
            ]},
        ]
    }
    assert parse_news_sentiment(resp, "AAPL") == pytest.approx(0.3)  # (0.4 + 0.2)/2
    assert parse_news_sentiment(resp, "TSLA") is None


def test_parse_earnings_and_upside():
    assert parse_earnings_surprise({"quarterlyEarnings": [{"surprisePercentage": "5.5"}]}) == 5.5
    assert parse_earnings_surprise({}) is None
    assert parse_analyst_upside({"AnalystTargetPrice": "120"}, 100.0) == 20.0
    assert parse_analyst_upside({"AnalystTargetPrice": "none"}, 100.0) is None


# --------------------------- stop-loss ---------------------------

def test_stop_loss_triggers_at_threshold():
    sig = check_stop_loss("XYZ", Basket.HIGH_VOLATILITY, entry_price=100, current_price=79, stop_loss_pct=20)
    assert sig is not None
    assert sig.signal is SignalType.STOP_LOSS


def test_stop_loss_not_triggered():
    assert check_stop_loss("XYZ", Basket.HIGH_VOLATILITY, entry_price=100, current_price=85, stop_loss_pct=20) is None
