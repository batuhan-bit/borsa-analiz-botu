"""Deterministik LiveDecision örnekleri — Slack snapshot testleri + altın dosya üretimi.

Hem tests/test_slack.py hem altın-dosya üreticisi bu SAME kurucuları kullanır;
böylece snapshot ile test aynı girdiden doğar.
"""
from __future__ import annotations

from datetime import date

from bot.rotation.alerts import SellAlert, SellTrigger, TriggerType
from bot.rotation.live import BuySuggestion, ExitSuggestion, LiveDecision, RebalanceNote
from bot.rotation.slots import Observation, RankMover


def rotation_decision() -> LiveDecision:
    return LiveDecision(
        as_of=date(2026, 7, 1), frequency="biweekly", is_rotation_day=True,
        sell_alerts=[SellAlert("SMCI", [SellTrigger(
            TriggerType.RANKING, "Sıralama #7 — ilk 6 dışına düştü (ay sonu beklenmez)")],
            current_rank=7)],
        rotation_entries=[BuySuggestion(
            "SPY", "low_volatility", "broad_market", 0.2, 500.0, 2.0, 1000.0, 1,
            "yeni giren (sıra #1)")],
        rotation_exits=[ExitSuggestion(
            "SMCI", "high_volatility", 7,
            "sıra düşüşü — hedef portföy dışı (güncel sıra #7)")],
        rotation_holds=["NVDA", "AMD"],
        rebalance_notes=[RebalanceNote("NVDA", "azalt", 0.25, 0.175, 42.9)],
        observation=Observation(top_movers=[RankMover("IONQ", 12, 8, 4)],
                                portfolio_ranks={"NVDA": 2, "AMD": 3}),
    )


def watch_decision() -> LiveDecision:
    return LiveDecision(
        as_of=date(2026, 7, 8), frequency="biweekly", is_rotation_day=False,
        sell_alerts=[],
        slot_fills=[BuySuggestion(
            "XLU", "low_volatility", "utilities", 0.2, 80.0, 12.0, 960.0, 4,
            "boşalan low_volatility slotu için en yüksek uygun aday (sırada #4)")],
        observation=Observation(top_movers=[], portfolio_ranks={"SPY": 1}),
    )
