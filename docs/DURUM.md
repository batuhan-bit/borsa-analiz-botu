# DURUM — Sinyal Botu v2

> Oturum sonu durum özeti (CLAUDE.md kuralı). Son güncelleme: **2026-07-14** (FAZ B kodu + ping-pong churn teşhis/düzeltme).
> Aktif dal: `feature/rotation-v2` (main'e merge insan onayıyla).

## Dönem ayrımı disiplini (İHLAL EDİLEMEZ — CLAUDE.md)
- Parametre ayarı/konfig seçimi YALNIZ **2016-2019** verisinde.
- **2020-2022** doğrulama penceresi: aday konfig başına EN FAZLA BİR koşu.
- **2023-2026** nihai rapora kadar HİÇ bakılmaz; nihai raporda BİR kez.
- Doğrulama/nihai pencere sonucuna bakıp parametre değiştirmek **yasak**.

## FAZ A — Rotasyon motoru · ✅ TAMAM

Tüm görevler `feature/rotation-v2` dalında, ayrı commit'ler, 100 test yeşil.
v1 çalışma yoluna dokunulmadı (canlı akış hâlâ v1; legacy switchover FAZ C.1).

| Görev | Durum | Çıktı |
|------|-------|-------|
| A.1 Rotasyon çekirdeği | ✅ | `bot/rotation/engine.py` — per_basket / global_top_n hedef seçimi, fark (giren/çıkan/kalan), rebalans bandı. Deterministik ((-skor, sembol) sıralaması). `sizing.py` (ağırlık→adet). |
| A.2 Sıralama skoru S1/S2 | ✅ | `bot/rotation/scoring.py` — ortak `rank(symbols, as_of)` arayüzü. S1 = v1 teknik skoru (ağırlıklar değişmedi), S2 = momentum (son 126g, son 21g hariç; pencereler config'te). `make_ranker` seçer. |
| A.3 Kural-bazlı satış uyarıları | ✅ | `bot/rotation/alerts.py` — 3 tetik: teknik acil (N×ATR), sıralama çöküşü (2×top_n dışı), temel kırmızı bayrak (kazanç çöküşü / zarar+daralma / asimetrik içeriden satış / iki kaynak negatif). `AlertLedger` günde-bir spam koruması. |
| A.4 Slot doldurma + tema + gözlem | ✅ | Tema etiketleri `config/universe.yaml`'da (60/60). `slots.py` — slot_candidates (sepet/tema kısıtlı), daily_observation (eylemsiz; "eylem önerisi değildir"). |

### Yapısal değişiklik: evren tek gerçek kaynak
- Evren `config/strategy.yaml`'dan **`config/universe.yaml`'a taşındı**: her
  sembol `basket` + `theme`. strategy.yaml'da yalnız sepet ağırlıkları kaldı.
- Config yükleyici (`bot/config.py`) sembol listesini `baskets[*].universe`'e
  geri-doldurur → v1 sinyal motoru ve backtest **değişmeden** çalışır.
- Yeni erişimciler: `Strategy.rotation`, `universe_symbols`, `basket_of`,
  `theme_of`.

### Yeni config blokları (`strategy.yaml`)
- `rotation:` — frequency, selection, score, top_n, rebalance_band_pct,
  max_positions_per_theme, momentum.{lookback_days, skip_days}.
- `sell_alerts:` — atr_exit_multiple, ranking_collapse_multiple, fundamental.*.

## FAZ B — Backtest ve ölçüm katmanı · ✅ KOD TAMAM, ⏸ KOŞU İNSAN ONAYINDA

Tüm B.1/B.2/B.3 **makinesi + testleri** yazıldı; ayrı commit'ler, testler yeşil.
Gerçek-veri koşusu (yfinance + uzun süre) YAPILMADI — validate/final pencerelerine
bakmak geri döndürülemez ve dönem ayrımı disiplini gereği insan onayına tabidir.

| Görev | Durum | Çıktı |
|------|-------|-------|
| B.1 Rotasyon backtest | ✅ kod | `backtest/rotation_backtest.py` — sinyal kapanışta / icra ertesi gün açılışta; komisyon bps + sabit + sepet-bazlı kayma; maliyetsiz/maliyetli fark; satış-uyarısı tetikleri (teknik acil / sıralama çöküşü) + slot doldurma; rejim anahtarı; kapsam raporu. Determinizm bit-bazında testli. `scoring.py`'ye `score_series` (as_of paneli; `rank()` ile birebir). |
| B.2 Pertürbasyon topluluğu | ✅ kod | `backtest/ensemble.py` + `report_v2.py`. 50 koşu (başlangıç ±10g + kayma ±%50 çarpansal), medyan + [%10,%90] bandı; benchmark'lar SPY/eşit-ağırlık/sepet-ağırlıklı; tasarım sağlığı (bant > medyan±%30 → uyarı). `python -m backtest.report_v2` tek komut. Bantsız rakam yok (testli). |
| B.3 Konfig yarışması | ✅ kod | `backtest/competition.py`. 32 nokta ızgara (skor·seçim·N·ritim·rejim); fazlı CLI `--phase tune\|validate\|final`; fazlar arası JSON devir; validate/final ağdan önce `--i-understand-window-discipline` ister; en fazla 2 aday → aday başına 1 koşu → SPY'ı medyanda geçen tek kazanan → final tek bakış. |

### Yeni config blokları (`strategy.yaml`)
- `rotation_backtest:` — initial_capital, execution_lag_days, commission_bps,
  commission_fixed_usd, slippage_bps (sepet-bazlı), deployment_pct,
  regime.{enabled, benchmark, ma_days, deployment_pct}, windows.{tune,validate,final},
  ensemble.{runs, start_jitter_days, slippage_jitter_pct, band_*, health_band_pct, seed},
  competition.{grid.*, max_candidates}.

### Koşu komutları (insan tetikler — gerçek veri, uzun)
```
python -m backtest.rotation_backtest --start 2016-01-01 --end 2019-12-31   # tekil koşu
python -m backtest.report_v2 --window tune                                  # topluluk raporu
python -m backtest.competition --phase tune                                 # ızgara (2016-2019)
python -m backtest.competition --phase validate --i-understand-window-discipline
python -m backtest.competition --phase final --i-understand-window-discipline
```
Çıktılar `results/` altına md/json (commit'lenir; ham log/CSV değil).

## Teşhis + düzeltme: 1923 işlem anomalisi (ping-pong churn) · ✅ TAMAM

Teşhis (`results/diag_1923_trades.md`): 2016-2019 tune koşusu 1923 işlem üretti;
%92'si `ranking_collapse` satışıydı, %93'ü slot-doldurma alışıydı. Kök neden:
çöküş testi **küresel** sırayı (2×top_n = 12/60) kullanırken portföy/slot
**per_basket sepet-içi** sıraya göre işliyordu → meşru tutulan pozisyon her gün
"çökmüş" sayılıp satılıyor, boşalan slot yeniden doldruluyordu (aç-kapa döngüsü;
POWL 177, KTOS 344 round-trip). Bant değil — bant yalnız 48 aylık günde kontrol
ediliyor; churn günlük `alert_orders`'tan.

Üç parçalı **yapısal** düzeltme (ortak modüller — backtest + Faz C canlı yol):
| Parça | Nerede | Ne |
|------|--------|----|
| (1) Taban hizalama | `alerts.py` `collapse_cutoff`/`collapse_rank_map` | per_basket'te çöküş SEPET-İÇİ sıra + eşik `mult×positions_per_basket` (2×2=4); global_top_n'de küresel `mult×top_n` korunur. slot_candidates de aynı taban (testli). |
| (2) Kalıcılık şartı | `alerts.py` `RankingCollapseTracker` | çöküş ancak art arda `ranking_collapse_persist_days` (3) işlem günü sürerse tetiklenir; tek-gün gürültü satmaz. **Teknik acil MUAF** (ilk günden tetikler). |
| (3) Yeniden-giriş bekleme | `alerts.py` `AlertCooldown` + `slots.py` `excluded` | uyarıyla kapanan sembol `slot_refill_cooldown_days` (5) işlem günü slot adayı olamaz → günlük aç-kapa yapısal olarak imkânsız. |

Backtest bağlandı (`backtest/rotation_backtest.py` `alert_orders`). Yeni config:
`sell_alerts.ranking_collapse_persist_days`, `sell_alerts.slot_refill_cooldown_days`
(hardcode yok). Doğrulama (aynı tune penceresi): işlem **1923→548**,
ranking_collapse **1776→336**, ardışık-gün yeniden açılma **889→12** (kalan 12:
aylık rebalans/technical, slot-fill churn değil), maliyet **$3.100→$1.093**.
> Getiri sayıları yalnız mekanik düzelmeyi doğrular; varsayılanlar tune-getirisine
> göre optimize edilmedi (dönem ayrımı korunur — konfig seçimi hâlâ B.3 fazlı).

## Testler
- **133 test yeşil** (120 → +13). Yeni: `tests/test_rotation_pingpong.py` (POWL
  2016-06 deseni regresyonu — aynı desen → en fazla bir çıkış, yeniden açılma
  cooldown'a takılır); `test_rotation_alerts.py`'ye taban hizalama + kalıcılık +
  cooldown birim testleri; `test_rotation_slots.py`'ye cooldown-dışlama + ortak-taban.
- FAZ A/B dosyaları: `tests/test_rotation_backtest.py`, `test_rotation_ensemble.py`,
  `test_rotation_competition.py`; `test_rotation_scoring.py` (`score_series`).
- Çalıştırma: `python -m pytest -q`.

## Sıradaki
- **İnsan kararı:** FAZ B koşularını başlatmak (yukarıdaki komutlar, disiplin sırasıyla).
  ⏸ **FAZ B SONUNDA DUR** — nihai rapor insan değerlendirmesine sunulur; Faz C kararı
  bu rapora bağlıdır (aday SPY'ı validate'te medyanda geçemezse Faz C'ye geçilmez).

## Notlar
- `strategy.yaml` dışında sabit değer (hardcode) yok kuralına uyuldu (ATR periyodu 14
  hariç — bu modüller arası yerleşik konvansiyon, ayarlanabilir parametre değil).
- Her değişiklik sonrası test suite yeşil bırakıldı.
