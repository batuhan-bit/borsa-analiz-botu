# Pozisyon Boyutlandırma Denetimi — 2016-2022 (b) koşusu

_Kaynak: `backtest/backtest.py` `run_backtest` BUY döngüsü + canlı motor (`bot/signals/engine.py`) + Slack (`bot/notify/slack.py`). Sayılar, kaynağa DOKUNULMADAN Position kurulum anında çağıran çerçevenin yerel değişkenleri okunarak yakalandı; yakalanan 54 BUY = koşunun 54 işlemi, toplam getiri %+521.93 (birebir tutarlı)._

## 1) Boyut neye göre hesaplanıyor?

**Hedef boyut TOPLAM ÖZSERMAYE'ye göre, ama fiili alım SERBEST NAKİT ile sınırlı.** İkisi de devrede — melez bir mantık:

```python
# backtest.py, BUY döngüsü (sadeleştirilmiş)
equity = cash + sum(pozisyonların güncel değeri)   # gün başında BİR kez
target_value = per_pos_frac[basket] * equity        # <- ÖZSERMAYE tabanlı hedef
budget       = min(target_value, cash)              # <- SERBEST NAKİT tavanı
shares       = floor(budget / price)                # <- aşağı yuvarla
cash        -= shares * price
```

`per_pos_frac[basket] = allocation_pct / 100 / positions_per_basket`, yani sepet başına: düşük vol 40/2=**%20**, yüksek vol 35/2=**%17.5**, radar-altı 25/2=**%12.5**. Altı hedefin toplamı = **%100** — portföy tam yatırımdayken nakit → 0.

Üç yapısal sonuç:

- **`min(target, cash)` tavanı:** Nakit azaldığında yeni pozisyon hedefini değil, elde kalan nakadi alır. Boş bir slot dolarken geri dönen nakit yalnızca o an satılan pozisyonun değeri kadardır; özsermaye büyümüşse hedef bu nakdi kolayca aşar.
- **Sepet sırası nakit açlığı yaratıyor:** Sepetler `strategy.yaml` sırasıyla işlenir (düşük vol → yüksek vol → radar-altı). Aynı gün önce düşük/yüksek vol alır, **radar-altı en sona kalan nakitle** dolar. Cılız pozisyonların çoğu bu yüzden radar-altı.
- **`equity` gün başında sabit, `cash` alım başına azalıyor:** Hedefler bayat (gün başı) özsermayeye göre; nakit tükendikçe son alımlar orantısız küçük çıkar.

## 2) İşlem bazında hedef vs gerçekleşen boyut (54 BUY)

**27/54 BUY nakit-kısıtlı** (budget < target), **11/54 alım hedefin yarısından azını aldı**. Yani sorun uç durum değil, sistematik.

| # | Tarih | Sembol | Sepet | Özsermaye $ | Hedef $ | Nakit(önce) $ | Bütçe $ | Fiyat $ | Adet | Gerçekleşen $ | Dolum % | Nakit-kısıtlı |
|--:|-------|--------|-------|------------:|--------:|--------------:|--------:|--------:|-----:|--------------:|--------:|:-:|
| 1 | 2016-01-04 | KMB | düşük vol | 3,000 | 600 | 3,000 | 600 | 87.68 | 6 | 526 | 88 |  |
| 2 | 2016-01-04 | XLU | düşük vol | 3,000 | 600 | 2,474 | 600 | 15.49 | 38 | 589 | 98 |  |
| 3 | 2016-01-06 | NVDA | yüksek vol | 3,014 | 527 | 1,885 | 527 | 0.77 | 686 | 527 | 100 |  |
| 4 | 2016-01-29 | TSM | yüksek vol | 3,001 | 525 | 1,358 | 525 | 17.13 | 30 | 514 | 98 |  |
| 5 | 2016-02-02 | ANF | radar-altı | 2,992 | 374 | 844 | 374 | 21.68 | 17 | 369 | 99 |  |
| 6 | 2016-02-17 | NVDA | yüksek vol | 2,968 | 519 | 897 | 519 | 0.67 | 770 | 519 | 100 |  |
| 7 | 2016-04-27 | CELH | radar-altı | 3,243 | 405 | 378 | 378 | 0.78 | 485 | 378 | 93 | ✔ |
| 8 | 2016-07-05 | POWL | radar-altı | 3,480 | 435 | 284 | 284 | 10.20 | 27 | 275 | 63 | ✔ |
| 9 | 2016-10-06 | PG | düşük vol | 3,810 | 762 | 861 | 762 | 68.45 | 11 | 753 | 99 |  |
| 10 | 2016-11-09 | KTOS | radar-altı | 3,835 | 479 | 108 | 108 | 6.23 | 17 | 106 | 22 | ✔ |
| 11 | 2016-11-14 | WMT | düşük vol | 4,050 | 810 | 644 | 644 | 19.93 | 32 | 638 | 79 | ✔ |
| 12 | 2017-01-11 | MRK | düşük vol | 4,463 | 893 | 631 | 631 | 43.92 | 14 | 615 | 69 | ✔ |
| 13 | 2017-04-26 | CELH | radar-altı | 4,543 | 568 | 263 | 263 | 1.33 | 198 | 263 | 46 | ✔ |
| 14 | 2018-02-02 | NEE | düşük vol | 7,459 | 1,492 | 610 | 610 | 31.50 | 19 | 599 | 40 | ✔ |
| 15 | 2018-02-16 | COST | düşük vol | 7,588 | 1,518 | 920 | 920 | 171.61 | 5 | 858 | 57 | ✔ |
| 16 | 2018-02-16 | ANF | radar-altı | 7,588 | 949 | 62 | 62 | 19.91 | 3 | 60 | 6 | ✔ |
| 17 | 2018-06-07 | TDW | radar-altı | 7,867 | 983 | 302 | 302 | 31.40 | 9 | 283 | 29 | ✔ |
| 18 | 2018-06-19 | ASML | yüksek vol | 7,811 | 1,367 | 962 | 962 | 191.57 | 5 | 958 | 70 | ✔ |
| 19 | 2018-10-18 | REGN | yüksek vol | 7,438 | 1,302 | 904 | 904 | 391.98 | 2 | 784 | 60 | ✔ |
| 20 | 2018-11-05 | KTOS | radar-altı | 6,830 | 854 | 120 | 120 | 13.04 | 9 | 117 | 14 | ✔ |
| 21 | 2018-11-21 | AMD | yüksek vol | 5,831 | 1,020 | 3,352 | 1,020 | 18.73 | 54 | 1,011 | 99 |  |
| 22 | 2019-01-28 | MCD | düşük vol | 6,017 | 1,203 | 3,292 | 1,203 | 154.12 | 7 | 1,079 | 90 |  |
| 23 | 2019-04-17 | ANF | radar-altı | 6,396 | 799 | 2,213 | 799 | 26.63 | 30 | 799 | 100 |  |
| 24 | 2019-05-13 | MRVL | yüksek vol | 6,318 | 1,106 | 2,035 | 1,106 | 21.38 | 51 | 1,090 | 99 |  |
| 25 | 2019-06-17 | CELH | radar-altı | 6,439 | 805 | 1,468 | 805 | 1.35 | 597 | 804 | 100 |  |
| 26 | 2019-10-10 | HIMS | radar-altı | 6,349 | 794 | 1,295 | 794 | 9.82 | 80 | 786 | 99 |  |
| 27 | 2019-11-25 | POWL | radar-altı | 7,020 | 878 | 677 | 677 | 11.99 | 56 | 671 | 76 | ✔ |
| 28 | 2020-01-31 | CELH | radar-altı | 7,580 | 947 | 810 | 810 | 1.80 | 449 | 808 | 85 | ✔ |
| 29 | 2020-03-18 | WMT | düşük vol | 5,836 | 1,167 | 2,869 | 1,167 | 37.40 | 31 | 1,159 | 99 |  |
| 30 | 2020-03-18 | MRNA | yüksek vol | 5,836 | 1,021 | 1,709 | 1,021 | 31.58 | 32 | 1,011 | 99 |  |
| 31 | 2020-04-06 | WMT | düşük vol | 6,405 | 1,281 | 1,778 | 1,281 | 38.64 | 33 | 1,275 | 100 |  |
| 32 | 2020-04-30 | ABBV | düşük vol | 6,971 | 1,394 | 1,441 | 1,394 | 64.86 | 21 | 1,362 | 98 |  |
| 33 | 2020-05-08 | CELH | radar-altı | 7,488 | 936 | 79 | 79 | 1.70 | 46 | 78 | 8 | ✔ |
| 34 | 2021-03-30 | SYM | radar-altı | 11,830 | 1,479 | 1,397 | 1,397 | 10.09 | 138 | 1,392 | 94 | ✔ |
| 35 | 2021-04-08 | JNJ | düşük vol | 12,869 | 2,574 | 1,421 | 1,421 | 140.71 | 10 | 1,407 | 55 | ✔ |
| 36 | 2021-04-13 | POWL | radar-altı | 13,241 | 1,655 | 14 | 14 | 10.44 | 1 | 10 | 1 | ✔ |
| 37 | 2021-04-22 | NVDA | yüksek vol | 14,019 | 2,453 | 4,411 | 2,453 | 14.80 | 165 | 2,441 | 100 |  |
| 38 | 2021-08-05 | IONQ | radar-altı | 23,386 | 2,923 | 1,978 | 1,978 | 9.98 | 198 | 1,976 | 68 | ✔ |
| 39 | 2021-10-05 | ANF | radar-altı | 20,257 | 2,532 | 1,489 | 1,489 | 39.18 | 37 | 1,450 | 57 | ✔ |
| 40 | 2021-11-17 | MDLZ | düşük vol | 18,979 | 3,796 | 1,466 | 1,466 | 54.78 | 26 | 1,424 | 38 | ✔ |
| 41 | 2022-01-07 | TSM | yüksek vol | 17,461 | 3,056 | 6,956 | 3,056 | 114.78 | 26 | 2,984 | 98 |  |
| 42 | 2022-03-01 | RGTI | radar-altı | 16,874 | 2,109 | 5,298 | 2,109 | 10.24 | 205 | 2,099 | 100 |  |
| 43 | 2022-03-07 | FLNC | radar-altı | 15,517 | 1,940 | 5,475 | 1,940 | 9.85 | 196 | 1,931 | 100 |  |
| 44 | 2022-03-18 | IONQ | radar-altı | 17,547 | 2,193 | 3,544 | 2,193 | 14.36 | 152 | 2,183 | 100 |  |
| 45 | 2022-03-30 | QBTS | radar-altı | 17,407 | 2,176 | 3,245 | 2,176 | 9.88 | 220 | 2,174 | 100 |  |
| 46 | 2022-04-12 | SYM | radar-altı | 15,972 | 1,996 | 5,774 | 1,996 | 9.90 | 201 | 1,990 | 100 |  |
| 47 | 2022-04-19 | SMCI | yüksek vol | 15,950 | 2,791 | 3,784 | 2,791 | 4.47 | 625 | 2,791 | 100 |  |
| 48 | 2022-05-02 | VRTX | yüksek vol | 15,505 | 2,713 | 4,527 | 2,713 | 261.96 | 10 | 2,620 | 97 |  |
| 49 | 2022-07-15 | SO | düşük vol | 17,774 | 3,555 | 3,323 | 3,323 | 62.60 | 53 | 3,318 | 93 | ✔ |
| 50 | 2022-08-24 | CELH | radar-altı | 17,955 | 2,244 | 1,791 | 1,791 | 37.85 | 47 | 1,779 | 79 | ✔ |
| 51 | 2022-09-22 | MRK | düşük vol | 15,959 | 3,192 | 4,032 | 3,192 | 78.19 | 40 | 3,128 | 98 |  |
| 52 | 2022-09-28 | OKLO | radar-altı | 15,911 | 1,989 | 905 | 905 | 9.75 | 92 | 897 | 45 | ✔ |
| 53 | 2022-10-03 | OKLO | radar-altı | 16,348 | 2,043 | 900 | 900 | 9.74 | 92 | 896 | 44 | ✔ |
| 54 | 2022-11-10 | FLNC | radar-altı | 17,918 | 2,240 | 2,173 | 2,173 | 15.55 | 139 | 2,161 | 97 | ✔ |

### $10'lık POWL (2021-04-13) — adım adım

1. Gün başı özsermaye = **$13,241**; radar-altı hedefi = %12.5 × 13,241 = **$1,655**.
2. Ama o an serbest nakit = **$14.29** (özsermayenin %99.9'u zaten 5 pozisyonda + o gün önce dolan diğer slotlarda bağlı).
3. `budget = min(1,655, 14.29)` = **$14.29**.
4. `shares = floor(14.29 / 10.44)` = **1 adet** → pozisyon **$10.44** (hedefin **%1**'i).
5. Sonuç: 1 hisselik pozisyon -22.45% stop ile kapandı, PnL yalnız -$2.34 — portföyde gürültüden başka bir şey değil, ama yine de bir stop-loss/komisyon yüzeyi işgal etti.

### $106'lık KTOS (2016-11-09) — adım adım

1. Gün başı özsermaye = **$3,835**; radar-altı hedefi = %12.5 × 3,835 = **$479**.
2. Serbest nakit = **$107.96** (koşunun başı; düşük/yüksek vol sepetleri ilk dolduğundan radar-altına az nakit kalmış).
3. `budget = min(479, 107.96)` = **$107.96**.
4. `shares = floor(107.96 / 6.23)` = **17 adet** → pozisyon **$105.91** (hedefin **%22**'i).
5. Sonuç: KTOS +68.70% kazandı ama küçük boyut yüzünden PnL yalnız +$72.76; hedef boyutta ~5x daha fazla katkı yapabilirdi.

### Kritik gözlem: cılız pozisyonlar en büyük kazananları da buduyor

Dolum <%50 olan 11 pozisyonun gerçek sonuçları — 6 kazanan / 5 kaybeden, yani cılız pozisyonlar 'kötü' değil, sadece **küçük**:

| Tarih | Sembol | Hedef $ | Gerçekleşen $ | Dolum % | Getiri % | PnL $ | Çıkış |
|-------|--------|--------:|--------------:|--------:|---------:|------:|-------|
| 2016-11-09 | KTOS | 479 | 106 | 22 | +68.70 | +72.76 | SELL |
| 2017-04-26 | CELH | 568 | 263 | 46 | +14.32 | +37.62 | SELL |
| 2018-02-02 | NEE | 1,492 | 599 | 40 | +56.74 | +339.63 | SELL |
| 2018-02-16 | ANF | 949 | 60 | 6 | -15.83 | -9.46 | SELL |
| 2018-06-07 | TDW | 983 | 283 | 29 | -23.22 | -65.63 | stop |
| 2018-11-05 | KTOS | 854 | 117 | 14 | +43.17 | +50.67 | SELL |
| 2020-05-08 | CELH | 936 | 78 | 8 | +860.12 | +671.29 | SELL |
| 2021-04-13 | POWL | 1,655 | 10 | 1 | -22.45 | -2.34 | stop |
| 2021-11-17 | MDLZ | 3,796 | 1,424 | 38 | -0.67 | -9.55 | SELL |
| 2022-09-28 | OKLO | 1,989 | 897 | 45 | -0.51 | -4.60 | SELL |
| 2022-10-03 | OKLO | 2,043 | 896 | 44 | +1.85 | +16.56 | dönem sonu |

En çarpıcısı **CELH 2020-05-08**: koşunun en büyük yüzde kazananı (+860%), ama nakit tükendiği için yalnız **$78** (hedef $936'in %8'i) alındı. PnL +$671 oldu; hedef boyutta olsaydı kabaca +$8,050 olurdu — nakit-açlığı sizing en iyi işlemi ~12x küçülttü. **Yani bu boyutlandırma hatası backtest getirisini şişirmiyor, tam tersine radar-altı momentum kazananlarını sistematik olarak eksik-boyutlandırarak gerçekte BASTIRIYOR.**

## 3) ÖNERİ (uygulanmadı): `min_position_pct` kapısı

**Öneri:** `strategy.yaml` `portfolio:` altına `min_position_pct` (ör. 0.5) ekle. BUY sizing'de `budget < target_value * min_position_pct` ise pozisyonu **açma, slotu boş bırak, nakdi tut**. Değer kodda sabitlenmez, config'ten okunur (mevcut kalıp).

**Gerekçe:** $10'lık POWL gibi pozisyonlar getiriye katkı vermez ama stop-loss/komisyon/izleme yüzeyi ekler ve raporu gürültüyle kirletir.

**Ama veriyi görmeden uygulamak yanlış olur — bu yüzden önce rapor:**

- Kapı **iptal değil erteleme** yapar: aday her gün yeniden değerlendirildiği için, sinyal sürerse ve başka çıkışlardan nakit dönerse pozisyon sonraki günlerde tam boyutla açılabilir. Etki, sinyalin kalıcılığına ve nakit dönüşüne bağlıdır.
- Naif eşik **en büyük kazananı düşürebilir**: CELH 2020-05-08 (dolum %8) bu kapıyla o gün atlanırdı; sinyal sonraki günlerde kaybolduysa +860%'lik işlem tümüyle kaçardı. 11 cılızın 6'sı kazanandı.
- **Kök neden `min_position_pct` değil, nakit-açlığı sizing'in kendisi.** Daha sağlam çözüm hedefi serbest nakde göre yeniden ölçeklemek (ör. slotu tam açamıyorsan ertele + o gün başka sepetten nakit ödünç verme kuralı) veya sepet sırasını gün-içi nakit paylaşımına göre adil kılmaktır. `min_position_pct` yalnız semptomu (cılız pozisyon) keser, dağıtım çarpıklığını değil.
- **Bu bir Faz 2 gerçekçilik kararı; Görev 2.1 (ertesi-gün-açılış dolgusu + komisyon) ile birlikte değerlendirilmeli** — komisyon eklenince $10'lık pozisyonlar zaten net-negatif olur ve kapının gerekçesi güçlenir.

## 4) Canlı motor / Slack pozisyon boyutu önerisi var mı?

**Hayır — canlı yolda pozisyon boyutlandırma HİÇ YOK.** `SignalEngine` yalnız BUY/SELL/HOLD/STOP_LOSS kararı, skor, fiyat ve (BUY için) stop/destek/hedef/R-R seviyeleri üretir; adet, dolar tutarı veya '%X al' önerisi hesaplamaz. `slack.py` `_format_signal_line` da fiyat + seviyeleri gösterir, **boyut önermez**. `portfolio.execution: manual` — kullanıcı ne kadar alacağına kendi karar verir.

**Asimetri:** Backtest pozisyonları boyutlandırıyor (özsermaye × sepet%/2, nakit tavanlı) ve raporladığı getiri **bu** boyutlandırmaya bağlı; ama canlıda kullanıcıya hiçbir boyut rehberi verilmiyor. Dolayısıyla backtest'in ürettiği getiri, canlıda kullanıcının elle seçeceği boyutlarla **tekrarlanmayabilir** — iki yol aynı sizing mantığını paylaşmıyor. Bir sonraki adım, sepet ağırlığı × bütçe'den türeyen bir 'önerilen tutar/adet'i Slack BUY satırına eklemek olabilir (ayrı görev; burada yalnız denetim).
