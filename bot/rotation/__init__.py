"""Rotasyon motoru (v2) — aylık kesitsel portföy rotasyonu.

v1'in eşik-tetiklemeli BUY/SELL motorunun yerini alır. Deterministiktir:
aynı veri + aynı tarih -> aynı hedef portföy. Modüller:
  - engine   : hedef portföy + fark (giren/çıkan/kalan) + rebalans (Görev A.1)
  - sizing   : ağırlık -> tutar/adet dönüşümü (Görev A.1)
  - scoring  : sıralama skorları S1/S2 (Görev A.2)
"""
from __future__ import annotations

from .alerts import (
    AlertCooldown,
    AlertLedger,
    RankingCollapseTracker,
    SellAlert,
    SellAlertEngine,
    SellTrigger,
    TriggerType,
    check_fundamental_red_flags,
    check_ranking_collapse,
    check_technical_emergency,
    collapse_cutoff,
    collapse_rank_map,
    compute_atr,
)
from .engine import (
    RebalanceAction,
    RotationEngine,
    RotationPlan,
    TargetPosition,
)
from .live import (
    BuySuggestion,
    ExitSuggestion,
    LiveDecision,
    RebalanceNote,
    run_live_flow,
)
from .scoring import (
    MomentumRanker,
    Ranker,
    TechnicalRanker,
    make_ranker,
)
from .calendar import is_rotation_day, rotation_days
from .cooldown_store import (
    CooldownStore,
    InMemoryCooldownStore,
    SheetsCooldownStore,
    active_cooldown_dates,
    reconstruct_cooldown,
)
from .sizing import SizedPosition, size_positions
from .slots import (
    Observation,
    RankMover,
    SlotCandidate,
    daily_observation,
    render_observation_lines,
    slot_candidates,
)

__all__ = [
    "RotationEngine",
    "RotationPlan",
    "TargetPosition",
    "RebalanceAction",
    "SizedPosition",
    "size_positions",
    "Ranker",
    "TechnicalRanker",
    "MomentumRanker",
    "make_ranker",
    "SlotCandidate",
    "slot_candidates",
    "Observation",
    "RankMover",
    "daily_observation",
    "render_observation_lines",
    "TriggerType",
    "SellTrigger",
    "SellAlert",
    "AlertLedger",
    "SellAlertEngine",
    "RankingCollapseTracker",
    "AlertCooldown",
    "check_technical_emergency",
    "check_ranking_collapse",
    "check_fundamental_red_flags",
    "collapse_cutoff",
    "collapse_rank_map",
    "compute_atr",
    "rotation_days",
    "is_rotation_day",
    "CooldownStore",
    "InMemoryCooldownStore",
    "SheetsCooldownStore",
    "reconstruct_cooldown",
    "active_cooldown_dates",
    "run_live_flow",
    "LiveDecision",
    "BuySuggestion",
    "ExitSuggestion",
    "RebalanceNote",
]
