"""Slack biçimlendirme testleri — ağ gerektirmez (send çağrılmaz)."""
from __future__ import annotations

from datetime import date

from bot.models import Basket, Signal, SignalType
from bot.notify import SlackNotifier


def _sig(symbol, stype, score=0.5, basket=Basket.HIGH_VOLATILITY, reasons=None):
    return Signal(symbol, basket, stype, score, 100.0, reasons=reasons or ["gerekçe"])


def _texts(payload) -> str:
    """Tüm blok metinlerini tek stringde topla (arama kolaylığı için)."""
    parts = [payload["text"]]
    for b in payload["blocks"]:
        if "text" in b and isinstance(b["text"], dict):
            parts.append(b["text"]["text"])
        for el in b.get("elements", []):
            parts.append(el.get("text", ""))
    return "\n".join(parts)


def test_message_has_header_and_counts():
    signals = [
        _sig("AAA", SignalType.BUY),
        _sig("BBB", SignalType.SELL),
        _sig("CCC", SignalType.STOP_LOSS),
        _sig("DDD", SignalType.HOLD),
    ]
    payload = SlackNotifier("http://x").format_message(signals, on_date=date(2026, 7, 11))
    blob = _texts(payload)
    assert "2026-07-11" in blob
    assert "1 acil satış" in blob and "1 alış" in blob and "1 satış" in blob and "1 bekle" in blob
    # Kategoriler görünüyor
    assert "ACİL SATIŞ" in blob and "ALIŞ SİNYALLERİ" in blob and "SATIŞ SİNYALLERİ" in blob
    # Semboller
    assert "AAA" in blob and "CCC" in blob


def test_holds_are_summarized_not_listed_individually():
    signals = [_sig(f"H{i}", SignalType.HOLD) for i in range(20)]
    payload = SlackNotifier("http://x").format_message(signals)
    blob = _texts(payload)
    assert "Bekle (20)" in blob
    # Her HOLD için ayrı section açılmamalı (blok sayısı makul)
    assert len(payload["blocks"]) < 10


def test_empty_signals_still_valid():
    payload = SlackNotifier("http://x").format_message([])
    assert payload["blocks"][0]["type"] == "header"
    assert "0 alış" in _texts(payload)


def test_block_and_section_limits_respected():
    # Çok sayıda uzun gerekçeli BUY -> chunking ve blok limiti devrede
    long_reason = "çok uzun bir gerekçe metni " * 20
    signals = [_sig(f"S{i}", SignalType.BUY, reasons=[long_reason]) for i in range(120)]
    payload = SlackNotifier("http://x").format_message(signals)
    assert len(payload["blocks"]) <= 49
    for b in payload["blocks"]:
        if b.get("type") == "section":
            assert len(b["text"]["text"]) <= 3000
