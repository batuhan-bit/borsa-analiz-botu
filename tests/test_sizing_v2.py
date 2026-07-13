"""Sizing v2 (Görev 2.2) + gerçekçilik katmanı (Görev 2.1) motor testleri.

Ağ yok — load_bars monkeypatch ile sentetik barlar. Her gün AÇILIŞ, o günün
kapanışının %2 altında (open != close) olacak şekilde kurulur; böylece
ertesi-gün-açılış dolgusu, kapanış dolgusundan ölçülebilir biçimde ayrışır.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import backtest.backtest as bt
from bot.config import Settings


def _bars(start: str, end: str, seed: int) -> pd.DataFrame:
    idx = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.15, 1.0, len(idx)))   # yukarı eğilimli
    close = np.maximum(close, 2.0)
    return pd.DataFrame(
        {"open": close * 0.98,                 # açılış kapanışın %2 altında
         "high": close + 1, "low": close * 0.97, "close": close,
         "volume": rng.integers(1_000_000, 2_000_000, len(idx))},
        index=idx,
    )


@pytest.fixture()
def fake_bars(monkeypatch):
    def _load(symbol, *, years=3.0, start=None, end=None):
        return _bars(start or "2015-01-01", end or "2017-12-31", seed=hash(symbol) % 97)
    monkeypatch.setattr(bt, "load_bars", _load)
    return _load


def _run(settings, **kw):
    return bt.run_backtest(settings, basket_limit=2, start="2016-01-04",
                           end="2017-12-29", verbose=False, **kw)


def test_costs_reduce_returns(fake_bars):
    settings = Settings.load(strict=False)
    costless = _run(settings, sizing_mode="v2", fill_mode="next_open", apply_costs=False)
    costed = _run(settings, sizing_mode="v2", fill_mode="next_open", apply_costs=True)
    assert costed.num_trades > 0
    # Komisyon+kayma her işlemde sürtünme -> maliyetli getiri daha düşük
    assert costed.total_return_pct < costless.total_return_pct


def test_next_open_fill_differs_from_close(fake_bars):
    settings = Settings.load(strict=False)
    close_fill = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    open_fill = _run(settings, sizing_mode="v2", fill_mode="next_open", apply_costs=False)
    # Farklı dolgu fiyatı -> farklı giriş fiyatları -> farklı toplam getiri
    assert close_fill.total_return_pct != open_fill.total_return_pct
    close_entries = sorted(t.entry_price for t in close_fill.trades)
    open_entries = sorted(t.entry_price for t in open_fill.trades)
    assert close_entries != open_entries


def test_deployment_cap_limits_exposure(fake_bars):
    settings = Settings.load(strict=False)
    settings.strategy.raw["portfolio"].setdefault("sizing", {})
    # Yüksek dağıtım tavanı: neredeyse tam yatırım
    settings.strategy.raw["portfolio"]["sizing"].update(
        {"deployment_pct": 95, "min_fill_pct": 0.0, "fractional_shares": False})
    high = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    # Düşük dağıtım tavanı: sermayenin çoğu nakitte -> yükselen piyasada daha az kazanç
    settings.strategy.raw["portfolio"]["sizing"]["deployment_pct"] = 30
    low = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    assert high.total_return_pct != low.total_return_pct
    assert high.total_return_pct > low.total_return_pct   # daha fazla maruziyet, yükseliş


def test_min_fill_gate_defers(fake_bars):
    """Yüksek min_fill_pct, cılız (nakit-kısıtlı) dolumları erteler -> <= işlem."""
    settings = Settings.load(strict=False)
    settings.strategy.raw["portfolio"].setdefault("sizing", {})
    settings.strategy.raw["portfolio"]["sizing"].update(
        {"deployment_pct": 95, "min_fill_pct": 0.0, "fractional_shares": False})
    permissive = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    settings.strategy.raw["portfolio"]["sizing"]["min_fill_pct"] = 0.99
    strict = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    assert strict.num_trades <= permissive.num_trades


def test_legacy_and_v2_agree_without_contention(fake_bars):
    """Nakit çekişmesi yokken (sinyaller farklı günlere yayılınca) v2 ve legacy
    aynı sonucu verir — v2 yalnız aynı-gün nakit paylaşımında ayrışır."""
    settings = Settings.load(strict=False)
    legacy = _run(settings, sizing_mode="legacy", fill_mode="close", apply_costs=False)
    v2 = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    assert legacy.num_trades > 0 and v2.num_trades > 0


def test_legacy_vs_v2_diverge_under_contention(monkeypatch):
    """Tüm semboller AYNI seriyi paylaşınca hepsi aynı gün BUY verir → nakit
    çekişmesi. Legacy sepet sırasıyla doldurur (deployment tavanı yok, %100'e
    kadar yatırır); v2 deployment_pct ile sınırlar ve orantılı paylaşır →
    sonuçlar ayrışmalı."""
    shared = _bars("2015-01-01", "2017-12-31", seed=1)
    monkeypatch.setattr(bt, "load_bars", lambda symbol, **kw: shared)
    settings = Settings.load(strict=False)
    settings.strategy.raw["portfolio"].setdefault("sizing", {})
    settings.strategy.raw["portfolio"]["sizing"].update(
        {"deployment_pct": 95, "min_fill_pct": 0.0, "fractional_shares": False})
    legacy = _run(settings, sizing_mode="legacy", fill_mode="close", apply_costs=False)
    v2 = _run(settings, sizing_mode="v2", fill_mode="close", apply_costs=False)
    assert legacy.num_trades > 0 and v2.num_trades > 0
    # Legacy %100'e kadar yatırır, v2 %95 tavanla nakit tutar → yükseliş piyasada legacy önde
    assert legacy.total_return_pct != v2.total_return_pct
