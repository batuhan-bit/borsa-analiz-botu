"""Perplexity istemcisi parse testleri — ağ gerektirmez (_ask mocklanır)."""
from __future__ import annotations

from bot.config import Secrets
from bot.data.perplexity_client import PerplexityClient


def _client() -> PerplexityClient:
    return PerplexityClient(Secrets.load(strict=False))


def test_parses_score_and_summary(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_ask", lambda symbol: "SKOR: 0.42\nÖZET: Güçlü kazanç beklentisi var.")
    result = c.get_web_sentiment("AAPL")
    assert result["score"] == 0.42
    assert result["summary"] == "Güçlü kazanç beklentisi var."


def test_score_clipped_to_range(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_ask", lambda symbol: "SKOR: 5.0\nÖZET: Aşırı iyimser")
    result = c.get_web_sentiment("AAPL")
    assert result["score"] == 1.0


def test_negative_score_parsed(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_ask", lambda symbol: "SKOR: -0.30\nÖZET: Olumsuz haberler")
    result = c.get_web_sentiment("AAPL")
    assert result["score"] == -0.30


def test_malformed_response_returns_none_not_raise(monkeypatch):
    c = _client()
    monkeypatch.setattr(c, "_ask", lambda symbol: "Üzgünüm, bu konuda bilgim yok.")
    result = c.get_web_sentiment("AAPL")
    assert result["score"] is None
    assert result["summary"] is None
