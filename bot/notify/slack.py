"""Slack Incoming Webhook bildirimi.

Günde 1 kez, piyasa kapanışı sonrası üretilen sinyalleri okunabilir bir
mesaj olarak Slack'e gönderir. STOP_LOSS sinyalleri belirgin şekilde
vurgulanır.
"""
from __future__ import annotations

import requests

from ..models import Signal


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def format_message(self, signals: list[Signal]) -> dict:
        """Sinyal listesini Slack mesaj gövdesine (blocks) çevir."""
        raise NotImplementedError("Adım 5'te doldurulacak")

    def send(self, signals: list[Signal]) -> None:
        """Sinyalleri Slack webhook'una gönder."""
        raise NotImplementedError("Adım 5'te doldurulacak")
