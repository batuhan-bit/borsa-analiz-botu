# 2016-2022 İşlem Dökümü — Varyant (b): Yalnız Trend Filtresi Açık

_Dönem: 2016-01-04 → 2022-12-30 · Başlangıç sermayesi: $3,000 · Toplam getiri: %+521.93 · Kaynak: `python -m backtest.backtest --start 2016-01-01 --end 2022-12-31 --no-volume-direction --no-rr-gate`_

Toplam 54 kayıt: **48 kapanmış işlem** (35 SELL sinyali, 13 stop-loss) + **6 pozisyon dönem sonunda açıktı** (son fiyattan değerlendi). Kapanmış işlemlerde kazanma oranı: %39.6. Fiyatlar temettü/bölünme düzeltmelidir.

| # | Sembol | Sepet | Giriş | Çıkış | Süre (gün) | Giriş $ | Çıkış $ | Çıkış nedeni | Getiri % | PnL $ |
|--:|--------|-------|-------|-------|-----------:|--------:|--------:|--------------|---------:|------:|
| 1 | KMB | düşük vol | 2016-01-04 | 2016-10-05 | 275 | 87.68 | 86.84 | SELL sinyali | -0.96 | -5.06 |
| 2 | XLU | düşük vol | 2016-01-04 | 2016-11-14 | 315 | 15.49 | 16.90 | SELL sinyali | +9.11 | +53.62 |
| 3 | NVDA | yüksek vol | 2016-01-06 | 2016-02-08 | 33 | 0.77 | 0.61 | stop-loss | -20.01 | -105.46 |
| 4 | TSM | yüksek vol | 2016-01-29 | 2018-06-18 | 871 | 17.13 | 31.40 | SELL sinyali | +83.35 | +428.23 |
| 5 | ANF | radar-altı | 2016-02-02 | 2016-05-27 | 115 | 21.68 | 16.70 | stop-loss | -23.00 | -84.77 |
| 6 | NVDA | yüksek vol | 2016-02-17 | 2018-11-16 | 1003 | 0.67 | 4.07 | SELL sinyali | +503.60 | +2613.10 |
| 7 | CELH | radar-altı | 2016-04-27 | 2016-09-23 | 149 | 0.78 | 0.68 | SELL sinyali | -12.39 | -46.88 |
| 8 | POWL | radar-altı | 2016-07-05 | 2017-03-31 | 269 | 10.20 | 9.14 | SELL sinyali | -10.39 | -28.63 |
| 9 | PG | düşük vol | 2016-10-06 | 2018-02-16 | 498 | 68.45 | 66.36 | SELL sinyali | -3.05 | -22.99 |
| 10 | KTOS | radar-altı | 2016-11-09 | 2018-02-05 | 453 | 6.23 | 10.51 | SELL sinyali | +68.70 | +72.76 |
| 11 | WMT | düşük vol | 2016-11-14 | 2017-01-11 | 58 | 19.93 | 19.51 | SELL sinyali | -2.08 | -13.30 |
| 12 | MRK | düşük vol | 2017-01-11 | 2018-01-31 | 385 | 43.92 | 43.52 | SELL sinyali | -0.91 | -5.62 |
| 13 | CELH | radar-altı | 2017-04-26 | 2018-05-30 | 399 | 1.33 | 1.52 | SELL sinyali | +14.32 | +37.62 |
| 14 | NEE | düşük vol | 2018-02-02 | 2020-04-30 | 818 | 31.50 | 49.38 | SELL sinyali | +56.74 | +339.63 |
| 15 | ANF | radar-altı | 2018-02-16 | 2018-10-11 | 237 | 19.91 | 16.76 | SELL sinyali | -15.83 | -9.46 |
| 16 | COST | düşük vol | 2018-02-16 | 2019-01-28 | 346 | 171.61 | 190.29 | SELL sinyali | +10.89 | +93.40 |
| 17 | TDW | radar-altı | 2018-06-07 | 2018-11-13 | 159 | 31.40 | 24.11 | stop-loss | -23.22 | -65.63 |
| 18 | ASML | yüksek vol | 2018-06-19 | 2018-10-09 | 112 | 191.57 | 169.99 | SELL sinyali | -11.27 | -107.92 |
| 19 | REGN | yüksek vol | 2018-10-18 | 2019-05-10 | 204 | 391.98 | 310.30 | stop-loss | -20.84 | -163.37 |
| 20 | KTOS | radar-altı | 2018-11-05 | 2019-11-22 | 382 | 13.04 | 18.67 | SELL sinyali | +43.17 | +50.67 |
| 21 | AMD | yüksek vol | 2018-11-21 | 2021-04-21 | 882 | 18.73 | 81.61 | SELL sinyali | +335.72 | +3395.52 |
| 22 | MCD | düşük vol | 2019-01-28 | 2020-03-18 | 415 | 154.12 | 118.78 | stop-loss | -22.93 | -247.43 |
| 23 | ANF | radar-altı | 2019-04-17 | 2019-05-29 | 42 | 26.63 | 17.45 | stop-loss | -34.46 | -275.30 |
| 24 | MRVL | yüksek vol | 2019-05-13 | 2020-03-13 | 305 | 21.38 | 20.21 | SELL sinyali | -5.46 | -59.49 |
| 25 | CELH | radar-altı | 2019-06-17 | 2019-10-03 | 108 | 1.35 | 1.06 | stop-loss | -21.53 | -173.13 |
| 26 | HIMS | radar-altı | 2019-10-10 | 2020-01-31 | 113 | 9.82 | 10.05 | SELL sinyali | +2.29 | +18.00 |
| 27 | POWL | radar-altı | 2019-11-25 | 2020-03-03 | 99 | 11.99 | 9.34 | stop-loss | -22.05 | -147.99 |
| 28 | CELH | radar-altı | 2020-01-31 | 2020-03-16 | 45 | 1.80 | 1.07 | stop-loss | -40.37 | -326.27 |
| 29 | MRNA | yüksek vol | 2020-03-18 | 2022-01-06 | 659 | 31.58 | 216.06 | SELL sinyali | +584.17 | +5903.36 |
| 30 | WMT | düşük vol | 2020-03-18 | 2020-03-31 | 13 | 37.40 | 34.82 | SELL sinyali | -6.90 | -79.99 |
| 31 | WMT | düşük vol | 2020-04-06 | 2021-03-30 | 358 | 38.64 | 42.28 | SELL sinyali | +9.44 | +120.36 |
| 32 | ABBV | düşük vol | 2020-04-30 | 2022-09-15 | 868 | 64.86 | 124.35 | SELL sinyali | +91.72 | +1249.33 |
| 33 | CELH | radar-altı | 2020-05-08 | 2022-03-07 | 668 | 1.70 | 16.29 | SELL sinyali | +860.12 | +671.29 |
| 34 | SYM | radar-altı | 2021-03-30 | 2021-04-08 | 9 | 10.09 | 10.27 | SELL sinyali | +1.78 | +24.84 |
| 35 | JNJ | düşük vol | 2021-04-08 | 2021-11-17 | 223 | 140.71 | 142.70 | SELL sinyali | +1.41 | +19.90 |
| 36 | POWL | radar-altı | 2021-04-13 | 2021-08-05 | 114 | 10.44 | 8.09 | stop-loss | -22.45 | -2.34 |
| 37 | NVDA | yüksek vol | 2021-04-22 | 2022-04-20 | 363 | 14.80 | 21.42 | SELL sinyali | +44.76 | +1092.68 |
| 38 | IONQ | radar-altı | 2021-08-05 | 2021-10-04 | 60 | 9.98 | 7.51 | stop-loss | -24.75 | -489.06 |
| 39 | ANF | radar-altı | 2021-10-05 | 2022-03-01 | 147 | 39.18 | 35.85 | SELL sinyali | -8.50 | -123.21 |
| 40 | MDLZ | düşük vol | 2021-11-17 | 2022-07-15 | 240 | 54.78 | 54.41 | SELL sinyali | -0.67 | -9.55 |
| 41 | TSM | yüksek vol | 2022-01-07 | 2022-04-07 | 90 | 114.78 | 93.88 | SELL sinyali | -18.21 | -543.59 |
| 42 | RGTI | radar-altı | 2022-03-01 | 2022-03-04 | 3 | 10.24 | 7.45 | stop-loss | -27.25 | -571.95 |
| 43 | FLNC | radar-altı | 2022-03-07 | 2022-04-08 | 32 | 9.85 | 11.54 | SELL sinyali | +17.16 | +331.24 |
| 44 | IONQ | radar-altı | 2022-03-18 | 2022-03-29 | 11 | 14.36 | 12.39 | SELL sinyali | -13.72 | -299.44 |
| 45 | QBTS | radar-altı | 2022-03-30 | 2022-08-23 | 146 | 9.88 | 8.12 | SELL sinyali | -17.81 | -387.20 |
| 46 | SYM | radar-altı | 2022-04-12 | 2022-11-08 | 210 | 9.90 | 10.79 | SELL sinyali | +8.99 | +178.89 |
| 47 | SMCI | yüksek vol | 2022-04-19 | 2022-12-30 | 255 | 4.47 | 8.21 | dönem sonu (açık) | +83.87 | +2340.62 |
| 48 | VRTX | yüksek vol | 2022-05-02 | 2022-12-30 | 242 | 261.96 | 288.78 | dönem sonu (açık) | +10.24 | +268.20 |
| 49 | SO | düşük vol | 2022-07-15 | 2022-12-30 | 168 | 62.60 | 63.00 | dönem sonu (açık) | +0.65 | +21.62 |
| 50 | CELH | radar-altı | 2022-08-24 | 2022-09-22 | 29 | 37.85 | 29.97 | stop-loss | -20.82 | -370.36 |
| 51 | MRK | düşük vol | 2022-09-22 | 2022-12-30 | 99 | 78.19 | 99.79 | dönem sonu (açık) | +27.63 | +864.04 |
| 52 | OKLO | radar-altı | 2022-09-28 | 2022-09-29 | 1 | 9.75 | 9.70 | SELL sinyali | -0.51 | -4.60 |
| 53 | OKLO | radar-altı | 2022-10-03 | 2022-12-30 | 88 | 9.74 | 9.92 | dönem sonu (açık) | +1.85 | +16.56 |
| 54 | FLNC | radar-altı | 2022-11-10 | 2022-12-30 | 50 | 15.55 | 17.15 | dönem sonu (açık) | +10.29 | +222.40 |

## Özet istatistikler

- Kapanmış işlem başına ortalama getiri: %+47.81 (medyan %-2.08)
- Ortalama tutma süresi: 278 gün (medyan 210 gün)
- Stop-loss'ların getiri aralığı: %-40.37 … %-20.01 — %20 eşik çoğu kez gap ile aşılıyor
- En büyük 4 kazanan (MRNA (+584%), AMD (+336%), NVDA (+504%), SMCI (+84%)) toplam PnL'in %91'ini oluşturuyor — sonuç birkaç dev kazanana dayalı, bootstrap güven aralığının genişliğinin nedeni bu.

