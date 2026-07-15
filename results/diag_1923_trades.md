# Teşhis — 1923 işlem anomalisi (2016-2019 tune penceresi)

> Salt teşhis; motor kodu **değiştirilmedi**. Koşu 2016-2019 (tune) verisinde —
> dönem ayrımı disiplinine uygun. Ham işlem dökümü: `results/trades_2016_2019.csv`.
> Koşu özeti: 1923 işlem, getiri **%-26.6**, CAGR %-7.46, MaxDD %-38.72,
> kazanma %42.0, toplam maliyet **$3.100** (başlangıç sermayesi $3.000).

## Kısa teşhis
1923 işlemin **1776'sı (%92) `ranking_collapse`** çıkışı; alış tarafında
**1796'sı (%93) slot-doldurma**. Baskın döngü: **slot-doldurma → ertesi gün
sıralama-çöküşü satışı → slot yeniden doldurma → …** Aynı sembol art arda
günlerde kapanıp yeniden açılıyor (≤1 işlem günü boşlukla **889** yeniden-açılma).
Gerçek aylık rotasyon yalnız **121** işlem; teknik acil **20**; sonda kapanış 6.

## (1) Kaynak tipine göre sayım
**Satış (exit_reason):**
| tip | adet |
|---|---|
| ranking_collapse | 1776 |
| rotation (aylık) | 121 |
| technical_emergency | 20 |
| backtest_end | 6 |

**Alış (entry kaynağı — entry_date'in bir önceki günü rotasyon günü mü):**
| tip | adet |
|---|---|
| slot_fill_entry | 1796 |
| rotation_entry | 127 |

**Çapraz (baskın kalıp):** slot_fill → ranking_collapse **1650**,
rotation_entry → ranking_collapse 126, slot_fill → rotation 121.

## (2) Aylık rotasyon gerçekten yalnız ay başında mı?
Evet. `exit_reason=="rotation"` işlemlerin **121/121'i** rotasyon-icra gününde
(ayın ilk işlem gününün ertesi açılışı). Rotasyon-icra günü dışında **0**.
Ayın-günü histogramı: gün2=65, gün3=16, gün4=26, gün5=14 (icra=sinyal ertesi
gün olduğu için 1'inci değil ~2'nci işlem günü). 48 rotasyon günü, 42 ayrı
günde rotasyon çıkışı. → Rotasyon **aylık** tetikleniyor, günlük değil.

## (3) rebalance_band_pct — değer ve kontrol sıklığı (kod izi)
- Değer: `strategy.yaml → rotation.rebalance_band_pct: 20` (%20).
- `engine.py:80` → `self._band = 20/100 = 0.20`.
- Bant yalnız `RotationEngine._diff` (`engine.py:149`) içinde `plan.rebalance`
  üretiminde kullanılır.
- `plan.rebalance` yalnız `rebalance_orders` (`rotation_backtest.py:366-370`)
  tarafından tüketilir.
- `rebalance_orders` **yalnız** `if day in rotation_days` dalında çağrılır
  (`rotation_backtest.py:420-421`).
- Diğer 958 günde `alert_orders` çalışır ve bant kullanılmaz.
→ **Bant yalnız 48 aylık rotasyon gününde kontrol edilir; günlük değil.**
Yani churn'ün kaynağı bant DEĞİL; günlük `alert_orders`.

## (4) Sıralama çöküşü 2016-2017 + ardışık gün ping-pong
- ranking_collapse toplam **1776**; **2016-2017 = 819** (2016: 312, 2017: 507;
  2018: 399, 2019: 558).
- Aynı sembol kapanıp **≤1 işlem günü** içinde yeniden açılma: **889 kez**.
- alert (rc+te) çıkışları **796 ayrı günde** — 958 rotasyon-dışı günün %83'ü.
- Örnek (POWL, günlük ping-pong):
  `2016-06-03→06 [rc]` · `06-06→07 [rc]` · `06-07→08 [rc]` · `06-08→09 [rc]` …
- En çok işlem gören: KTOS 344, CELH 239, POWL 177, ANF 122 round-trip.

## Kök neden (kod düzeyinde)
`alert_orders` **her rotasyon-dışı günde** çalışır (`rotation_backtest.py:423`).
Sıralama-çöküşü testi **global** sıralamada `rank > 2·top_n = 12` bakar
(`alerts.py:85-86`), ama seçim modu `per_basket`: portföy sepet-içi sıraya göre
tutuluyor (her sepetten 2), global sıraya göre değil. 60 sembollük evrende bir
sepetin 2. tercihi global sırada rahatça 12'nin altına düşebilir → **meşru
biçimde tutulan pozisyon her gün "çöküş" sayılıp satılıyor**. Boşalan slot
`slot_candidates` ile portföy-dışı en yüksek adayla doldruluyor; o aday da
global 12 dışında olabildiğinden ertesi gün yine satılıyor. Sonuç: her işlem
gününde zorunlu al-sat döngüsü ve $3.100 maliyet.

**Uyumsuzluk:** çöküş eşiği (`2·top_n`, global) ile tutma kuralı (`per_basket`,
sepet-içi) aynı sıralama tabanına oturmuyor. (Düzeltme kararı insana ait —
bu rapor yalnız teşhis.)

---

## Düzeltme sonrası (aynı 2016-2019 tune penceresi)
Üç parçalı yapısal düzeltme uygulandı (taban hizalama + kalıcılık şartı +
yeniden-giriş bekleme; `bot/rotation/alerts.py`, `slots.py`, config `sell_alerts`).
Aynı koşu tekrarlandı (tune penceresi — dönem ayrımına uygun):

| Ölçüt | Önce | Sonra |
|---|---|---|
| İşlem sayısı | 1923 | **548** (−%71) |
| ranking_collapse (satış) | 1776 | **336** |
| Toplam maliyet | $3.100 | **$1.093** |
| Ardışık-gün (≤1) yeniden açılma | 889 | **12** |
| slot_fill → ranking_collapse | 1650 | 224 |

Kalan 12 ardışık-gün yeniden açılmanın tamamı **aylık rotasyon rebalansı**
(hedef ağırlığa çekmek için ay başında kapat-yeniden aç, gap=0) veya
**technical_emergency** (ani olay; kalıcılıktan muaf) kaynaklı — hiçbiri
slot-fill günlük aç-kapa döngüsü değil. Ping-pong yapısal olarak kapandı.

> Not (dönem ayrımı): getiri/CAGR gibi pencere-sonucu sayıları burada YALNIZ
> churn'ün mekanik olarak düzeldiğini doğrulamak için var; parametre seçimi bu
> sayılara bakarak yapılmadı. Varsayılanlar (persist=3, cooldown=5, taban=sepet-içi)
> teşhisten türeyen tasarım kararlarıdır, tune-getirisine göre optimize edilmedi.
> Konfig yarışması hâlâ fazlı disipline tabidir (B.3).
