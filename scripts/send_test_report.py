"""Sepet-içi sıra gözlem satırı için Slack test raporu — GERÇEK pipeline.

Raporu elle kurulmuş bir Observation'dan DEĞİL, gerçek `run_live_flow` hattından
üretir (böylece `_build_observation` → `basket_rank_map` → `SlackNotifier` gerçek
kod yolundan geçer). Ağ/Sheets gerekmez: bar'lar sentetik-ama-deterministiktir,
semboller gerçek evrenden alınır.

GÜVENLİK (C): Bu script sentetik veri üretir; üretim kanalına DÜŞMEMESİ için:
  - Kararı `synthetic=True` işaretler (SlackNotifier üretim webhook'una reddeder).
  - Yalnız AYRI `SLACK_TEST_WEBHOOK_URL` ortam değişkenini okur; üretim
    `SLACK_WEBHOOK_URL`'ini ASLA kullanmaz. İkisi aynıysa gönderimi reddeder.
  - Gerçek gönderim için `--send` YANINDA `--i-know-this-is-synthetic` gerekir.

Kullanım:
  # Önizleme (ağ YOK — render edilen gözlem satırını yazdırır):
  python -m scripts.send_test_report

  # Gerçek gönderim (AYRI test kanalı):
  SLACK_TEST_WEBHOOK_URL="https://hooks.slack.com/services/TEST" \
      python -m scripts.send_test_report --send --i-know-this-is-synthetic
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

from bot.config import Strategy
from bot.notify import SlackNotifier
from bot.rotation import run_live_flow
from bot.rotation.alerts import AlertCooldown, collapse_cutoff

# Gerçek evren sembolleri; sepet-içi sıra rate'e (momentum) göre AZALAN olur.
# low_volatility'ye 8 sembol -> sepet-içi sıra 1..8. cutoff (gerçek config: 3×2=6)
# üstündeki tutulan sembol (COST, sepet-içi #8) eşik-dışı italik vurgu ile görünür.
_RATES = {
    # low_volatility (sepet-içi #1..#8)
    "SPY": 1.0080, "XLP": 1.0070, "XLU": 1.0060, "JNJ": 1.0050,
    "PG": 1.0040, "KO": 1.0030, "PEP": 1.0020, "COST": 1.0010,
    # high_volatility (#1..#3)
    "NVDA": 1.0075, "AMD": 1.0065, "SMCI": 1.0055,
    # under_radar (#1..#3)
    "IONQ": 1.0072, "RGTI": 1.0062, "QBTS": 1.0052,
}
_INDEX = pd.bdate_range(end="2022-06-30", periods=210)
_WATCH_DAY = pd.Timestamp("2022-06-08")   # ay ortası -> izleme günü (rotasyon değil)

# Tutulan pozisyonlar: her sepetten en yüksek + low_vol'de sepet-içi #8 (eşik-dışı).
_HELD = [
    ("SPY", "low_volatility"),
    ("COST", "low_volatility"),     # sepet-içi #8 > cutoff 6 -> hafif italik vurgu
    ("NVDA", "high_volatility"),
    ("IONQ", "under_radar"),
]


def _geom_bars(rate: float, base: float = 100.0) -> pd.DataFrame:
    close = pd.Series([base * (rate ** i) for i in range(len(_INDEX))], index=_INDEX)
    return pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": 1_000_000,
    }, index=_INDEX)


def _real_decision():
    strategy = Strategy.load()
    bars = {sym: _geom_bars(r) for sym, r in _RATES.items()}
    holdings = [
        {"symbol": sym, "basket": basket, "entry_price": 100.0, "shares": 5.0,
         "entry_date": None}
        for sym, basket in _HELD
    ]
    decision = run_live_flow(
        strategy, bars, holdings, cooldown=AlertCooldown(cooldown_days=5),
        today=_WATCH_DAY, portfolio_value=5000, cash=1000.0,
    )
    decision.synthetic = True    # (C) üretim webhook'una gitmesin
    return strategy, decision


def _resolve_test_webhook() -> str:
    """Yalnız AYRI test webhook'unu döndür; üretimle karışmayı reddet."""
    test_url = os.getenv("SLACK_TEST_WEBHOOK_URL", "")
    prod_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not test_url:
        raise SystemExit(
            "HATA: SLACK_TEST_WEBHOOK_URL ayarlı değil. Bu script sentetik veri üretir ve "
            "yalnız AYRI bir test webhook'una gönderir; üretim SLACK_WEBHOOK_URL'ini kullanmaz.")
    if prod_url and test_url == prod_url:
        raise SystemExit(
            "HATA: SLACK_TEST_WEBHOOK_URL, üretim SLACK_WEBHOOK_URL ile AYNI — sentetik veri "
            "üretim kanalına gönderilemez. Farklı bir test webhook'u kullanın.")
    return test_url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Slack'e gerçekten gönder")
    ap.add_argument("--i-know-this-is-synthetic", dest="ack_synthetic",
                    action="store_true", help="Sentetik veri gönderdiğini onayla (--send ile zorunlu)")
    args = ap.parse_args()

    strategy, decision = _real_decision()
    payload = SlackNotifier("preview").format_message(decision)

    print(f"[gerçek pipeline · SENTETİK] izleme günü {decision.as_of} · collapse_cutoff="
          f"{collapse_cutoff(strategy)} (sepet-içi sıra bunun üstündeyse italik)")
    for b in payload["blocks"]:
        t = b.get("text", {})
        if isinstance(t, dict) and "sıraları" in t.get("text", ""):
            print(t["text"].replace("\\n", "\n"))
    print("-" * 60)

    if not args.send:
        print("[önizleme] Gönderim yapılmadı. Göndermek için: --send --i-know-this-is-synthetic "
              "(SLACK_TEST_WEBHOOK_URL gerekli)")
        return 0

    if not args.ack_synthetic:
        print("HATA: --send yalnız --i-know-this-is-synthetic ile birlikte kullanılabilir "
              "(sentetik veri gönderdiğinizi onaylayın).", file=sys.stderr)
        return 1

    test_url = _resolve_test_webhook()
    # allow_synthetic=True yalnız AYRI test kanalında; yaş kapısı yok (veri kasıtlı eski).
    SlackNotifier(test_url, allow_synthetic=True).send(decision)
    print("[gönderildi] Test webhook'una POST edildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
