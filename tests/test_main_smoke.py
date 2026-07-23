"""bot.main uçtan uca wiring dumanı (Görev C.1/v1 emekliliği) — GERÇEK AĞ YOK.

Ağır bağımlılıklar taklit edilir: yfinance (_load_bars), Sheets (kimliksiz →
devre dışı), Slack POST (requests.post fake). Amaç: v2 akışının entrypoint'ten
uçtan uca hatasız koştuğunu ve v1 motoruna DOKUNMADIĞINI doğrulamak.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import bot.main as main_mod
import bot.notify.slack as slack_mod
from bot.config import Strategy
from bot.rotation.live import LiveDecision

# as_of güncel olmalı: bayat-tarih kapısı (A) canlı akışta 3 günden eski raporu
# engeller; smoke testi gerçek gönderimi doğruladığı için bar'lar BUGÜNDE biter.
INDEX = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=200)
RATES = {"SPY": 1.005, "XLU": 1.004, "NVDA": 1.006, "AMD": 1.005,
         "IONQ": 1.005, "RGTI": 1.004}


def _geom(rate):
    close = pd.Series([100 * rate ** i for i in range(len(INDEX))], index=INDEX)
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                         "close": close, "volume": 1e6}, index=INDEX)


class _FakeResp:
    status_code = 200
    text = "ok"


def test_main_runs_end_to_end_without_network(monkeypatch):
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["payload"] = json
        return _FakeResp()

    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://example/hook")
    monkeypatch.setattr(main_mod, "_load_bars",
                        lambda strategy, years: {s: _geom(r) for s, r in RATES.items()})
    monkeypatch.setattr(slack_mod.requests, "post", fake_post)

    main_mod.main()   # çökmemeli

    assert "payload" in sent
    payload = sent["payload"]
    assert "blocks" in payload
    # v2 başlığı; v1 "Borsa Analizi" / eşik dili değil
    assert "Rotasyon" in payload["text"]


def _decision(today_index: int) -> LiveDecision:
    return LiveDecision(as_of=date.today(), frequency="biweekly",
                        is_rotation_day=False, today_index=today_index)


# ---------------- (B) veri-bütünlüğü kapısı ----------------

def test_assert_live_data_raises_on_empty_bars():
    with pytest.raises(RuntimeError, match="bars"):
        main_mod._assert_live_data(Strategy.load(), {}, _decision(3))


def test_assert_live_data_raises_on_invalid_today_index():
    with pytest.raises(RuntimeError, match="işlem günü"):
        main_mod._assert_live_data(Strategy.load(), {"SPY": object()}, _decision(-1))


def test_assert_live_data_passes_with_real_data():
    # Boş olmayan bars + geçerli işlem günü -> hata YOK
    main_mod._assert_live_data(Strategy.load(), {"SPY": object()}, _decision(5))


# ---------------- (C) test script'i üretim webhook'unu kullanamaz ----------------

def test_test_report_decision_is_synthetic():
    from scripts.send_test_report import _real_decision
    _strat, d = _real_decision()
    assert d.synthetic is True


def test_test_report_refuses_missing_test_webhook(monkeypatch):
    from scripts.send_test_report import _resolve_test_webhook
    monkeypatch.delenv("SLACK_TEST_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://prod")
    with pytest.raises(SystemExit):
        _resolve_test_webhook()                 # ayrı test webhook'u yok -> reddet


def test_test_report_refuses_prod_equal_test_webhook(monkeypatch):
    from scripts.send_test_report import _resolve_test_webhook
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://same")
    monkeypatch.setenv("SLACK_TEST_WEBHOOK_URL", "http://same")
    with pytest.raises(SystemExit):
        _resolve_test_webhook()                 # üretimle aynı -> reddet


def test_test_report_accepts_distinct_test_webhook(monkeypatch):
    from scripts.send_test_report import _resolve_test_webhook
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "http://prod")
    monkeypatch.setenv("SLACK_TEST_WEBHOOK_URL", "http://test")
    assert _resolve_test_webhook() == "http://test"


def test_legacy_engine_is_importable_but_not_used_by_main():
    # v1 parçaları SİLİNMEDİ — legacy_engine'den erişilebilir
    from bot.legacy_engine import SignalEngine, check_stop_loss
    assert SignalEngine is not None and check_stop_loss is not None
    # ...ama canlı entrypoint (bot.main) onları IMPORT/ÇAĞIRMAZ (docstring'de
    # yönlendirme olarak anılması sorun değil; kod yolunda olmamalı).
    import inspect
    src = inspect.getsource(main_mod)
    assert "from .legacy_engine" not in src and "import legacy_engine" not in src
    assert "from .signals" not in src        # v1 sinyal motoru import edilmez
    assert "from .risk" not in src           # v1 stop-loss import edilmez
    assert "SignalEngine(" not in src        # örneklenmez
    assert "check_stop_loss(" not in src     # çağrılmaz
