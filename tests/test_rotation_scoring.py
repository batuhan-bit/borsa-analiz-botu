"""Sıralama skorları (Görev A.2) birim testleri — ağ/anahtar gerektirmez.

S1 (teknik) ve S2 (momentum) skorlayıcılarını sentetik barlarla doğrular.
İkisi de aynı rank(symbols, as_of) arayüzünü uygular.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from bot.config import Strategy
from bot.rotation import MomentumRanker, TechnicalRanker, make_ranker


def _trend_df(slope: float, n: int = 300, start: float = 100.0) -> pd.DataFrame:
    """Doğrusal eğimli (gürültüsüz) fiyat serisi — deterministik."""
    close = start + slope * np.arange(n)
    idx = pd.bdate_range("2020-01-01", periods=n)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(n, 1_000_000)},
        index=idx,
    )


def _provider(frames: dict[str, pd.DataFrame]):
    return lambda sym: frames.get(sym, pd.DataFrame())


def _strategy(**rotation_overrides) -> Strategy:
    strat = Strategy.load()
    strat.raw.setdefault("rotation", {})
    strat.raw["rotation"].update(rotation_overrides)
    return strat


# ---------------- S1 teknik ----------------

def test_technical_ranker_orders_uptrend_above_downtrend():
    frames = {"UP": _trend_df(0.5), "DOWN": _trend_df(-0.5)}
    ranker = TechnicalRanker(_strategy(), _provider(frames))
    ranked = ranker.rank(["DOWN", "UP"])
    assert [s for s, _ in ranked] == ["UP", "DOWN"]
    assert ranked[0][1] > ranked[1][1]


def test_technical_ranker_skips_insufficient_history():
    frames = {"SHORT": _trend_df(0.5, n=50)}   # 200G ortalama için yetersiz
    ranker = TechnicalRanker(_strategy(), _provider(frames))
    assert ranker.rank(["SHORT"]) == []


def test_ranker_deterministic_tie_break_alphabetical():
    # Aynı eğim -> aynı skor; eşitlikte alfabetik sıra
    frames = {"BBB": _trend_df(0.3), "AAA": _trend_df(0.3)}
    ranker = TechnicalRanker(_strategy(), _provider(frames))
    ranked = ranker.rank(["BBB", "AAA"])
    assert [s for s, _ in ranked] == ["AAA", "BBB"]


# ---------------- S2 momentum ----------------

def test_momentum_ranker_orders_by_return():
    frames = {"FAST": _trend_df(1.0), "SLOW": _trend_df(0.1)}
    ranker = MomentumRanker(_strategy(momentum={"lookback_days": 126, "skip_days": 21}),
                            _provider(frames))
    ranked = ranker.rank(["SLOW", "FAST"])
    assert [s for s, _ in ranked] == ["FAST", "SLOW"]
    assert ranked[0][1] > ranked[1][1]


def test_momentum_excludes_recent_skip_window():
    """Son skip günündeki çöküş momentumu etkilememeli (skip penceresi hariç)."""
    # 300 gün yükseliş, son 21 günde sert çöküş
    close = np.concatenate([100 + 0.5 * np.arange(279), np.linspace(239, 150, 21)])
    idx = pd.bdate_range("2020-01-01", periods=300)
    crash = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.full(300, 1_000_000)}, index=idx,
    )
    steady = _trend_df(0.5, n=300)   # aynı yükseliş, çöküş yok
    ranker = MomentumRanker(_strategy(momentum={"lookback_days": 126, "skip_days": 21}),
                            _provider({"CRASH": crash, "STEADY": steady}))
    scored = dict(ranker.rank(["CRASH", "STEADY"]))
    # Skip penceresi çöküşü dışladığı için CRASH momentumu hâlâ pozitif ve
    # STEADY ile aynı büyüklük mertebesinde (son 21 gün ikisinde de sayılmaz).
    assert scored["CRASH"] > 0
    assert abs(scored["CRASH"] - scored["STEADY"]) < 0.05


def test_momentum_skips_insufficient_history():
    frames = {"SHORT": _trend_df(0.5, n=100)}   # 126+21 için yetersiz
    ranker = MomentumRanker(_strategy(momentum={"lookback_days": 126, "skip_days": 21}),
                            _provider(frames))
    assert ranker.rank(["SHORT"]) == []


# ---------------- Fabrika + as_of ----------------

def test_make_ranker_selects_variant():
    frames = {"X": _trend_df(0.5)}
    assert isinstance(make_ranker(_strategy(score="s1_technical"), _provider(frames)),
                      TechnicalRanker)
    assert isinstance(make_ranker(_strategy(score="s2_momentum"), _provider(frames)),
                      MomentumRanker)


def test_as_of_slices_history():
    """as_of verilince yalnız o tarihe kadar olan barlar kullanılır."""
    frames = {"UP": _trend_df(0.5, n=300)}
    ranker = MomentumRanker(_strategy(momentum={"lookback_days": 126, "skip_days": 21}),
                            _provider(frames))
    early_date = frames["UP"].index[100]     # ilk 101 bar -> momentum için yetersiz
    assert ranker.rank(["UP"], as_of=early_date) == []
    # Yeterli tarih verilince skor üretilir
    assert ranker.rank(["UP"], as_of=frames["UP"].index[-1]) != []


# ---------------- score_series (backtest paneli) ----------------

def test_momentum_score_series_matches_rank_as_of():
    """Vektörel momentum serisi, her tarihte rank(as_of) skoruyla birebir eşleşmeli.

    Backtest paneli sıralamayı bu seriden okur; rank() ile tutarlı olmalı ki
    canlı ve backtest aynı skoru görsün (Görev B.1 doğruluğu).
    """
    frames = {"UP": _trend_df(0.5, n=300)}
    ranker = MomentumRanker(_strategy(momentum={"lookback_days": 126, "skip_days": 21}),
                            _provider(frames))
    series = ranker.score_series(frames["UP"])
    for as_of in (frames["UP"].index[150], frames["UP"].index[200], frames["UP"].index[-1]):
        expected = dict(ranker.rank(["UP"], as_of=as_of)).get("UP")
        assert abs(series.loc[as_of] - expected) < 1e-9


def test_technical_score_series_matches_rank_as_of():
    frames = {"UP": _trend_df(0.5, n=300)}
    ranker = TechnicalRanker(_strategy(), _provider(frames))
    series = ranker.score_series(frames["UP"])
    for as_of in (frames["UP"].index[210], frames["UP"].index[260], frames["UP"].index[-1]):
        expected = dict(ranker.rank(["UP"], as_of=as_of)).get("UP")
        assert abs(series.loc[as_of] - expected) < 1e-9
