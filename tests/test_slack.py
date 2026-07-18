"""Slack v2 rotasyon biçimlendirme — snapshot testli (Görev C.1). Ağ gerektirmez.

Altın dosyalar tests/snapshots/*.json. Biçim değişirse test kırılır; kasıtlı
değişiklikte dosyalar yeniden üretilir (scratchpad/gen_golden.py deseni).
v1 eşik BUY/SELL/HOLD biçiminin TAMAMEN kaldırıldığı da doğrulanır.
"""
from __future__ import annotations

import json
from pathlib import Path

from bot.notify import SlackNotifier
from tests.slack_fixtures import rotation_decision, summary_decision, watch_decision

SNAP = Path(__file__).resolve().parent / "snapshots"


def _texts(payload) -> str:
    parts = [payload["text"]]
    for b in payload["blocks"]:
        if "text" in b and isinstance(b["text"], dict):
            parts.append(b["text"]["text"])
        for el in b.get("elements", []):
            parts.append(el.get("text", ""))
    return "\n".join(parts)


def _golden(name: str) -> dict:
    with open(SNAP / f"{name}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_rotation_day_matches_snapshot():
    payload = SlackNotifier("http://x").format_message(rotation_decision())
    assert payload == _golden("slack_rotation_day")


def test_watch_day_matches_snapshot():
    payload = SlackNotifier("http://x").format_message(watch_decision())
    assert payload == _golden("slack_watch_day")


def test_monthly_summary_matches_snapshot():
    payload = SlackNotifier("http://x").format_message(summary_decision())
    assert payload == _golden("slack_monthly_summary")


def test_monthly_summary_renders_portfolio_spy_universe():
    blob = _texts(SlackNotifier("http://x").format_message(summary_decision()))
    assert "AYLIK KARNE" in blob
    assert "Portföy %+3.10" in blob and "SPY %+1.80" in blob and "Evren al-tut %+2.40" in blob


def test_no_monthly_summary_block_when_absent():
    blob = _texts(SlackNotifier("http://x").format_message(rotation_decision()))
    assert "AYLIK KARNE" not in blob      # summary None -> blok yok (snapshot korunur)


def test_rotation_message_has_entries_exits_and_money():
    blob = _texts(SlackNotifier("http://x").format_message(rotation_decision()))
    assert "ROTASYON GÜNÜ" in blob
    assert "GİREN" in blob and "ÇIKAN" in blob
    assert "💰" in blob and "$1,000.00" in blob      # sizing görünür
    assert "sıra düşüşü" in blob                      # çıkan gerekçesi
    assert "Kalan (2)" in blob


def test_watch_day_has_slot_fill_and_observation_no_rotation():
    blob = _texts(SlackNotifier("http://x").format_message(watch_decision()))
    assert "İzleme" in blob
    assert "SLOT DOLDURMA" in blob
    assert "Günlük gözlem" in blob
    assert "GİREN" not in blob and "ÇIKAN" not in blob


def test_no_v1_threshold_language_anywhere():
    """v1 eşik BUY/SELL/HOLD biçimi tamamen kaldırıldı — hiçbir izi kalmamalı."""
    for dec in (rotation_decision(), watch_decision()):
        blob = _texts(SlackNotifier("http://x").format_message(dec))
        for banned in ("ALIŞ SİNYALLERİ", "SATIŞ SİNYALLERİ", "ACİL SATIŞ (stop-loss)",
                       "R/R", "stop-loss", "buy_threshold", "Bekle ("):
            assert banned not in blob, f"v1 dili sızdı: {banned!r}"


def test_read_warning_rendered_at_top_when_present():
    """Okunamayan pozisyon satırı varsa uyarı mesajın EN ÜSTÜNDE (özetten önce)."""
    dec = rotation_decision()
    dec.read_warnings = ["satır 3 (BAD): Adet='1.2,3' — belirsiz"]
    dec.suppress_suggestions = True
    dec.rotation_entries = []
    dec.rotation_exits = []
    payload = SlackNotifier("http://x").format_message(dec)
    # header (0) hemen ardından uyarı bloğu (1) gelmeli; özet (2) ondan sonra
    assert payload["blocks"][0]["type"] == "header"
    warn_block = payload["blocks"][1]["text"]["text"]
    assert "pozisyon satırı okunamadı" in warn_block
    assert "satır 3 (BAD)" in warn_block and "1.2,3" in warn_block
    assert "bastırıldı" in warn_block
    # özet bloğu uyarıdan SONRA gelir (uyarı en üstte)
    assert "satış uyarısı" in payload["blocks"][2]["text"]["text"]


def test_no_read_warning_block_when_absent():
    """Uyarı yoksa yeni blok eklenmez (mevcut snapshot'lar korunur)."""
    blob = _texts(SlackNotifier("http://x").format_message(rotation_decision()))
    assert "okunamadı" not in blob


def test_block_and_section_limits_respected():
    dec = rotation_decision()
    # Çok sayıda uzun uyarı -> chunking ve blok limiti devrede
    long = "çok uzun gerekçe " * 40
    from bot.rotation.alerts import SellAlert, SellTrigger, TriggerType
    dec.sell_alerts = [SellAlert(f"S{i}", [SellTrigger(TriggerType.TECHNICAL, long)], i)
                       for i in range(120)]
    payload = SlackNotifier("http://x").format_message(dec)
    assert len(payload["blocks"]) <= 49
    for b in payload["blocks"]:
        if b.get("type") == "section":
            assert len(b["text"]["text"]) <= 3000
