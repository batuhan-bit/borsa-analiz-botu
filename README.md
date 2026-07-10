# Borsa Analiz Botu

Teknik + temel analiz karışımıyla günlük **sinyal/bildirim** üreten bir bot.
Bot gerçek alım-satım yapmaz — sinyalleri üretir, Slack'e bildirir ve Google
Sheets'e loglar. Alım-satım kararını ve işlemi kullanıcı **manuel** yürütür.

> ⚠️ Bu bir yatırım tavsiyesi aracı değildir. Üretilen sinyaller eğitim/analiz
> amaçlıdır; tüm işlem kararları ve sorumluluğu kullanıcıya aittir.

## Strateji Özeti

| Parametre | Değer |
|---|---|
| Bütçe | $1,000 – $5,000 (3 aylık) |
| Hedef | 3 ayda %6.5 portföy getirisi |
| Pozisyon | 6 (her sepette 2) |
| Yürütme | Manuel |
| Stop-loss | Pozisyon bazlı %20 (portföy seviyesi yok) |
| Bildirim | Günde 1, piyasa kapanışı sonrası (Slack) |

**Sepetler:** Düşük volatilite (%40) · Yüksek volatilite (%35) · Radar altı (%25)

**Sinyaller:** RSI, MACD, 50/200 MA kesişimi, hacim teyidi + haber/kazanç/analist verisi.

Tüm strateji parametreleri [`config/strategy.yaml`](config/strategy.yaml) içinde;
kod değişmeden ayarlanabilir.

## Mimari

```
bot/
├── config.py          # sırlar (.env) + strateji (yaml) yükleme
├── models.py          # Signal, Basket, SignalType ortak tipleri
├── data/              # Alpaca · yfinance · Alpha Vantage istemcileri
├── signals/           # technical · fundamental · engine (skor birleştirme)
├── risk/              # pozisyon bazlı %20 stop-loss
├── notify/            # Slack webhook bildirimi
├── logging/           # Google Sheets loglama
└── main.py            # uçtan uca akış (GitHub Actions bunu çalıştırır)
backtest/              # 3 yıllık strateji doğrulaması
.github/workflows/     # günlük zamanlanmış çalıştırma (cron)
```

## Kurulum

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Linux/Mac:           source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # değerleri doldurun (Windows: copy)
```

Gerekli sırlar (`.env` veya GitHub Secrets): `ALPACA_API_KEY`,
`ALPACA_SECRET_KEY`, `ALPHA_VANTAGE_API_KEY`, `SLACK_WEBHOOK_URL`,
`GOOGLE_SHEET_ID` ve Google service account (dosya ya da
`GOOGLE_SERVICE_ACCOUNT_JSON`).

## Çalıştırma

```bash
python -m bot.main              # günlük analizi bir kez çalıştır
python -m backtest.backtest     # 3 yıllık backtest
pytest                          # testler
```

GitHub Actions [`daily.yml`](.github/workflows/daily.yml) her hafta içi
22:00 UTC'de otomatik çalıştırır (elle tetikleme: `workflow_dispatch`).

## Geliştirme Durumu

- [x] 1. Repo iskeleti + requirements.txt
- [x] 2. Veri çekme modülleri (Alpaca, yfinance, Alpha Vantage)
- [x] 3. Sinyal motoru (teknik + temel) + pozisyon bazlı stop-loss
- [x] 4. Backtesting scripti (3 yıl, yalnızca teknik)
- [x] 5. Slack bildirim modülü
- [ ] 6. Google Sheets loglama
- [ ] 7. GitHub Actions workflow (iskelet hazır)
- [ ] 8. Uçtan uca test
