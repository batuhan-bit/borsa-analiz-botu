"""Temel analiz skoru.

Girdiler: haber duygusu (Alpha Vantage NEWS_SENTIMENT), kazanç sürprizi
(EARNINGS), analist hedef fiyatı (OVERVIEW), web duygusu (Perplexity — Alpha
Vantage'dan bağımsız bir kaynak, çapraz doğrulama için). Çıktı: [-1, 1] skor
+ gerekçeler.

parse_* fonksiyonları ham Alpha Vantage yanıtlarını normalize eder;
fundamental_score normalize edilmiş sözlükten skor üretir (ağdan bağımsız test
edilebilir). Veri yoksa skor 0.0 ve boş gerekçe döner (teknik tarafa ağırlık kalır).
"""
from __future__ import annotations

from typing import Any, Optional

from .util import clip

# Alpha Vantage haber duygu skoru kabaca [-0.35, 0.35] aralığında (Bearish..Bullish).
_AV_SENTIMENT_SCALE = 0.35

# İki bağımsız kaynak (AV haber duygusu, Perplexity web duygusu) bu kadardan
# fazla ayrışırsa (normalize [-1,1] skalada) "çelişkili kaynak" uyarısı verilir.
_DISAGREEMENT_THRESHOLD = 0.6


def parse_news_sentiment(response: dict, symbol: str) -> Optional[float]:
    """NEWS_SENTIMENT yanıtından sembole özgü ortalama duygu skorunu çıkar."""
    feed = response.get("feed") or []
    scores: list[float] = []
    for article in feed:
        for ticker_sent in article.get("ticker_sentiment", []):
            if ticker_sent.get("ticker") == symbol:
                try:
                    scores.append(float(ticker_sent["ticker_sentiment_score"]))
                except (KeyError, TypeError, ValueError):
                    continue
    return sum(scores) / len(scores) if scores else None


def parse_earnings_surprise(response: dict) -> Optional[float]:
    """EARNINGS yanıtından en son çeyreğin sürpriz yüzdesini çıkar."""
    quarterly = response.get("quarterlyEarnings") or []
    if not quarterly:
        return None
    try:
        return float(quarterly[0].get("surprisePercentage"))
    except (TypeError, ValueError):
        return None


def parse_analyst_upside(overview: dict, price: Optional[float]) -> Optional[float]:
    """OVERVIEW'daki analist hedef fiyatından yüzde yükseliş potansiyeli hesapla."""
    if not price:
        return None
    try:
        target = float(overview.get("AnalystTargetPrice"))
    except (TypeError, ValueError):
        return None
    if target <= 0:
        return None
    return (target - price) / price * 100


def fundamental_score(data: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Normalize edilmiş temel verilerden [-1, 1] skor ve gerekçeleri üret.

    Beklenen anahtarlar (hepsi opsiyonel):
      - news_sentiment_score: float, AV ölçeğinde (~[-0.35, 0.35])
      - earnings_surprise_pct: float, yüzde
      - analyst_target_upside_pct: float, yüzde
      - web_sentiment_score: float, [-1, 1] (Perplexity — bağımsız kaynak)
    """
    components: list[float] = []
    reasons: list[str] = []

    ns_norm: Optional[float] = None
    ns = data.get("news_sentiment_score")
    if ns is not None:
        ns_norm = clip(ns / _AV_SENTIMENT_SCALE, -1, 1)
        components.append(ns_norm)
        label = "pozitif" if ns > 0.15 else "negatif" if ns < -0.15 else "nötr"
        reasons.append(f"Haber duygusu (AV) {ns:+.2f} ({label})")

    es = data.get("earnings_surprise_pct")
    if es is not None:
        # ±%10 sürpriz → ±1 skor
        components.append(clip(es / 10.0, -1, 1))
        reasons.append(f"Kazanç sürprizi %{es:+.1f}")

    up = data.get("analyst_target_upside_pct")
    if up is not None:
        # ±%25 potansiyel → ±1 skor
        components.append(clip(up / 25.0, -1, 1))
        reasons.append(f"Analist hedefi %{up:+.0f} potansiyel")

    ws = data.get("web_sentiment_score")
    if ws is not None:
        components.append(clip(ws, -1, 1))
        label = "pozitif" if ws > 0.15 else "negatif" if ws < -0.15 else "nötr"
        reasons.append(f"Web duygusu (Perplexity) {ws:+.2f} ({label})")

    # Çapraz doğrulama: iki bağımsız kaynak ters yöne işaret ediyorsa uyar
    if ns_norm is not None and ws is not None and abs(ns_norm - ws) >= _DISAGREEMENT_THRESHOLD:
        reasons.append(
            f"⚠️ Kaynaklar çelişkili (AV {ns_norm:+.2f} vs Perplexity {ws:+.2f}) — dikkatli değerlendirin"
        )

    if not components:
        return 0.0, []

    return clip(sum(components) / len(components), -1, 1), reasons
