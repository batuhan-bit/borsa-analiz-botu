"""Slack Incoming Webhook bildirimi.

Günde 1 kez, piyasa kapanışı sonrası üretilen sinyalleri okunabilir bir
Slack mesajına (Block Kit) çevirip webhook'a gönderir.

Öncelik sırası: STOP_LOSS (acil satış) → BUY → SELL → HOLD (özet).
Aksiyon gerektiren sinyaller tek tek listelenir; HOLD'lar tek satırda özetlenir.

format_message ağdan bağımsız test edilebilir; send yalnızca POST yapar.
"""
from __future__ import annotations

import logging
from datetime import date

import requests

from ..models import Signal, SignalType

log = logging.getLogger(__name__)

# Block Kit sınırları
_MAX_SECTION_CHARS = 2900   # section text limiti 3000; güvenli marj
_MAX_BLOCKS = 48            # limit 50; başlık/özet için pay bırak

_BASKET_LABEL = {
    "low_volatility": "Düşük Vol",
    "high_volatility": "Yüksek Vol",
    "under_radar": "Radar Altı",
}

_EMOJI = {
    SignalType.STOP_LOSS: "🚨",
    SignalType.BUY: "🟢",
    SignalType.SELL: "🔴",
    SignalType.HOLD: "⚪",
}


def _basket_label(value: str) -> str:
    return _BASKET_LABEL.get(value, value)


def _format_signal_line(sig: Signal) -> str:
    reasons = "; ".join(sig.reasons) if sig.reasons else "-"
    emoji = _EMOJI.get(sig.signal, "•")
    return (
        f"{emoji} *{sig.symbol}*  ${sig.price:,.2f}  "
        f"_(skor {sig.score:.2f}, {_basket_label(sig.basket.value)})_\n"
        f"      {reasons}"
    )


def _chunk_sections(lines: list[str]) -> list[dict]:
    """Satırları 3000 karakter sınırına uyacak şekilde section bloklarına böl."""
    blocks: list[dict] = []
    buffer = ""
    for line in lines:
        candidate = f"{buffer}\n{line}" if buffer else line
        if len(candidate) > _MAX_SECTION_CHARS:
            if buffer:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": buffer}})
            buffer = line
        else:
            buffer = candidate
    if buffer:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": buffer}})
    return blocks


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def format_message(self, signals: list[Signal], *, on_date: date | None = None) -> dict:
        """Sinyal listesini Slack mesaj gövdesine (blocks + fallback text) çevir."""
        on_date = on_date or date.today()

        by_type: dict[SignalType, list[Signal]] = {t: [] for t in SignalType}
        for sig in signals:
            by_type[sig.signal].append(sig)

        counts = {t: len(by_type[t]) for t in SignalType}

        header = f"📊 Günlük Borsa Analizi — {on_date.isoformat()}"
        summary = (
            f"🚨 {counts[SignalType.STOP_LOSS]} acil satış · "
            f"🟢 {counts[SignalType.BUY]} alış · "
            f"🔴 {counts[SignalType.SELL]} satış · "
            f"⚪ {counts[SignalType.HOLD]} bekle"
        )

        blocks: list[dict] = [
            {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
        ]

        # Aksiyon gerektiren kategoriler — öncelik sırasıyla, tek tek
        section_titles = {
            SignalType.STOP_LOSS: "*🚨 ACİL SATIŞ (stop-loss)*",
            SignalType.BUY: "*🟢 ALIŞ SİNYALLERİ*",
            SignalType.SELL: "*🔴 SATIŞ SİNYALLERİ*",
        }
        for stype, title in section_titles.items():
            items = sorted(by_type[stype], key=lambda s: s.score, reverse=True)
            if not items:
                continue
            blocks.append({"type": "divider"})
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": title}})
            lines = [_format_signal_line(s) for s in items]
            for block in _chunk_sections(lines):
                blocks.append(block)

        # HOLD'lar: tek satır özet (sembol listesi)
        holds = by_type[SignalType.HOLD]
        if holds:
            symbols = ", ".join(s.symbol for s in holds)
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f"⚪ *Bekle ({len(holds)}):* {symbols}"}],
            })

        # Manuel işlem hatırlatması
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "ℹ️ Bu sinyaller bilgi amaçlıdır; alım-satımı kendiniz yürütürsünüz.",
            }],
        })

        # Blok sınırını aşarsak kırp
        if len(blocks) > _MAX_BLOCKS:
            blocks = blocks[:_MAX_BLOCKS]
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": "… (mesaj kısaltıldı)"}],
            })

        return {"text": f"{header} — {summary}", "blocks": blocks}

    def send(self, signals: list[Signal], *, on_date: date | None = None) -> None:
        """Sinyalleri Slack webhook'una gönder."""
        if not self._webhook_url:
            log.warning("SLACK_WEBHOOK_URL boş — bildirim atlanıyor.")
            return
        payload = self.format_message(signals, on_date=on_date)
        resp = requests.post(self._webhook_url, json=payload, timeout=30)
        if resp.status_code != 200 or resp.text.strip().lower() != "ok":
            raise RuntimeError(f"Slack gönderimi başarısız: {resp.status_code} {resp.text[:200]}")
        log.info("Slack bildirimi gönderildi (%d sinyal).", len(signals))
