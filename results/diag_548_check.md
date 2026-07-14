# Teşhis — 548 işlem kompozisyon kontrolü (düzeltme sonrası doğrulama)

> Salt teşhis; kod **değiştirilmedi**. Koşu 2016-2019 (tune) penceresinde —
> dönem ayrımı disiplinine uygun. Aynı `run_rotation_backtest` koşusu, ping-pong
> düzeltmesinden (bkz. `results/diag_1923_trades.md`) sonraki kod üzerinde.
> Koşu özeti: 548 işlem, getiri %57.71, maliyet $1.093,42.

## (1) exit_reason dağılımı — ranking_collapse hâlâ baskın, ama farklı bir kategori

| tip | adet | pay |
|---|---|---|
| ranking_collapse | 336 | **%61.3** |
| rotation | 158 | %28.8 |
| technical_emergency | 48 | %8.8 |
| backtest_end | 6 | %1.1 |

1923-işlem koşusunda ranking_collapse payı **%92.4**'tü; şimdi **%61.3**'e düştü —
mutlak sayı da 1776'dan 336'ya indi. Yine de en büyük tekil kategori. Bunun
kendisi anomali değil: ranking_collapse zaten üç meşru tetikten biri (aylık
rotasyon dışında tek satış kaynağı budur), dolayısıyla payının rotation'dan
yüksek kalması beklenir. Önemli olan mutlak sayı ve churn deseni — o da (2)'de
netleşiyor.

## (2) Cooldown/persist gerçekten çalışıyor mu — KISMEN: bir kod yolu atlıyor

384 alert-tetikli çıkışın **47'si** ≤7 işlem günü içinde aynı sembolü yeniden
açtı; bunların **14'ü** doğrudan `cooldown_days=5` sınırını ihlal etti (gap
1-4 işlem günü).

### İhlal örnekleri (gap < 5 işlem günü)
| sembol | çıkış (neden) | yeniden-giriş | gap |
|---|---|---|---|
| ASML | 2019-10-30 [ranking_collapse] | 2019-11-04 | 3 |
| VZ | 2019-03-27 [ranking_collapse] | 2019-04-02 | 4 |
| AMD | 2017-01-27 [ranking_collapse] | 2017-02-02 | 4 |
| MU | 2017-07-28 [ranking_collapse] | 2017-08-02 | 3 |
| ANF | 2019-02-28 [ranking_collapse] | 2019-03-04 | 2 |
| ANET | 2018-08-31 [ranking_collapse] | 2018-09-05 | 2 |
| MRK | 2019-01-29 [ranking_collapse] | 2019-02-04 | 4 |
| PG | 2017-05-31 [ranking_collapse] | 2017-06-02 | 2 |
| PG | 2017-06-30 [ranking_collapse] | 2017-07-05 | 2 |
| KTOS | 2017-08-01 [technical_emergency] | 2017-08-02 | 1 |
| KTOS | 2018-10-29 [technical_emergency] | 2018-11-02 | 4 |
| KTOS | 2019-03-28 [technical_emergency] | 2019-04-02 | 3 |
| JNJ | 2017-11-30 [ranking_collapse] | 2017-12-04 | 2 |
| CL | 2019-07-01 [ranking_collapse] | 2019-07-02 | 1 |

**Kök neden:** Bu 14 vakayı tek tek izledim — **hepsi rotasyon-icra gününde**
yeniden açılmış. `AlertCooldown`/`excluded` yalnız `backtest/rotation_backtest.py`
içindeki `alert_orders` → `slot_candidates` çağrısında uygulanıyor. Aylık
`rebalance_orders` (rotasyon günü seçimi) **cooldown'u hiç kontrol etmiyor** —
`engine.build_plan` / `rank_fn_as_of` cooldown'dan habersiz. Yani bir sembol
persist+cooldown ile alert'le kapatıldıktan sonra, bir sonraki aylık rotasyon
günü sırası yeniden yüksekse **anında geri seçilebiliyor** (örn. KTOS
technical_emergency ile 2017-08-01'de kapandı, 2017-08-02 rotasyon günü aynı
gün geri açıldı, gap=1).

Bu, önceki oturumda tasarım notu olarak "cooldown yalnız slot-doldurmayı
kapsar, aylık rotasyonu değil" diye işaretlenmişti, ama **ihlal sayısı
(14/384 = %3.6) küçük ve dağınık** — tek bir sembolde yoğunlaşan bir kalıntı
churn değil (KTOS 3 kez, diğerleri 1'er kez). Yapısal aç-kapa döngüsü
(889→12 düşüşü) **kalıcı olarak çözülmüş durumda**; bu 14 vaka ayrı, daha dar
bir boşluk: rotasyon ile cooldown'un aynı tabanı paylaşmaması.

## (3) En çok işlem gören 5 sembol — kalıntı yok

| sembol | round-trip |
|---|---|
| AVGO | 22 |
| LRCX | 22 |
| ASML | 20 |
| MRK | 19 |
| AMD | 18 |

1923-işlem koşusundaki outlier'lar büyük ölçüde eridi:

| sembol | 1923-koşusu | 548-koşusu |
|---|---|---|
| KTOS | 344 | 17 |
| CELH | 239 | 14 |
| POWL | 177 | 11 |
| ANF | 122 | 12 |

Şimdiki en yüksek (AVGO 22) makul bir dağılım; tek sembolde yoğunlaşan bir
kalıntı yok.

## Sonuç
Düzeltme asıl hastalığı (günlük slot-fill aç-kapa döngüsü, 889→12) tamamen
kapattı. Kalan tek boşluk: **rotasyon günü seçimi cooldown'dan habersiz** —
küçük ölçekli (14/548 işlem, %2.6) ama gerçek bir kod-yolu atlaması. Kod
değiştirilmedi; karar insana ait.
