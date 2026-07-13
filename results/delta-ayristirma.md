# Δ Ayrıştırma — gerçekçilik katmanının bileşen bazında etkisi

_Üretim: `python scratchpad/decompose.py` · strategy.yaml **DONDURULMUŞ** (eşikler,
skor ağırlıkları, sizing parametreleri değişmedi). Her varyant `run_backtest`
override'larıyla koşuldu (`sizing_mode` / `fill_mode` / `apply_costs`) — yaml'a
dokunulmadı. Koruyucu özellikler (trend filtresi + yönlü hacim + R/R kapısı) her
koşuda AÇIK; yani 2016-2022 için bu, rapordaki **varyant (c)** ile aynı yapı._

**Legacy taban** = sizing `legacy` · dolgu `close` (sinyal günü kapanışı) ·
maliyet `yok`. Üç bileşen tek tek, tabana göre açılıyor. "Δ" = tabana göre fark.
İşlem sayısı = round-trip kapanmış işlem (dönem-sonu zorunlu tasfiyeler hariç).

## Ana dönem — son 3 yıl (2023-07-10 → 2026-07-10)

| Konfigürasyon | Toplam getiri % | İşlem | Δ Toplam (puan) | Δ İşlem |
|---|---|---|---|---|
| legacy taban (close · maliyetsiz · legacy) | +187.71 | 28 | — (taban) | — |
| (1) yalnız fill: next_open | +171.32 | 28 | **−16.39** | +0 |
| (2) yalnız maliyetler (10 bps) | +303.25 | 24 | **+115.54** | −4 |
| (3) yalnız sizing v2 | +83.44 | 26 | **−104.27** | −2 |
| _referans:_ hepsi açık (v2 + next_open + maliyet) | +73.01 | 26 | −114.70 | −2 |

- Bileşen Δ'larının toplamı: −16.39 + 115.54 − 104.27 = **−5.12**
- Gerçek birleşik Δ: **−114.70** → **etkileşim terimi ≈ −109.6 puan**
- "hepsi açık" satırı rapordaki _Strateji (mevcut config)_ birincil koşusunu
  (+73.01 %, 26 işlem) **bire bir** yeniden üretir → ayrıştırma doğrulandı.

## 2016-2022 — fiilen out-of-sample (varyant c dönemi)

| Konfigürasyon | Toplam getiri % | İşlem | Δ Toplam (puan) | Δ İşlem |
|---|---|---|---|---|
| legacy taban (close · maliyetsiz · legacy) | +122.32 | 41 | — (taban) | — |
| (1) yalnız fill: next_open | +118.70 | 41 | **−3.62** | +0 |
| (2) yalnız maliyetler (10 bps) | +118.61 | 41 | **−3.71** | +0 |
| (3) yalnız sizing v2 | +71.08 | 37 | **−51.24** | −4 |
| _referans:_ hepsi açık (v2 + next_open + maliyet) | +139.72 | 30 | **+17.40** | −11 |

- Bileşen Δ'larının toplamı: −3.62 − 3.71 − 51.24 = **−58.57**
- Gerçek birleşik Δ: **+17.40** → **etkileşim terimi ≈ +75.97 puan**
- "hepsi açık" satırı rapordaki **varyant (c)** (+139.72 %, 30 işlem, Δ +17.40)
  koşusunu **bire bir** yeniden üretir.

## Yorum — "+17.4 hangi bileşenden geldi?"

**Hiçbirinden.** Sorunun cevabı, beklenenin tersi:

1. **Üç bileşenin de tek başına etkisi NEGATİF** (2016-2022'de −3.6, −3.7, −51.2).
   Yani gerçekçilik katmanının hiçbir parçası tek başına getiriyi artırmıyor —
   olması gereken de bu (daha gerçekçi dolgu + maliyet + temkinli boyutlandırma
   getiriyi düşürür).

2. **+17.4, üçü birlikte açıkken doğan bir ETKİLEŞİM etkisi.** Bileşenlerin
   ayrı ayrı toplamı −58.6 iken birleşik sonuç +17.4 — aradaki ≈ +76 puanlık
   fark, katkıların toplanabilir olmadığını gösterir. Sizing v2 tek başına −51
   getirirken, next_open + maliyetle birlikte koşulduğunda portföyün gün-içi
   nakit/dolum yolu değişiyor, farklı bir hisse kümesi tutuluyor ve birleşik yol
   tesadüfen tabanı geçiyor.

3. **Dolayısıyla +17.4 gerçek bir "iyileşme" değil, yol-bağımlılığı (path
   dependence) artefaktıdır.** En büyük tekil yapısal kaldıraç **sizing v2**'dir
   (her iki dönemde de en yüksek mutlak Δ: ana dönemde −104, 2016-2022'de −51);
   dolgu ve maliyet 2016-2022'de neredeyse etkisizdir (~−3.6'şar puan).

4. **Ana dönemdeki "yalnız maliyetler → +115.54" satırı bu kırılganlığın kanıtı.**
   10 bps maliyet getiriyi 115 puan ARTIRAMAZ; bu sonuç, maliyetin hisse
   adedini birazcık kısıp legacy boyutlandırmanın nakit yörüngesini değiştirmesi
   ve bambaşka bir yüksek-uçan kümesinin tutulmasıyla oluşan kaotik yeniden
   dizilimdir. Legacy sizing küçük girdilere aşırı duyarlıdır.

### Sonuç

Küçük işlem örnekleminde (30-41 kapanmış işlem) tekil bileşen Δ'ları büyük
etkileşim terimleriyle gölgeleniyor; **+17.4 tek bir bileşene atfedilemez.**
Yapısal olarak asıl belirleyici **sizing v2**'dir ve tek başına her iki dönemde
de getiriyi düşürür. Gerçekçilik katmanının değeri "getiriyi artırmak" değil,
birincil rakamları iyimserlikten arındırmaktır (bkz. `rapor.md` sınırlamalar).
