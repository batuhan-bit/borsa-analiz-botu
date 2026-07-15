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

**Sinyaller:** RSI, MACD, 50/200 MA kesişimi, hacim teyidi + haber/kazanç/analist
verisi (Alpha Vantage) + bağımsız web duygusu (Marketaux, ücretsiz opsiyonel
çapraz doğrulama — iki kaynak ters düşerse sinyalde "⚠️ Kaynaklar çelişkili" uyarısı).

Tüm strateji parametreleri [`config/strategy.yaml`](config/strategy.yaml) içinde;
kod değişmeden ayarlanabilir.

## Beklentiler ve Devreye Alma

> Bu bölüm, **v2 kesitsel momentum rotasyonunun** canlıya alınma sözleşmesidir
> (Faz D). Yukarıdaki "Strateji Özeti" tablosundaki *3 ayda %6.5* rakamı v1'den
> kalma bir hedeftir ve **bu ürünün vaadi DEĞİLDİR** — dürüst beklenti aşağıdadır.

### Zaman ufku ve dürüst beklenti

- **Minimum bağlılık: 12 ay.** Adil değerlendirme için **3 yıl** gerekir.
  **İlk çeyrek istatistiksel gürültüdür** ve tek başına hiçbir karara dayanak olmaz.
- **Beklenti çıpası backtest DEĞİLDİR.** Evren survivorship/hindsight bias içerir
  (bugün öne çıkan hisselerden kurulu); mutlak backtest getirileri (ör. final
  penceresi medyan %+349) **şişkin okunmalıdır**. Gerçekçi çıpa uzun vadeli hisse
  ortalaması **~%10/yıl**'dır. Bu sınıf stratejide **−%25–35 düşüşler normaldir**.
- **Maliyet sürüklemesi bilerek üstlenilir.** $1.000 başlangıçta yıllık toplam
  maliyet / ortalama sermaye oranı medyan **~%14.7/yıl**'dır ($3.000'de ~%3.7);
  fark, işlem başına $1.50 sabit ücretin küçük pozisyonda (~$125–200) oransal
  büyümesinden gelir (kaynak: [`results/small_budget_1000.md`](results/small_budget_1000.md), Görev D.2).

### Başarı kıstası (performans hükmü — yalnız 12. ay)

- Yuvarlanan **12 aylık getiri ≥ SPY** **VE** maksimum düşüş **≤ 1.5×SPY düşüşü**.
- **Evren al-tut** her raporda bir bilgi kolonu olarak gösterilir (çıpa değil, bağlam).
- **12. ayda takvimli gözden geçirme:** *devam / revize / durdur*.

### Düşük bütçeli canlı dönem ($1.000, 3 ay)

- **$1.000 başlangıç**, ilk **3 ay boyunca nakit girişi yok**. Bu tutar kullanıcı
  tarafından **tamamen kaybedilebilir risk sermayesi** olarak tanımlanmıştır.
- **3. ay kapısının ölçütleri OPERASYONELDİR, performans DEĞİLDİR.** 3 aylık getiri
  gürültüdür; nakit-artırma kararına tek başına dayanak yapılmaz. Kontrol edilenler:
  - Karne elle **müdahalesiz doluyor mu** (5/20/60g ileri getiri otomatik).
  - **Gerçekleşen maliyet vs D.2 tahmini** (~%14.7/yıl oranından sapma raporlanır).
  - **Öneri → icra gecikmesi** (sinyal ile elle işlem arasındaki gün).
  - **Sistem-dışı işlem sayısı** (hedef **0** — sistemin önermediği elle işlemler).
  - **Satış uyarılarının işlerliği** (tetikler zamanında ve doğru geliyor mu).
- **Performans hükmü yalnız 12. ayda**, yukarıdaki mutabık kıstasla verilir.

### Canlı sistemin bilinen iki sınırlaması

- **(a) Temel kırmızı-bayrak satış tetiği canlıda şu an UYKUDA.** Yalnız **teknik
  acil** + **sıralama çöküşü** tetikleri aktiftir; kazanç/haber/içeriden-satış
  temelli çıkış makinesi (A.3) hazırdır ama veri sağlayıcı bağlanana kadar pasiftir.
- **(b) Evren survivorship/hindsight bias içerir** (yukarıda; backtest getirileri
  şişkin, canlı çıpa ~%10/yıl).

### 🔲 TASLAK — kullanıcı onayı bekleyen sayısal eşikler

Aşağıdaki eşikler **taslaktır**; canlıya alma öncesi kullanıcı onayı gerekir:

| Kapı | Ölçüt | Taslak eşik |
|---|---|---|
| 3. ay (operasyonel) | Karne otomatik doluluk | %100 (elle müdahale 0) |
| 3. ay (operasyonel) | Gerçekleşen/tahmini maliyet sapması | ≤ ±%25 (D.2 ~%14.7/yıl çıpasına göre) |
| 3. ay (operasyonel) | Öneri → icra gecikmesi | ≤ 1 işlem günü |
| 3. ay (operasyonel) | Sistem-dışı işlem sayısı | 0 |
| 12. ay (performans) | Yuvarlanan 12a getiri | ≥ SPY |
| 12. ay (performans) | Maksimum düşüş | ≤ 1.5 × SPY düşüşü |

> Kur/transfer maliyetleri bot kapsamı dışıdır (broker/banka tarafında oluşur).

## Mimari

```
bot/
├── config.py          # sırlar (.env) + strateji (yaml) yükleme
├── models.py          # Signal, Basket, SignalType ortak tipleri
├── data/              # Alpaca · yfinance · Alpha Vantage · Marketaux istemcileri
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

Sırlar (`.env` veya GitHub Secrets):

| Değişken | Durum | Not |
|---|---|---|
| `SLACK_WEBHOOK_URL` | **Zorunlu** | Botun tek çıktısı; olmadan çalışmaz |
| `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` | Opsiyonel | Yoksa **yfinance**'e düşülür (anahtar gerekmez) |
| `ALPHA_VANTAGE_API_KEY` | Opsiyonel | Yoksa yalnızca teknik analiz |
| `MARKETAUX_API_KEY` | Opsiyonel | Yoksa çapraz doğrulama atlanır, yalnızca AV kullanılır (ücretsiz — [marketaux.com/register](https://marketaux.com/register)) |
| `GOOGLE_SHEET_ID` + service account (`GOOGLE_SERVICE_ACCOUNT_JSON` veya dosya) | Opsiyonel | Yoksa loglama/stop-loss atlanır |

Tasarım gereği her entegrasyon zarifçe devre dışı kalabilir; bir sağlayıcıdaki
kesinti (ör. Alpaca) botu durdurmaz.

## Çalıştırma

```bash
python -m bot.main              # günlük analizi bir kez çalıştır
python -m backtest.backtest     # 3 yıllık backtest
pytest                          # testler
```

GitHub Actions [`daily.yml`](.github/workflows/daily.yml) her hafta içi
22:00 UTC'de otomatik çalıştırır (elle tetikleme: `workflow_dispatch`).

## Google Sheet Yapısı

Bot, Sheet ID ile verilen dokümanda üç sekme kullanır (yoksa otomatik oluşturur):

| Sekme | Kim yazar | İçerik |
|---|---|---|
| **Sinyaller** | Bot | Üretilen her sinyal (zaman, sembol, sepet, sinyal, skor, fiyat, gerekçe) |
| **Pozisyonlar** | **Siz** | Açık pozisyonlarınız — stop-loss buradan hesaplanır |
| **Performans** | Bot | Günlük portföy değeri + sinyal sayaçları |

**Pozisyonlar** sekmesi sütunları: `Sembol · Sepet · Giriş Tarihi · Giriş Fiyatı · Adet · Durum`.
Manuel bir alım yaptığınızda buraya bir satır ekleyin; `Durum` `KAPALI` olmadıkça
pozisyon açık kabul edilir ve %20 stop-loss kontrolüne girer.

> Service account e-postasına Sheet'te **düzenleyici** erişimi vermeyi unutmayın.

## Geliştirme Durumu

- [x] 1. Repo iskeleti + requirements.txt
- [x] 2. Veri çekme modülleri (Alpaca, yfinance, Alpha Vantage)
- [x] 3. Sinyal motoru (teknik + temel) + pozisyon bazlı stop-loss
- [x] 4. Backtesting scripti (3 yıl, yalnızca teknik)
- [x] 5. Slack bildirim modülü
- [x] 6. Google Sheets loglama
- [x] 7. GitHub Actions workflow (günlük çalıştırma + CI testleri)
- [x] 8. Uçtan uca test (canlı Actions koşusu doğrulandı)

**Tüm adımlar tamamlandı.** Bot günlük olarak çalışır, teknik + temel analizle
sinyal üretir, Google Sheets'e loglar ve Slack'e bildirim gönderir.
