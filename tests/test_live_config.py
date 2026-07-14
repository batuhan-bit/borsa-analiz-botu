"""Canlı konfigürasyonun Faz B kazananına eşit olduğunu doğrular (Faz C kararı).

Bağlayıcı karar: canlı varsayılanlar = results/competition_winner.json
(s2_momentum · per_basket · N=6 · biweekly · rejim KAPALI). Bu test, birisi
strategy.yaml'daki kazanan parametrelerini elle değiştirirse (yeniden doğrulama
yapmadan) kırmızıya döner — dönem-ayrımı disiplininin canlı bekçisidir.
"""
from __future__ import annotations

import json
from pathlib import Path

from bot.config import Strategy

ROOT = Path(__file__).resolve().parent.parent
WINNER_PATH = ROOT / "results" / "competition_winner.json"


def _winner() -> dict:
    with open(WINNER_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["winner"]


def test_live_rotation_matches_competition_winner():
    winner = _winner()
    rot = Strategy.load().rotation
    assert rot.get("score") == winner["score"]
    assert rot.get("selection") == winner["selection"]
    assert int(rot.get("top_n")) == int(winner["top_n"])
    assert rot.get("frequency") == winner["frequency"]


def test_live_regime_is_off():
    """Kazanan rejim KAPALI; canlı akışta rejim anahtarı devrede olmamalı."""
    winner = _winner()
    assert winner["regime"] is False
    # rotation_backtest.regime.enabled canlı varsayılanda da kapalı kalır
    # (canlı akış rejim-bazlı dağıtım düşürmesi uygulamaz).
    strat = Strategy.load()
    assert bool(strat.rotation_backtest.get("regime", {}).get("enabled", False)) is False
