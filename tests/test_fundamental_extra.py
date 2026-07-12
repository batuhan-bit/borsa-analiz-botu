"""Part 3 temel-analiz eklentileri: kâr/zarar, büyüme, içeriden işlem, notlar."""
from __future__ import annotations

import pytest

from bot.config import Strategy
from bot.signals.fundamental import (
    fundamental_notes,
    fundamental_score,
    parse_insider_net,
    parse_overview_fundamentals,
)

FUND_CFG = Strategy.load().fundamental


def test_parse_overview_fundamentals():
    ov = {"ProfitMargin": "-0.05", "EPS": "-0.25",
          "QuarterlyEarningsGrowthYOY": "0.15", "QuarterlyRevenueGrowthYOY": "None"}
    out = parse_overview_fundamentals(ov)
    assert out["profit_margin"] == -0.05
    assert out["eps"] == -0.25
    assert out["earnings_growth_yoy"] == 0.15
    assert out["revenue_growth_yoy"] is None


def test_parse_insider_net_counts_recent_only():
    from datetime import date, timedelta
    recent = (date.today() - timedelta(days=10)).isoformat()
    old = (date.today() - timedelta(days=300)).isoformat()
    resp = {"data": [
        {"transactionDate": recent, "change": -1000},
        {"transactionDate": recent, "change": -500},
        {"transactionDate": recent, "change": 200},
        {"transactionDate": old, "change": -99999},   # eski, sayılmamalı
    ]}
    net = parse_insider_net(resp)
    assert net["net_shares"] == -1300      # -1000 -500 +200
    assert net["sells"] == 2 and net["buys"] == 1


def test_parse_insider_net_empty():
    assert parse_insider_net({"data": []}) is None
    assert parse_insider_net({}) is None


def test_analyst_upside_extreme_is_dampened():
    normal = fundamental_score({"analyst_target_upside_pct": 40}, FUND_CFG)[0]
    extreme = fundamental_score({"analyst_target_upside_pct": 150}, FUND_CFG)[0]
    # %40 tam katkı (+1.0), %150 kırpılmış (+0.4) -> aşırı olan DAHA DÜŞÜK katkı verir
    assert normal > extreme


def test_loss_making_penalizes_and_notes():
    score, reasons = fundamental_score({"profit_margin": -0.10, "eps": -1.2}, FUND_CFG)
    assert score < 0                                  # zarar cezası negatif skor
    notes = fundamental_notes({"profit_margin": -0.10, "eps": -1.2})
    assert any("zarar ediyor" in n for n in notes)


def test_insider_selling_note_and_score():
    data = {"insider_net_shares": -50000, "insider_sells": 3, "insider_buys": 0}
    score, reasons = fundamental_score(data, FUND_CFG)
    assert score < 0
    assert any("net satış" in r for r in reasons)
    notes = fundamental_notes(data)
    assert any("NET SATIŞ" in n for n in notes)


def test_insider_buying_positive():
    data = {"insider_net_shares": 25000}
    notes = fundamental_notes(data)
    assert any("net ALIM" in n for n in notes)
