# Backtest Doğrulama Raporu — Faz 2 (Sizing v2 + gerçekçilik katmanı)

_Üretim: 2026-07-13 17:14 · `python -m backtest.report` · strategy.yaml eşikleri ve skor ağırlıkları DONDURULMUŞ (yalnız boyutlandırma/dolgu/maliyet katmanı değişti)_

**Birincil rakamlar** artık gerçekçi: pozisyon boyutlandırma **v2** (deployment %95, min-dolum %60, tam adet), dolgu **ertesi-gün-açılışı**, işlem maliyeti **10 bps/işlem** (komisyon+kayma). Son iki kolon eski **legacy** koşuyu (sepet-sıralı boyut, kapanış dolgusu, **maliyetsiz**) ve farkı gösterir — Görev 2.1 (dolgu+maliyet) ile 2.2 (boyutlandırma) birlikte.

## 1) Ana dönem: son 3 yıl (in-sample)

Dönem: **2023-07-10 → 2026-07-10** · Başlangıç sermayesi: $3,000 · Yalnızca teknik sinyaller (temel katman backtest dışı).

| Konfigürasyon | Toplam % | Yıllık % | Maks DD % | Sharpe | Calmar | İşlem | Ort. işlem % | Toplam getiri %90 GA | Legacy Top.% (maliyetsiz) | Δ Top.% |
|---|---|---|---|---|---|---|---|---|---|---|
| Strateji (mevcut config) | +73.01 | +20.04 | -32.24 | 0.74 | 0.62 | 26 | +7.96 | [-22.05 … +73.98] | +187.71 | -114.70 |
| Eşit-ağırlık evren (al-tut) | +276.15 | +55.50 | -36.26 | 1.34 | 1.53 | — | — | — | — | — |
| Sepet-ağırlıklı evren (al-tut) | +243.02 | +50.80 | -31.94 | 1.37 | 1.59 | — | — | — | — | — |
| SPY (al-tut) | +78.24 | +21.24 | -18.76 | 1.34 | 1.13 | — | — | — | — | — |

- **Strateji (mevcut config)** alfa: -203.1 puan vs Eşit-ağırlık evren (al-tut); -170.0 puan vs Sepet-ağırlıklı evren (al-tut); -5.2 puan vs SPY (al-tut)

> Not: Evren bugünden geriye seçildiği için bu dönem hindsight bias içerir; benchmark aynı evreni kullandığından alfa kıyası yine de anlamlıdır. Parametreler bu döneme bakılarak ayarlandığı için bu tablo IN-SAMPLE'dır. Benchmark'lar pasif al-tut olduğundan boyutlandırma/maliyetten etkilenmez.

## 2) 2016-2022 dönemi (fiilen out-of-sample)

Parametreler 2023-2026 verisine bakılarak ayarlandı; 2016-2022 görülmemiş veridir. Üç konfigürasyon varyantı, aynı dondurulmuş eşiklerle:

| Konfigürasyon | Toplam % | Yıllık % | Maks DD % | Sharpe | Calmar | İşlem | Ort. işlem % | Toplam getiri %90 GA | Legacy Top.% (maliyetsiz) | Δ Top.% |
|---|---|---|---|---|---|---|---|---|---|---|
| (a) Trend filtresi kapalı | +231.98 | +18.74 | -27.76 | 0.91 | 0.67 | 190 | +4.48 | [+64.27 … +379.44] | +256.01 | -24.03 |
| (b) Trend filtresi açık | +441.82 | +27.38 | -35.03 | 1.04 | 0.78 | 39 | +27.54 | [+63.05 … +608.84] | +521.93 | -80.11 |
| (c) Trend + yönlü hacim + R/R | +139.72 | +13.33 | -48.60 | 0.63 | 0.27 | 30 | +22.07 | [-6.01 … +286.94] | +122.32 | +17.40 |
| Eşit-ağırlık evren (al-tut) | +293.17 | +21.65 | -38.97 | 0.90 | 0.56 | — | — | — | — | — |
| Sepet-ağırlıklı evren (al-tut) | +285.04 | +21.28 | -39.24 | 0.90 | 0.54 | — | — | — | — | — |
| SPY (al-tut) | +115.77 | +11.64 | -33.72 | 0.67 | 0.35 | — | — | — | — | — |

- **(a) Trend filtresi kapalı** alfa: -61.2 puan vs Eşit-ağırlık evren (al-tut); -53.1 puan vs Sepet-ağırlıklı evren (al-tut); +116.2 puan vs SPY (al-tut)
- **(b) Trend filtresi açık** alfa: +148.6 puan vs Eşit-ağırlık evren (al-tut); +156.8 puan vs Sepet-ağırlıklı evren (al-tut); +326.1 puan vs SPY (al-tut)
- **(c) Trend + yönlü hacim + R/R** alfa: -153.5 puan vs Eşit-ağırlık evren (al-tut); -145.3 puan vs Sepet-ağırlıklı evren (al-tut); +24.0 puan vs SPY (al-tut)

### İstatistiksel değerlendirme (bootstrap %90 GA, Görev 1.3)

- ⚠ '(a) Trend filtresi kapalı' vs '(b) Trend filtresi açık': güven aralıkları çakışıyor — fark örneklem gürültüsünden ayırt edilemiyor.
- ⚠ '(a) Trend filtresi kapalı' vs '(c) Trend + yönlü hacim + R/R': güven aralıkları çakışıyor — fark örneklem gürültüsünden ayırt edilemiyor.
- ⚠ '(b) Trend filtresi açık' vs '(c) Trend + yönlü hacim + R/R': güven aralıkları çakışıyor — fark örneklem gürültüsünden ayırt edilemiyor.

### Kapsam raporu (Görev 1.2 politikası: sembol, verisi başladığı gün katılır)

| Sepet | Dönem başında aktif | Sonradan katılan | Verisi yok |
|---|---|---|---|
| low_volatility | 20/20 | — | — |
| high_volatility | 16/20 | CRSP (2016-10-19), MRNA (2018-12-07), PLTR (2020-09-30) | ARM |
| under_radar | 5/20 | APP (2021-04-15), ASTS (2019-11-01), FLNC (2021-10-28), HIMS (2019-09-13), IONQ (2021-01-04), LUNR (2021-11-17), OKLO (2021-07-08), QBTS (2020-12-11), RGTI (2021-04-22), RKLB (2020-11-24), SMR (2022-03-01), SYM (2021-03-09) | NNE, TEM, ALAB |

## 3) Rejim bazlı alt-rapor: ayı piyasalarında koruma

Soru: koruyucu özellikler (trend filtresi, yönlü hacim, R/R kapısı) düşüş rejimlerinde gerçekten koruyor mu? (2016-2022 v2 koşularının pencere içi kesitleri)

**2018 Q4 düzeltmesi** (2018-10-01 → 2018-12-31)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | -15.54 | -20.37 |
| (b) Trend filtresi açık | -30.78 | -35.03 |
| (c) Trend + yönlü hacim + R/R | -37.03 | -40.41 |
| Eşit-ağırlık evren (al-tut) | -16.50 | -21.69 |
| Sepet-ağırlıklı evren (al-tut) | -16.60 | -21.85 |
| SPY (al-tut) | -13.83 | -19.20 |

**Mart 2020 çöküşü** (2020-02-01 → 2020-04-30)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | -10.27 | -25.33 |
| (b) Trend filtresi açık | -10.71 | -30.77 |
| (c) Trend + yönlü hacim + R/R | -20.70 | -27.99 |
| Eşit-ağırlık evren (al-tut) | -1.39 | -27.37 |
| Sepet-ağırlıklı evren (al-tut) | -1.23 | -27.47 |
| SPY (al-tut) | -9.85 | -33.72 |

**2022 ayı piyasası** (2022-01-01 → 2022-12-31)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | -1.77 | -16.23 |
| (b) Trend filtresi açık | +5.74 | -18.53 |
| (c) Trend + yönlü hacim + R/R | -17.88 | -22.07 |
| Eşit-ağırlık evren (al-tut) | -25.26 | -36.86 |
| Sepet-ağırlıklı evren (al-tut) | -26.81 | -37.98 |
| SPY (al-tut) | -18.65 | -24.50 |

## Sınırlamalar (dürüstlük notları)

- **Evren önyargısı:** 60 sembol bugünden geriye seçildi (survivorship/hindsight
  bias). Benchmark aynı evreni kullandığı için alfa ölçümü bu önyargıyı büyük
  ölçüde nötrler, ama mutlak getiriler şişkin okunmalıdır.
- **Dolgu fiyatı (Görev 2.1 ✓):** Birincil koşular artık sinyal günü kapanışında
  karar verip ERTESİ GÜN AÇILIŞINDAN dolduruyor ve her işleme komisyon+kayma
  uyguluyor. Günlük özsermaye yine kapanıştan işaretlenir (giriş ertesi açılıştan
  kaydedildiğinden en çok 1 günlük işaretleme gecikmesi kalır — toplam getiriye
  etkisi ihmal edilebilir).
- **Boyutlandırma (Görev 2.2 ✓):** Birincil koşular v2 kullanır — aynı gün adaylar
  nakdi hedef ağırlıkları oranında paylaşır (sepet sırası avantajı yok), dolum
  min_fill_pct altındaysa pozisyon ertelenir, toplam dağıtım deployment_pct ile
  sınırlıdır. Legacy kolonu eski nakit-açlığı davranışını kıyas için korur.
- **Temel katman backtest dışı:** Bu rapor yalnızca teknik sinyalleri ölçer;
  canlıdaki %35 ağırlıklı temel katman point-in-time test edilemedi (Görev 3.1).
- **Küçük örneklem:** İşlem sayıları düşük; GA'lar geniş. GA'ları çakışan
  konfigürasyonlar arasında üstünlük iddia edilemez.
