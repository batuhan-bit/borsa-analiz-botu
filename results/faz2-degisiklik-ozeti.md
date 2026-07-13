# Faz 2 — Sizing v2 + Gerçekçilik Katmanı + Rapor v2

_Üretim: 2026-07-13 · branch `claude/sad-heyrovsky-847073` (Faz 1 dalı `b53a17` üzerine kuruludur) · 90 test geçiyor · yalnız yerel commit (push edilmedi)_

Bu belge, verilen 4 maddelik görevde tam olarak ne yapıldığını özetler. **Sinyal
eşiklerine ve skor ağırlıklarına dokunulmadı** — yalnız boyutlandırma, dolgu ve
işlem-maliyeti katmanı değişti.

---

## 1) `config/strategy.yaml` — yeni ayarlar

```yaml
portfolio:
  sizing:
    mode: v2                 # legacy | v2
    deployment_pct: 95       # portföyün en çok bu kadarı pozisyonlarda tutulur
    min_fill_pct: 0.60       # gün-içi dolum bu oranın altındaysa aç-ma, ertele
    fractional_shares: false # kesirli hisse alınabilsin mi (false = tam adet)

backtest:
  fill: next_open            # close | next_open (ertesi-gün açılışından dolum)
  commission_bps: 5          # işlem başına komisyon (bps)
  slippage_bps: 5            # işlem başına kayma (bps)
```

- **legacy** modu mevcut davranışı **birebir** korur.
- **v2** modu Görev 2.2'nin gövdesidir (aşağıda).

---

## 2) Görev 2.1 + 2.2 — `backtest/backtest.py`

### Görev 2.2 — Sizing v2 (pozisyon boyutlandırma)
Denetim raporunun (`pozisyon-boyutlandirma-denetimi.md`) tespit ettiği "nakit-açlığı
+ sepet-sırası" çarpıklığını çözer:

- Aynı gün **tüm sepetlerdeki** BUY adayları, mevcut nakdi **hedef ağırlıkları
  oranında** paylaşır — sepet sırası (düşük→yüksek→radar) artık avantaj vermez.
- Ortak dolum oranı `f = kullanılabilir_nakit / toplam_talep`. `f < min_fill_pct`
  ise o gün **hiçbir** pozisyon açılmaz → **ertelenir** (aday ertesi gün yeniden
  değerlendirilir; nakit döndükçe tam boyutla açılabilir). Bu, denetimdeki $10'lık
  POWL gibi cılız pozisyonları kökten engeller.
- Toplam maruziyet `deployment_pct` ile sınırlıdır (özsermayenin en az
  `%(100−deployment_pct)`'i nakitte tampon kalır).

### Görev 2.1 — Gerçekçilik katmanı
- **Dolgu fiyatı:** Sinyal günü kapanışında karar, **ertesi gün açılışından**
  dolum (`fill: next_open`). Canlı gerçeği yansıtır (sinyal kapanış sonrası üretilir,
  işlem ancak ertesi gün açılır).
- **İşlem maliyeti:** Komisyon + kayma her işlemde etkin fiyata gömülür (alışta ↑,
  satışta ↓). `0 bps` = eski maliyetsiz davranış.

### legacy korunumu (kanıtlı)
Ortak `open_position` yardımcısı `cost_frac=0 + fill=close` iken eski
`floor(min(hedef, nakit) / kapanış)` mantığına birebir indirgenir. Raporun **legacy
kolonu Faz 1 rakamlarını birebir üretti** (aşağıya bakınız) → doğrulandı.

### Çalıştırma
```bash
python -m backtest.backtest                       # config default (v2 + maliyet + next_open)
python -m backtest.backtest --sizing legacy --fill close --no-costs   # eski davranış
```
`run_backtest(...)` fonksiyonu `sizing_mode`, `fill_mode`, `apply_costs` override
alır; config'i ezer (rapor aynı stratejiyi iki türlü koşabilsin diye).

---

## 3) Rapor v2 — `backtest/report.py` → `results/rapor.md`

Aynı format korundu (2023-2026 + 2016-2022, (a)/(b)/(c) varyantları, üç benchmark,
bootstrap %90 GA, rejim pencereleri) ama:

- Her konfigürasyon **iki kez** koşulur: **birincil** (v2 + maliyet + ertesi-açılış)
  ve **legacy** (sepet-sıralı + kapanış + maliyetsiz).
- Tabloya iki yeni kolon: **`Legacy Top.% (maliyetsiz)`** ve **`Δ Top.%`** — fark
  görünsün diye.

### Öne çıkan sonuçlar

**Ana dönem (2023-07-10 → 2026-07-10, in-sample)**

| Konfigürasyon | Toplam % (v2+maliyet) | Legacy % (maliyetsiz) | Δ |
|---|---|---|---|
| Strateji (mevcut config) | **+73.01** | +187.71 | **−114.70** |

**2016-2022 (fiilen out-of-sample)**

| Varyant | Toplam % (v2+maliyet) | Legacy % (maliyetsiz) | Δ |
|---|---|---|---|
| (a) Trend kapalı | +231.98 | +256.01 | −24.03 |
| (b) Trend açık | +441.82 | +521.93 | −80.11 |
| (c) Trend + yönlü hacim + R/R | **+139.72** | +122.32 | **+17.40** |

**Yorum:**
- Legacy kolonu Faz 1 rakamlarını (+187.71 / +256.01 / +521.93 / +122.32) **birebir**
  üretti → legacy modun sadakati kanıtlı; Δ'lar tümüyle Görev 2.1+2.2 etkisidir.
- Gerçekçilik güçlü boğada (ana dönem, OOS-b) getiriyi **düşürür** — iyimserlik
  payı buydu.
- Ama **OOS (c) gerçekçilikle İYİLEŞTİ (+17.4 puan)**: v2, denetim raporunun
  öngördüğü gibi momentum kazananlarını cılız-boyutlandırmayı bıraktığı için.
- Bootstrap GA'ları hâlâ çakışıyor (varyantlar istatistiksel olarak ayırt edilemiyor)
  ve rejim tabloları benzer resmi koruyor.

### Çalıştırma
```bash
python -m backtest.report        # results/rapor.md üretir
```

---

## 4) Slack BUY — "önerilen tutar/adet" (ayrı küçük iş)

Canlı yolda (`bot/main.py`) her BUY sinyaline, **Sheets özsermayesinden** hesaplanan
öneri eklenir; Slack ve konsolda `💰` satırıyla gösterilir:

```
🟢 KO  $42.50  (skor 0.55, Düşük Vol)
      RSI toparlıyor
      💰 Öneri: ~$1,100 (%20 ağırlık) → 25 adet ≈ $1,062
```

- **v2 kuralı:** önerilen tutar = hedef ağırlık × özsermaye
  (hedef ağırlık = sepet dağılımı ÷ sepetteki pozisyon sayısı).
- **`fractional_shares` config'ine saygılı:** kapalıysa tam adet (floor), açıksa
  kesirli. Tam adet modunda 1 hisse bile hedefi aşıyorsa "1 hisse hedefi aşıyor"
  uyarısı.
- Yeni saf modül `bot/signals/sizing.py` (`suggested_position`, `portfolio_equity`,
  `target_weight`) — ağdan bağımsız, kolay test edilir. `Signal.sizing` alanı eklendi.

### Özsermaye kaynağı (senin tercihin: kesin nakit)
Google Sheets **Pozisyonlar** sekmesine bir satır ekleyerek serbest nakit girilir:

| Sembol | Sepet | Giriş Tarihi | **Giriş Fiyatı** | Adet | Durum |
|--------|-------|--------------|------------------|------|-------|
| NAKİT  |       |              | **3000**         |      |       |

- `Sembol = NAKİT` (veya `CASH`), tutar **"Giriş Fiyatı"** sütununda.
- Bu satır **pozisyon sayılmaz** (stop-loss'a girmez).
- Özsermaye = güncel pozisyon değeri + serbest nakit → **kesin**.
- Nakit satırı yoksa `budget_max` çıpalı tahmine düşer (geriye uyumlu).
- `sheets.parse_free_cash` / `SheetsLogger.get_free_cash` ile okunur.

---

## Testler

`90 test geçiyor.` Yeni test dosyaları:
- `tests/test_sizing.py` — saf öneri yardımcısı (tam adet, kesirli, karşılanamaz,
  özsermaye çıpası/kesin).
- `tests/test_sizing_v2.py` — motor: maliyet getiriyi düşürür, next_open ≠ close,
  deployment tavanı maruziyeti sınırlar, min_fill erteler, legacy/v2 çekişmede ayrışır.
- `tests/test_sheets.py` — NAKİT satırı okuma + pozisyon/kapalı/nakit ayrımı.

---

## Commit'ler (yalnız yerel — push edilmedi)

```
01eaa92  Slack sizing: Sheets NAKİT satırından kesin serbest nakit oku
0c7bc74  Sizing v2 + gerçekçilik katmanı + Rapor v2 (Görev 2.1/2.2)
```

## Notlar
- Bu branch, henüz `main`'e girmemiş **Faz 1 dalı** üzerine kuruludur; PR bütün yığını
  (Faz 1 + Faz 2) içerir ya da önce Faz 1 merge edilmelidir.
- Görev 2.1/2.2 tam tanım metni repoda yoktu; görev açıklaman + Faz 1 rapor/denetim
  referanslarından (`Görev 2.1 = ertesi-gün-açılış + komisyon`) türetildi.
- Push istersen `claude/sad-heyrovsky-847073` dalı uzağa gönderilebilir.
