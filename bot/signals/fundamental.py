"""Temel analiz skoru.

Girdiler: haber duygusu (Alpha Vantage NEWS_SENTIMENT), kazanç sürprizi
(EARNINGS), analist hedef fiyatı (OVERVIEW), web duygusu (Marketaux
news/all — AV'den bağımsız, ücretsiz bir kaynak, çapraz doğrulama için).
Çıktı: [-1, 1] skor + gerekçeler.

parse_* fonksiyonları ham API yanıtlarını normalize eder; fundamental_score
normalize edilmiş sözlükten skor üretir (ağdan bağımsız test edilebilir).
Veri yoksa skor 0.0 ve boş gerekçe döner (teknik tarafa ağırlık kalır).
"""
from __future__ import annotations

from typing import Any, Optional

from .util import clip

# Alpha Vantage haber duygu skoru kabaca [-0.35, 0.35] aralığında (Bearish..Bullish).
_AV_SENTIMENT_SCALE = 0.35

# İki bağımsız kaynak (AV haber duygusu, Marketaux web duygusu) bu kadardan
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


def parse_marketaux_sentiment(response: dict, symbol: str) -> Optional[float]:
    """Marketaux /news/all yanıtından sembole özgü ortalama duygu skorunu çıkar.

    Her haberin 'entities' listesinde sembolü eşleşen entity'nin
    sentiment_score'u zaten [-1, 1] aralığında; birden fazla haberde
    geçiyorsa ortalaması alınır.
    """
    articles = response.get("data") or []
    scores: list[float] = []
    for article in articles:
        for entity in article.get("entities", []):
            if entity.get("symbol") == symbol:
                try:
                    scores.append(float(entity["sentiment_score"]))
                except (KeyError, TypeError, ValueError):
                    continue
    return sum(scores) / len(scores) if scores else None


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "None", "-", "NaN"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_overview_fundamentals(overview: dict) -> dict:
    """AV OVERVIEW'dan kârlılık ve büyüme alanlarını çıkar."""
    return {
        "profit_margin": _to_float(overview.get("ProfitMargin")),
        "eps": _to_float(overview.get("EPS")),
        "earnings_growth_yoy": _to_float(overview.get("QuarterlyEarningsGrowthYOY")),
        "revenue_growth_yoy": _to_float(overview.get("QuarterlyRevenueGrowthYOY")),
    }


def parse_insider_net(response: dict, *, days: int = 90) -> Optional[dict]:
    """Insider-transactions yanıtından son `days` gündeki net hisse değişimi.

    Döndürür: {net_shares, buys, sells} — net_shares>0 alım, <0 satış. Veri yoksa None.
    """
    from datetime import date, timedelta

    rows = response.get("data") or []
    cutoff = date.today() - timedelta(days=days)
    net = 0.0
    buys = sells = 0
    counted = False
    for r in rows:
        raw_date = r.get("transactionDate") or r.get("filingDate")
        try:
            d = date.fromisoformat(str(raw_date)[:10])
        except (TypeError, ValueError):
            continue
        if d < cutoff:
            continue
        change = _to_float(r.get("change"))
        if change is None:
            continue
        counted = True
        net += change
        if change > 0:
            buys += 1
        elif change < 0:
            sells += 1
    if not counted:
        return None
    return {"net_shares": net, "buys": buys, "sells": sells}


def fundamental_notes(data: dict[str, Any]) -> list[str]:
    """Kullanıcıya AYRICA iletilecek önemli uyarılar (bunlar skoru zaten etkiledi)."""
    notes: list[str] = []

    pm, eps = data.get("profit_margin"), data.get("eps")
    if (pm is not None and pm < 0) or (eps is not None and eps < 0):
        notes.append("⚠️ Şirket zarar ediyor (net marj / EPS negatif).")

    eg = data.get("earnings_growth_yoy")
    if eg is not None and eg <= -0.20:
        notes.append(f"⚠️ Kazançlar yıllık %{eg * 100:.0f} daralıyor.")

    up = data.get("analyst_target_upside_pct")
    if up is not None and abs(up) > 60:
        notes.append(
            f"⚠️ Analist hedefi aşırı uçta (%{up:+.0f}) — belirsizlik yüksek; "
            f"skora katkısı bilinçli olarak kırpıldı."
        )

    ins = data.get("insider_net_shares")
    if ins is not None and ins < 0:
        notes.append(f"⚠️ Son 3 ayda içeriden NET SATIŞ (~{abs(int(ins)):,} hisse).")
    elif ins is not None and ins > 0:
        notes.append(f"✅ Son 3 ayda içeriden net ALIM (~{int(ins):,} hisse) — olumlu.")

    return notes


def fundamental_score(data: dict[str, Any], cfg: dict[str, Any]) -> tuple[float, list[str]]:
    """Normalize edilmiş temel verilerden [-1, 1] skor ve gerekçeleri üret.

    Beklenen anahtarlar (hepsi opsiyonel):
      - news_sentiment_score: float, AV ölçeğinde (~[-0.35, 0.35])
      - earnings_surprise_pct: float, yüzde
      - analyst_target_upside_pct: float, yüzde (aşırı uçlar kırpılır)
      - web_sentiment_score: float, [-1, 1] (Marketaux — bağımsız kaynak)
      - profit_margin: float (0.10 = %10); negatifse ceza
      - earnings_growth_yoy: float (0.30 = +%30 YoY)
      - insider_net_shares: float; >0 alım, <0 satış
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
        # ±%25 potansiyel → ±1 skor. Aşırı uçlar (>%60) güvenilirliği düşük
        # olduğu için katkısı kırpılır (ör. LUNR %+153 gibi şişkin hedefler).
        comp = clip(up / 25.0, -1, 1)
        if abs(up) > 60:
            comp *= 0.4
        components.append(comp)
        reasons.append(f"Analist hedefi %{up:+.0f} potansiyel")

    # --- Kârlılık (net marj / EPS) ---
    pm = data.get("profit_margin")
    if pm is not None:
        components.append(clip(pm * 4, -0.6, 0.6))   # +%15 marj → +0.6; zarar → negatif
        if pm < 0:
            reasons.append("Şirket zararda (net marj negatif)")

    # --- Kazanç büyümesi (YoY) ---
    eg = data.get("earnings_growth_yoy")
    if eg is not None:
        components.append(clip(eg / 0.30, -1, 1))    # +%30 YoY → +1
        reasons.append(f"Kazanç büyümesi (YoY) %{eg * 100:+.0f}")

    # --- İçeriden işlem (son ~3 ay net) ---
    ins = data.get("insider_net_shares")
    if ins is not None:
        if ins > 0:
            components.append(0.3)
            reasons.append("İçeriden net alım (olumlu)")
        elif ins < 0:
            components.append(-0.3)
            reasons.append("İçeriden net satış")

    ws = data.get("web_sentiment_score")
    if ws is not None:
        components.append(clip(ws, -1, 1))
        label = "pozitif" if ws > 0.15 else "negatif" if ws < -0.15 else "nötr"
        reasons.append(f"Web duygusu (Marketaux) {ws:+.2f} ({label})")

    # Çapraz doğrulama: iki bağımsız kaynak ters yöne işaret ediyorsa uyar
    if ns_norm is not None and ws is not None and abs(ns_norm - ws) >= _DISAGREEMENT_THRESHOLD:
        reasons.append(
            f"⚠️ Kaynaklar çelişkili (AV {ns_norm:+.2f} vs Marketaux {ws:+.2f}) — dikkatli değerlendirin"
        )

    if not components:
        return 0.0, []

    return clip(sum(components) / len(components), -1, 1), reasons
