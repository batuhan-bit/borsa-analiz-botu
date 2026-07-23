"""Sepet-içi sıra gözlem satırı için Slack test raporu — GERÇEK pipeline.

Raporu elle kurulmuş bir Observation'dan DEĞİL, gerçek `run_live_flow` hattından
üretir (böylece `_build_observation` → `basket_rank_map` → `SlackNotifier` gerçek
kod yolundan geçer). Ağ/Sheets gerekmez: bar'lar sentetik-ama-deterministiktir,
semboller gerçek evrenden alınır; sepet-içi sıra ve eşik-dışı (over_threshold)
vurgusu gerçek config eşiğiyle (`collapse_cutoff`) hesaplanır.

Kullanım:
  # Önizleme (ağ YOK — render edilen gözlem satırını yazdırır):
  python -m scripts.send_test_report

  # Gerçek gönderim (SLACK_WEBHOOK_URL ayarlı olmalı):
  SLACK_WEBHOOK_URL="https://hooks.slack.com/services/XXX" python -m scripts.send_test_report --send
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
    return strategy, run_live_flow(
        strategy, bars, holdings, cooldown=AlertCooldown(cooldown_days=5),
        today=_WATCH_DAY, portfolio_value=5000, cash=1000.0,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Slack'e gerçekten gönder")
    args = ap.parse_args()

    strategy, decision = _real_decision()
    notifier = SlackNotifier(os.getenv("SLACK_WEBHOOK_URL", ""))
    payload = notifier.format_message(decision)

    print(f"[gerçek pipeline] izleme günü {decision.as_of} · collapse_cutoff="
          f"{collapse_cutoff(strategy)} (sepet-içi sıra bunun üstündeyse italik)")
    for b in payload["blocks"]:
        t = b.get("text", {})
        if isinstance(t, dict) and "sıraları" in t.get("text", ""):
            print(t["text"].replace("\\n", "\n"))
    print("-" * 60)

    if not args.send:
        print("[önizleme] Gönderim yapılmadı. Göndermek için: --send (SLACK_WEBHOOK_URL gerekli)")
        return 0

    if not os.getenv("SLACK_WEBHOOK_URL"):
        print("HATA: SLACK_WEBHOOK_URL ayarlı değil; gönderim yapılamadı.", file=sys.stderr)
        return 1

    notifier.send(decision)
    print("[gönderildi] Slack webhook'una POST edildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
