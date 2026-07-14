"""Sıralama skorları (Görev A.2) — iki varyant, ortak arayüz.

İki hipotez yarıştırılır (ikisi de aynı `rank(symbols, as_of)` arayüzünü uygular):

  - S1 (s1_technical): v1'in teknik skoru (bot.signals.technical) AYNEN taşınır;
    ağırlıklarına DOKUNULMAZ. Skor [-1, 1].
  - S2 (s2_momentum) : klasik kesitsel momentum — son `lookback_days` işlem günü
    getirisi, son `skip_days` gün hariç (12-1 momentumun kısa hali). Pencereler
    strategy.yaml'daki rotation.momentum'dan gelir.

Seçim `rotation.score` ile: s1_technical | s2_momentum. Fiyat verisi dışarıdan
`bars_provider(symbol) -> DataFrame` ile enjekte edilir (kaynak-bağımsız,
test edilebilir). Faz B her iki skoru da koşar.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

import pandas as pd

from ..config import Strategy
from ..signals.technical import compute_indicators, technical_score

# symbol -> tüm günlük barlar (OHLCV sözleşmesi)
BarsProvider = Callable[[str], pd.DataFrame]

# rotation.engine.RankFn ile uyumlu: symbol dizisi -> (symbol, skor) çiftleri
RankFn = Callable[[Sequence[str]], list[tuple[str, float]]]


def _slice(df: pd.DataFrame, as_of) -> pd.DataFrame:
    """Barları as_of tarihine (dahil) kadar kes; as_of None ise tümü."""
    if df is None or df.empty or as_of is None:
        return df if df is not None else pd.DataFrame()
    return df.loc[:pd.Timestamp(as_of)]


class Ranker:
    """Skorlayıcı taban sınıfı. Alt sınıflar `_score_symbol` uygular."""

    name = "base"

    def __init__(self, strategy: Strategy, bars_provider: BarsProvider) -> None:
        self._strategy = strategy
        self._bars = bars_provider

    def _score_symbol(self, df: pd.DataFrame) -> Optional[float]:
        raise NotImplementedError

    def rank(self, symbols: Sequence[str], as_of=None) -> list[tuple[str, float]]:
        """Sembolleri skora göre azalan sırala (eşitlikte alfabetik).

        Skoru hesaplanamayan (yetersiz/eksik veri) semboller listeden düşülür.
        """
        scored: list[tuple[str, float]] = []
        for sym in symbols:
            df = _slice(self._bars(sym), as_of)
            score = self._score_symbol(df) if df is not None and not df.empty else None
            if score is not None:
                scored.append((sym, float(score)))
        return sorted(scored, key=lambda x: (-x[1], x[0]))

    def as_rank_fn(self, as_of=None) -> RankFn:
        """RotationEngine.build_plan'a verilecek rank_fn'i as_of'a bağla."""
        return lambda syms: self.rank(syms, as_of)


class TechnicalRanker(Ranker):
    """S1 — v1 teknik skoru (ağırlıklar değişmez)."""

    name = "s1_technical"

    def _score_symbol(self, df: pd.DataFrame) -> Optional[float]:
        tech_cfg = self._strategy.technical
        min_bars = tech_cfg["moving_averages"]["long"] + 5
        if len(df) < min_bars:
            return None
        indicators = compute_indicators(df, tech_cfg)
        if not indicators:
            return None
        score, _ = technical_score(indicators, tech_cfg)
        return score


class MomentumRanker(Ranker):
    """S2 — kesitsel momentum: son lookback günü getirisi, son skip gün hariç."""

    name = "s2_momentum"

    def __init__(self, strategy: Strategy, bars_provider: BarsProvider) -> None:
        super().__init__(strategy, bars_provider)
        mom = strategy.rotation.get("momentum", {})
        self._lookback = int(mom.get("lookback_days", 126))
        self._skip = int(mom.get("skip_days", 21))

    def _score_symbol(self, df: pd.DataFrame) -> Optional[float]:
        close = df["close"].astype(float)
        # skip gün öncesinden, lookback gün geriye getiri:
        #   start = skip + lookback gün önce, end = skip gün önce
        needed = self._skip + self._lookback + 1
        if len(close) < needed:
            return None
        end = close.iloc[-(self._skip + 1)]
        start = close.iloc[-(self._skip + self._lookback + 1)]
        if start <= 0:
            return None
        return end / start - 1.0


def make_ranker(strategy: Strategy, bars_provider: BarsProvider) -> Ranker:
    """rotation.score ayarına göre uygun skorlayıcıyı üret."""
    choice = strategy.rotation.get("score", "s1_technical")
    if choice == "s2_momentum":
        return MomentumRanker(strategy, bars_provider)
    if choice == "s1_technical":
        return TechnicalRanker(strategy, bars_provider)
    raise ValueError(f"Bilinmeyen rotation.score: {choice!r} (s1_technical | s2_momentum)")
