"""Rotasyon motoru (v2) — aylık kesitsel portföy rotasyonu.

v1'in eşik-tetiklemeli BUY/SELL motorunun yerini alır. Deterministiktir:
aynı veri + aynı tarih -> aynı hedef portföy. Modüller:
  - engine   : hedef portföy + fark (giren/çıkan/kalan) + rebalans (Görev A.1)
  - sizing   : ağırlık -> tutar/adet dönüşümü (Görev A.1)
  - scoring  : sıralama skorları S1/S2 (Görev A.2)
"""
from __future__ import annotations

from .engine import (
    RebalanceAction,
    RotationEngine,
    RotationPlan,
    TargetPosition,
)
from .scoring import (
    MomentumRanker,
    Ranker,
    TechnicalRanker,
    make_ranker,
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
]
