# Backtest Doğrulama Raporu — Faz 1 (Görev 1.1, 1.2, 1.3)

_Üretim: 2026-07-13 15:26 · `python -m backtest.report` · strategy.yaml parametreleri DONDURULMUŞ (Faz 1 kuralı)_

## 1) Ana dönem: son 3 yıl (in-sample)

Dönem: **2023-07-10 → 2026-07-10** · Başlangıç sermayesi: $3,000 · Yalnızca teknik sinyaller (temel katman backtest dışı).

| Konfigürasyon | Toplam % | Yıllık % | Maks DD % | Sharpe | Calmar | İşlem | Ort. işlem % | Toplam getiri %90 GA |
|---|---|---|---|---|---|---|---|---|
| Strateji (mevcut config) | +187.71 | +42.22 | -25.54 | 1.20 | 1.65 | 28 | +10.42 | [-23.42 … +105.29] |
| Eşit-ağırlık evren (al-tut) | +276.15 | +55.50 | -36.26 | 1.34 | 1.53 | — | — | — |
| Sepet-ağırlıklı evren (al-tut) | +243.02 | +50.80 | -31.94 | 1.37 | 1.59 | — | — | — |
| SPY (al-tut) | +78.24 | +21.24 | -18.76 | 1.34 | 1.13 | — | — | — |

- **Strateji (mevcut config)** alfa: -88.4 puan vs Eşit-ağırlık evren (al-tut); -55.3 puan vs Sepet-ağırlıklı evren (al-tut); +109.5 puan vs SPY (al-tut)

> Not: Evren bugünden geriye seçildiği için bu dönem hindsight bias içerir; benchmark aynı evreni kullandığından alfa kıyası yine de anlamlıdır. Parametreler bu döneme bakılarak ayarlandığı için bu tablo IN-SAMPLE'dır.

## 2) 2016-2022 dönemi (fiilen out-of-sample)

Parametreler 2023-2026 verisine bakılarak ayarlandı; 2016-2022 görülmemiş veridir. Üç konfigürasyon varyantı, aynı dondurulmuş eşiklerle:

| Konfigürasyon | Toplam % | Yıllık % | Maks DD % | Sharpe | Calmar | İşlem | Ort. işlem % | Toplam getiri %90 GA |
|---|---|---|---|---|---|---|---|---|
| (a) Trend filtresi kapalı | +256.01 | +19.93 | -27.60 | 0.99 | 0.72 | 191 | +4.38 | [+100.33 … +393.62] |
| (b) Trend filtresi açık | +521.93 | +29.90 | -39.50 | 1.00 | 0.76 | 48 | +47.81 | [+37.36 … +841.21] |
| (c) Trend + yönlü hacim + R/R | +122.32 | +12.11 | -44.47 | 0.58 | 0.27 | 41 | +15.02 | [-65.82 … +339.76] |
| Eşit-ağırlık evren (al-tut) | +293.17 | +21.65 | -38.97 | 0.90 | 0.56 | — | — | — |
| Sepet-ağırlıklı evren (al-tut) | +285.04 | +21.28 | -39.24 | 0.90 | 0.54 | — | — | — |
| SPY (al-tut) | +115.77 | +11.64 | -33.72 | 0.67 | 0.35 | — | — | — |

- **(a) Trend filtresi kapalı** alfa: -37.2 puan vs Eşit-ağırlık evren (al-tut); -29.0 puan vs Sepet-ağırlıklı evren (al-tut); +140.2 puan vs SPY (al-tut)
- **(b) Trend filtresi açık** alfa: +228.8 puan vs Eşit-ağırlık evren (al-tut); +236.9 puan vs Sepet-ağırlıklı evren (al-tut); +406.2 puan vs SPY (al-tut)
- **(c) Trend + yönlü hacim + R/R** alfa: -170.9 puan vs Eşit-ağırlık evren (al-tut); -162.7 puan vs Sepet-ağırlıklı evren (al-tut); +6.5 puan vs SPY (al-tut)

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

Soru: koruyucu özellikler (trend filtresi, yönlü hacim, R/R kapısı) düşüş rejimlerinde gerçekten koruyor mu? (2016-2022 koşularının pencere içi kesitleri)

**2018 Q4 düzeltmesi** (2018-10-01 → 2018-12-31)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | -16.78 | -20.93 |
| (b) Trend filtresi açık | -31.25 | -34.35 |
| (c) Trend + yönlü hacim + R/R | -40.63 | -44.21 |
| Eşit-ağırlık evren (al-tut) | -16.50 | -21.69 |
| Sepet-ağırlıklı evren (al-tut) | -16.60 | -21.85 |
| SPY (al-tut) | -13.83 | -19.20 |

**Mart 2020 çöküşü** (2020-02-01 → 2020-04-30)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | -13.87 | -25.50 |
| (b) Trend filtresi açık | -9.21 | -32.97 |
| (c) Trend + yönlü hacim + R/R | -9.20 | -28.66 |
| Eşit-ağırlık evren (al-tut) | -1.39 | -27.37 |
| Sepet-ağırlıklı evren (al-tut) | -1.23 | -27.47 |
| SPY (al-tut) | -9.85 | -33.72 |

**2022 ayı piyasası** (2022-01-01 → 2022-12-31)

| Konfigürasyon | Pencere getirisi % | Pencere içi maks DD % |
|---|---|---|
| (a) Trend filtresi kapalı | +8.33 | -13.23 |
| (b) Trend filtresi açık | -1.26 | -19.30 |
| (c) Trend + yönlü hacim + R/R | -26.39 | -28.19 |
| Eşit-ağırlık evren (al-tut) | -25.26 | -36.86 |
| Sepet-ağırlıklı evren (al-tut) | -26.81 | -37.98 |
| SPY (al-tut) | -18.65 | -24.50 |

## Sınırlamalar (dürüstlük notları)

- **Evren önyargısı:** 60 sembol bugünden geriye seçildi (survivorship/hindsight
  bias). Benchmark aynı evreni kullandığı için alfa ölçümü bu önyargıyı büyük
  ölçüde nötrler, ama mutlak getiriler şişkin okunmalıdır.
- **Dolgu fiyatı:** Mevcut backtest sinyal günü kapanışından dolduruyor;
  ertesi-gün-açılış dolgusu ve komisyon/kayma Görev 2.1'de ele alınacak.
- **Temel katman backtest dışı:** Bu rapor yalnızca teknik sinyalleri ölçer;
  canlıdaki %35 ağırlıklı temel katman point-in-time test edilemedi (Görev 3.1).
- **Küçük örneklem:** İşlem sayıları düşük; GA'lar geniş. GA'ları çakışan
  konfigürasyonlar arasında üstünlük iddia edilemez.
