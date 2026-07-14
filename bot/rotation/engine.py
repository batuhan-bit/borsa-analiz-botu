"""Rotasyon çekirdeği (Görev A.1) — hedef portföy ve fark üretimi.

Rotasyon günü (ayın ilk işlem günü — takvim mantığı Faz C) evrendeki semboller
sıralama skoruyla sıralanır, hedef portföy seçilir ve mevcut portföyle fark
(giren / çıkan / kalan) üretilir. İki seçim modu:

  - per_basket   (birincil): her sepetten skor sırasına göre `positions_per_basket`
    hisse; sepet ağırlıkları (%40/35/25) korunur; pozisyon ağırlığı = sepet
    ağırlığı / positions_per_basket.
  - global_top_n (test): evren genelinde ilk N, eşit ağırlık, tema başına en çok
    `max_positions_per_theme` pozisyon.

DETERMİNİZM: sıralama daima (-skor, sembol) ile yapılır; skorlar dışarıdan saf
bir `rank_fn` ile gelir. Böylece aynı girdi -> birebir aynı plan (kabul kriteri).

Skorlama (`rank_fn`) ve fiyat verisi dışarıdan enjekte edilir; bu modül veri
kaynağı bilmez. Somut skorlayıcılar Görev A.2'de (scoring.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from ..config import Strategy
from .sizing import SizedPosition, size_positions

# Bir sembol kümesini (symbol, skor) çiftlerine eşleyen saf fonksiyon.
# Sıralama motorun kendisi tarafından yapılır; rank_fn yalnız skor üretir.
RankFn = Callable[[Sequence[str]], Sequence[tuple[str, float]]]


@dataclass(frozen=True)
class TargetPosition:
    symbol: str
    basket: str
    theme: str | None
    weight: float          # portföy kesri (0..1)
    score: float
    rank: int              # seçildiği sıradaki konumu (1 = en yüksek)


@dataclass(frozen=True)
class RebalanceAction:
    symbol: str
    current_weight: float
    target_weight: float
    action: str            # "ekle" | "azalt"
    drift_pct: float       # |cur - tgt| / tgt * 100


@dataclass(frozen=True)
class RotationPlan:
    selection: str
    targets: list[TargetPosition]
    entering: list[str]    # hedefte olup portföyde olmayanlar
    exiting: list[str]     # portföyde olup hedefte olmayanlar
    staying: list[str]     # her ikisinde de olanlar
    rebalance: list[RebalanceAction] = field(default_factory=list)

    @property
    def target_symbols(self) -> list[str]:
        return [t.symbol for t in self.targets]

    @property
    def weights(self) -> dict[str, float]:
        return {t.symbol: t.weight for t in self.targets}


def _sort_scored(scored: Sequence[tuple[str, float]]) -> list[tuple[str, float]]:
    """(-skor, sembol) ile deterministik sırala (yüksek skor önce, eşitlikte alfabetik)."""
    return sorted(scored, key=lambda x: (-x[1], x[0]))


class RotationEngine:
    def __init__(self, strategy: Strategy) -> None:
        self._strategy = strategy
        rot = strategy.rotation
        self._selection = rot.get("selection", "per_basket")
        self._top_n = int(rot.get("top_n", 6))
        self._band = float(rot.get("rebalance_band_pct", 20)) / 100.0
        self._max_per_theme = int(rot.get("max_positions_per_theme", 2))
        self._per_basket = int(strategy.portfolio.get("positions_per_basket", 2))

    # --- Hedef seçimi ---
    def _select_per_basket(self, rank_fn: RankFn) -> list[TargetPosition]:
        targets: list[TargetPosition] = []
        for name, cfg in self._strategy.baskets.items():
            syms = list(cfg.get("universe", []))
            if not syms:
                continue
            ranked = _sort_scored(rank_fn(syms))[: self._per_basket]
            basket_weight = cfg["allocation_pct"] / 100.0
            pos_weight = basket_weight / self._per_basket
            for i, (sym, score) in enumerate(ranked, start=1):
                targets.append(TargetPosition(
                    symbol=sym, basket=name, theme=self._strategy.theme_of(sym),
                    weight=pos_weight, score=float(score), rank=i,
                ))
        return targets

    def _select_global_top_n(self, rank_fn: RankFn) -> list[TargetPosition]:
        syms = self._strategy.universe_symbols
        ranked = _sort_scored(rank_fn(syms))
        picks: list[tuple[str, float]] = []
        theme_counts: dict[str | None, int] = {}
        for sym, score in ranked:
            theme = self._strategy.theme_of(sym)
            if theme_counts.get(theme, 0) >= self._max_per_theme:
                continue          # tema doygunluğu — yoğunlaşmayı sınırla
            picks.append((sym, score))
            theme_counts[theme] = theme_counts.get(theme, 0) + 1
            if len(picks) >= self._top_n:
                break
        if not picks:
            return []
        weight = 1.0 / len(picks)     # eşit ağırlık (seçilenler tam yatırılır)
        return [
            TargetPosition(
                symbol=sym, basket=self._strategy.basket_of(sym) or "",
                theme=self._strategy.theme_of(sym), weight=weight,
                score=float(score), rank=i,
            )
            for i, (sym, score) in enumerate(picks, start=1)
        ]

    def _select(self, rank_fn: RankFn) -> list[TargetPosition]:
        if self._selection == "global_top_n":
            return self._select_global_top_n(rank_fn)
        return self._select_per_basket(rank_fn)

    # --- Fark + rebalans ---
    def _diff(
        self, targets: list[TargetPosition], current: Mapping[str, float]
    ) -> tuple[list[str], list[str], list[str], list[RebalanceAction]]:
        held = set(current)
        target_syms = [t.symbol for t in targets]
        target_set = set(target_syms)

        entering = [s for s in target_syms if s not in held]
        exiting = sorted(s for s in held if s not in target_set)
        staying = [s for s in target_syms if s in held]

        rebalance: list[RebalanceAction] = []
        for t in targets:
            if t.symbol not in held or t.weight <= 0:
                continue
            cur = float(current[t.symbol])
            drift = abs(cur - t.weight) / t.weight
            if drift > self._band:
                rebalance.append(RebalanceAction(
                    symbol=t.symbol,
                    current_weight=round(cur, 4),
                    target_weight=round(t.weight, 4),
                    action="ekle" if cur < t.weight else "azalt",
                    drift_pct=round(drift * 100.0, 1),
                ))
        return entering, exiting, staying, rebalance

    def build_plan(
        self, rank_fn: RankFn, current: Mapping[str, float] | None = None
    ) -> RotationPlan:
        """Hedef portföyü ve mevcut portföyle farkı üret.

        rank_fn: sembol dizisini (symbol, skor) çiftlerine eşleyen saf fonksiyon.
                 Sıralama motor tarafından deterministik yapılır.
        current: symbol -> mevcut portföy ağırlığı (kesir). Rebalans önerileri
                 kalan (staying) semboller için buradan hesaplanır. Verilmezse
                 tüm hedefler "giren" sayılır, rebalans önerisi üretilmez.
        """
        current = current or {}
        targets = self._select(rank_fn)
        entering, exiting, staying, rebalance = self._diff(targets, current)
        return RotationPlan(
            selection=self._selection,
            targets=targets,
            entering=entering,
            exiting=exiting,
            staying=staying,
            rebalance=rebalance,
        )

    # --- Sizing köprüsü (Görev A.1 kabul: sizing v2 yeniden kullanılır) ---
    def size(
        self, plan: RotationPlan, capital: float, prices: Mapping[str, float],
        *, fractional: bool = False,
    ) -> list[SizedPosition]:
        """Plandaki hedef ağırlıkları sizing v2 modülüyle tutar/adete çevir."""
        return size_positions(plan.targets, capital, prices, fractional=fractional)
