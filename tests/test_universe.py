"""Evren (universe.yaml) doğrulama testleri.

Evren tek gerçek kaynaktır: her sembol tam olarak bir sepete ve bir temaya
ait olmalı; config yükleyici bunu baskets'e geri doldurmalı (v1 uyumu).
"""
from __future__ import annotations

from bot.config import Strategy
from bot.models import Basket

VALID_BASKETS = {b.value for b in Basket}


def test_universe_has_60_symbols():
    strat = Strategy.load()
    assert len(strat.universe) == 60, f"60 sembol beklenir, {len(strat.universe)} bulundu"


def test_every_symbol_has_valid_basket_and_theme():
    """60/60 sembol geçerli sepet + boş olmayan tema etiketine sahip olmalı."""
    strat = Strategy.load()
    for symbol, meta in strat.universe.items():
        assert meta.get("basket") in VALID_BASKETS, f"{symbol}: geçersiz sepet {meta.get('basket')}"
        theme = meta.get("theme")
        assert isinstance(theme, str) and theme.strip(), f"{symbol}: tema etiketi eksik"


def test_symbols_are_unique():
    """Aynı sembol iki kez tanımlanmamalı (YAML anahtarı zaten tekil ama açıkça doğrula)."""
    strat = Strategy.load()
    symbols = strat.universe_symbols
    assert len(symbols) == len(set(symbols))


def test_universe_rehydrated_into_baskets():
    """Yükleyici sepet başına sembol listesini universe.yaml'dan doldurmalı."""
    strat = Strategy.load()
    total = 0
    for name, cfg in strat.baskets.items():
        syms = cfg.get("universe", [])
        total += len(syms)
        for s in syms:
            assert strat.basket_of(s) == name
    assert total == 60


def test_strategy_yaml_has_no_hardcoded_universe():
    """strategy.yaml dosyasının kendisi evren listesi İÇERMEMELİ (yalnız ağırlıklar).

    Yükleyici sonrası baskets['universe'] dolu olsa da, ham dosya kaynağında
    olmamalı — tek gerçek kaynak universe.yaml.
    """
    import yaml
    from bot.config import DEFAULT_STRATEGY_PATH

    with open(DEFAULT_STRATEGY_PATH, "r", encoding="utf-8") as f:
        raw_file = yaml.safe_load(f)
    for name, cfg in raw_file.get("baskets", {}).items():
        assert "universe" not in cfg, f"{name}: strategy.yaml'da hardcode evren var"


def test_basket_allocations_still_present():
    """Ağırlıklar strategy.yaml'da kalmalı."""
    strat = Strategy.load()
    total = sum(b["allocation_pct"] for b in strat.baskets.values())
    assert total == 100
