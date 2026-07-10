"""Sinyal motoru — teknik ve temel skorları birleştirip Signal üretir.

Nihai skor = (1 - w) * teknik + w * temel     (w = fundamental.weight)
Temel veri yoksa skor tamamen tekniğe dayanır.
Karar: skor >= buy_threshold → BUY, <= sell_threshold → SELL, aksi HOLD.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from ..config import Settings
from ..data import AlpacaClient, AlphaVantageClient, YFinanceClient
from ..models import Basket, Signal, SignalType
from .fundamental import (
    fundamental_score,
    parse_analyst_upside,
    parse_earnings_surprise,
    parse_news_sentiment,
)
from .technical import compute_indicators, technical_score

log = logging.getLogger(__name__)

# Signal.technical alanında loglanacak ham gösterge anahtarları
_TECH_LOG_KEYS = ("rsi", "macd", "macd_signal", "ma_short", "ma_long", "volume_ratio")


class SignalEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._strategy = settings.strategy
        self._alpaca = AlpacaClient(settings.secrets)
        self._yf = YFinanceClient()
        # Alpha Vantage yalnızca anahtar varsa; yoksa temel analiz atlanır
        self._av: Optional[AlphaVantageClient] = None
        if settings.secrets.alpha_vantage_api_key:
            self._av = AlphaVantageClient(settings.secrets)

    # --- Veri ---
    def _get_bars(self, symbol: str, *, years: float = 1.0) -> pd.DataFrame:
        """Önce Alpaca'yı dene; boşsa yfinance'e düş."""
        df = self._alpaca.get_daily_bars(symbol, years=years)
        if df.empty:
            df = self._yf.get_daily_bars(symbol, years=years)
        return df

    def _get_fundamental_data(self, symbol: str, price: Optional[float]) -> dict[str, Any]:
        """Alpha Vantage'dan temel veriyi çek ve normalize et (anahtar yoksa {})."""
        if self._av is None:
            return {}
        data: dict[str, Any] = {}
        try:
            data["news_sentiment_score"] = parse_news_sentiment(
                self._av.get_news_sentiment(symbol), symbol
            )
        except Exception as exc:  # noqa: BLE001  (rate-limit/ağ/parse)
            log.warning("Haber duygusu alınamadı (%s): %s", symbol, exc)
        try:
            data["earnings_surprise_pct"] = parse_earnings_surprise(
                self._av.get_earnings(symbol)
            )
        except Exception as exc:  # noqa: BLE001  (rate-limit/ağ/parse)
            log.warning("Kazanç verisi alınamadı (%s): %s", symbol, exc)
        try:
            data["analyst_target_upside_pct"] = parse_analyst_upside(
                self._av.get_overview(symbol), price
            )
        except Exception as exc:  # noqa: BLE001  (rate-limit/ağ/parse)
            log.warning("Şirket özeti alınamadı (%s): %s", symbol, exc)
        # Tümü None ise boş kabul et (teknik ağırlık tam kalsın)
        if all(v is None for v in data.values()):
            return {}
        return data

    # --- Karar ---
    def _decide(self, final_score: float) -> SignalType:
        sig_cfg = self._strategy.raw.get("signals", {})
        buy = sig_cfg.get("buy_threshold", 0.30)
        sell = sig_cfg.get("sell_threshold", -0.30)
        if final_score >= buy:
            return SignalType.BUY
        if final_score <= sell:
            return SignalType.SELL
        return SignalType.HOLD

    @staticmethod
    def _trend_summary(ind: dict[str, Any]) -> str:
        """Belirgin bir olay yokken kısa trend özeti (loglama/Slack için)."""
        ma_s, ma_l, rsi = ind.get("ma_short"), ind.get("ma_long"), ind.get("rsi")
        if ma_s is not None and ma_l is not None:
            trend = "yükseliş trendi (50G>200G)" if ma_s > ma_l else "düşüş trendi (50G<200G)"
        else:
            trend = "trend belirsiz (yetersiz geçmiş)"
        rsi_txt = f", RSI {rsi:.0f}" if rsi is not None else ""
        return f"Belirgin sinyal yok — {trend}{rsi_txt}"

    def evaluate_symbol(self, symbol: str, basket: Basket) -> Signal:
        """Tek bir sembol için sinyal üret."""
        df = self._get_bars(symbol, years=1.0)
        if df.empty:
            return Signal(symbol, basket, SignalType.HOLD, 0.0, 0.0, reasons=["Veri yok"])

        indicators = compute_indicators(df, self._strategy.technical)
        tech_score, tech_reasons = technical_score(indicators, self._strategy.technical)
        price = indicators.get("close") or float(df["close"].iloc[-1])

        fdata = self._get_fundamental_data(symbol, price)
        fund_score, fund_reasons = fundamental_score(fdata, self._strategy.fundamental)

        weight = self._strategy.fundamental.get("weight", 0.35)
        # Temel veri yoksa nihai skor tamamen tekniğe dayanır
        final = tech_score if not fdata else (1 - weight) * tech_score + weight * fund_score

        reasons = tech_reasons + fund_reasons
        if not reasons:
            reasons = [self._trend_summary(indicators)]

        return Signal(
            symbol=symbol,
            basket=basket,
            signal=self._decide(final),
            score=min(abs(final), 1.0),
            price=price,
            reasons=reasons,
            technical={k: indicators.get(k) for k in _TECH_LOG_KEYS},
            fundamental=fdata,
        )

    def run(self) -> list[Signal]:
        """Tüm sepetlerdeki evreni tara ve sinyal listesi döndür."""
        signals: list[Signal] = []
        for name, cfg in self._strategy.baskets.items():
            basket = Basket(name)
            for symbol in cfg.get("universe", []):
                try:
                    sig = self.evaluate_symbol(symbol, basket)
                    signals.append(sig)
                    log.info("%s [%s] -> %s (skor %.2f)", symbol, basket.value, sig.signal.value, sig.score)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Değerlendirme hatası %s: %s", symbol, exc)
        return signals
