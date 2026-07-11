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
from ..data import AlpacaClient, AlphaVantageClient, PerplexityClient, YFinanceClient
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
        # Perplexity: opsiyonel çapraz doğrulama kaynağı (yoksa yalnızca AV kullanılır)
        self._pplx: Optional[PerplexityClient] = None
        if settings.secrets.perplexity_api_key:
            self._pplx = PerplexityClient(settings.secrets)
        self._bars_cache: dict[tuple[str, float], pd.DataFrame] = {}

    # --- Veri ---
    def _get_bars(self, symbol: str, *, years: float = 1.0) -> pd.DataFrame:
        """Önce Alpaca'yı dene; boşsa yfinance'e düş. Koşu boyunca hafızada tutar."""
        key = (symbol, years)
        if key in self._bars_cache:
            return self._bars_cache[key]
        df = self._alpaca.get_daily_bars(symbol, years=years)
        if df.empty:
            df = self._yf.get_daily_bars(symbol, years=years)
        self._bars_cache[key] = df
        return df

    def latest_price(self, symbol: str) -> Optional[float]:
        """Sembolün son kapanış fiyatı (stop-loss / performans için)."""
        df = self._get_bars(symbol, years=0.2)
        if df.empty:
            return None
        return float(df["close"].iloc[-1])

    def _get_fundamental_data(self, symbol: str, price: Optional[float]) -> dict[str, Any]:
        """Temel veriyi çek ve normalize et (Alpha Vantage + varsa Perplexity).

        Her iki kaynak da opsiyoneldir: anahtar yoksa o kaynak atlanır.
        İkisi de yoksa {} döner (teknik ağırlık tam kalır).
        """
        data: dict[str, Any] = {}

        if self._av is not None:
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

        if self._pplx is not None:
            try:
                web = self._pplx.get_web_sentiment(symbol)
                data["web_sentiment_score"] = web.get("score")
                if web.get("summary"):
                    data["web_sentiment_summary"] = web["summary"]
            except Exception as exc:  # noqa: BLE001  (rate-limit/ağ/parse)
                log.warning("Perplexity web duygusu alınamadı (%s): %s", symbol, exc)

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

    def evaluate_symbol(self, symbol: str, basket: Basket, *, fetch_fundamental: bool = True) -> Signal:
        """Tek bir sembol için sinyal üret.

        fetch_fundamental=False iken yalnızca teknik skor kullanılır (Alpha
        Vantage çağrısı yapılmaz). Böylece önce tüm evren ucuza teknik olarak
        taranıp, sadece güçlü adaylar temel veriyle zenginleştirilebilir.
        """
        df = self._get_bars(symbol, years=1.0)
        if df.empty:
            return Signal(symbol, basket, SignalType.HOLD, 0.0, 0.0, reasons=["Veri yok"])

        indicators = compute_indicators(df, self._strategy.technical)
        tech_score, tech_reasons = technical_score(indicators, self._strategy.technical)
        price = indicators.get("close") or float(df["close"].iloc[-1])

        fdata: dict[str, Any] = {}
        fund_reasons: list[str] = []
        if fetch_fundamental:
            fdata = self._get_fundamental_data(symbol, price)
            _, fund_reasons = fundamental_score(fdata, self._strategy.fundamental)

        weight = self._strategy.fundamental.get("weight", 0.35)
        if fdata:
            fund_score, _ = fundamental_score(fdata, self._strategy.fundamental)
            final = (1 - weight) * tech_score + weight * fund_score
        else:
            final = tech_score

        reasons = tech_reasons + fund_reasons
        if not reasons:
            reasons = [self._trend_summary(indicators)]

        return Signal(
            symbol=symbol,
            basket=basket,
            signal=self._decide(final),
            score=min(abs(final), 1.0),
            price=price,
            raw_score=final,
            reasons=reasons,
            technical={k: indicators.get(k) for k in _TECH_LOG_KEYS},
            fundamental=fdata,
        )

    def run(self) -> list[Signal]:
        """Tüm sepetlerdeki evreni tara ve sinyal listesi döndür.

        İki aşama:
          1. Tüm semboller yalnızca teknik olarak değerlendirilir (ucuz).
          2. Teknik olarak en dikkate değer semboller (|skor| >= eşik, en çok N)
             Alpha Vantage + (varsa) Perplexity ile zenginleştirilir — ücretli/
             limitli API'lerin bütçesini aşmadan.
        """
        # 1. Aşama: teknik tarama (fundamental yok)
        results: dict[str, Signal] = {}
        order: list[str] = []
        for name, cfg in self._strategy.baskets.items():
            basket = Basket(name)
            for symbol in cfg.get("universe", []):
                try:
                    sig = self.evaluate_symbol(symbol, basket, fetch_fundamental=False)
                    results[symbol] = sig
                    order.append(symbol)
                    log.info("%s [%s] -> %s (teknik %.2f)", symbol, basket.value, sig.signal.value, sig.raw_score)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Değerlendirme hatası %s: %s", symbol, exc)

        # 2. Aşama: güçlü adayları temel veriyle zenginleştir
        if self._av is not None or self._pplx is not None:
            fcfg = self._strategy.fundamental
            min_abs = fcfg.get("min_technical_abs", 0.20)
            max_syms = fcfg.get("max_symbols_per_run", 6)
            candidates = sorted(
                (s for s in order if abs(results[s].raw_score) >= min_abs),
                key=lambda s: abs(results[s].raw_score),
                reverse=True,
            )[:max_syms]
            log.info("Temel analiz adayları (%d): %s", len(candidates), ", ".join(candidates))
            for symbol in candidates:
                try:
                    enriched = self.evaluate_symbol(symbol, results[symbol].basket, fetch_fundamental=True)
                    results[symbol] = enriched
                    log.info("%s zenginleştirildi -> %s (skor %.2f)", symbol, enriched.signal.value, enriched.raw_score)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Zenginleştirme hatası %s: %s", symbol, exc)

        return [results[s] for s in order]
