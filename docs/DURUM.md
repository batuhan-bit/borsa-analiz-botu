# DURUM — Sinyal Botu v2

> Oturum sonu durum özeti (CLAUDE.md kuralı). Son güncelleme: **2026-07-15** (FAZ B/C tamam + **FAZ D: D.1 + D.2 tamam; canlı cron devre dışı**).
> Aktif dal: `main` (Faz C+D merge edildi — PR #2 + PR #3 hotfix; main HEAD `7d7cc37`).
> ⏸ **Gerçek Slack/Sheets'e karşı canlı deneme YAPILMADI** — insan onayı bekliyor.
> 🔒 **daily.yml otomatik cron DEVRE DIŞI** (yalnız elle `workflow_dispatch`) — merge sonrası denetimsiz canlı koşu olmasın diye.

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

## Kompozisyon kontrolü (548 işlem) + cooldown tek doğruluk kaynağı · ✅ TAMAM

Düzeltme sonrası doğrulama koşusu (`results/diag_548_check.md`, 2016-2019 tune):
işlem sayısı düştü ama ranking_collapse payı hâlâ %61.3 (beklenen — üç meşru
tetikten biri); en çok işlem gören sembollerde kalıntı yok (KTOS 344→17,
POWL 177→11). Ancak **384 alert-çıkışın 14'ü**, `slot_refill_cooldown_days`
sınırını (gap < 5 işlem günü) ihlal ediyordu — **hepsi rotasyon-icra gününde**.
Kök neden: `AlertCooldown` yalnız `alert_orders`→`slot_candidates` çağrısında
uygulanıyordu; aylık `rebalance_orders` (`engine.build_plan`) cooldown'dan
habersizdi (gerçek örnek: KTOS 2017-08-01 technical_emergency → 2017-08-02
rotasyon icrasında anında geri açılıyordu, gap=1).

**Düzeltme (`backtest/rotation_backtest.py`):** `rank_fn_as_of` (rotasyon
seçiminin TEK skor kaynağı) artık aynı `cooldown` nesnesini sorgular; bekleme
süresindeki sembol skorlanmadan elenir → `engine.build_plan` onu asla hedef
seçemez, sıradaki uygun aday otomatik alınır. `slot_candidates(excluded=...)`
zaten aynı nesneyi kullanıyordu — artık **tek** `AlertCooldown` durumu hem
rotasyon hem alert-günü doldurma yolunu besliyor (`day_index_of` haritası ile).

Regresyon (`tests/test_rotation_cooldown_unified.py`): KTOS teknik-acil çıkışı
→ ertesi rotasyon günü YENİDEN SEÇİLEMEMELİ (fix'siz koda karşı kırmızı
olduğu doğrulandı, fix'li yeşil). IONQ'nun (cooldown'da olmayan tek diğer
aday) normal seyrettiği ayrıca doğrulandı (yan etki yok).

## Çöküş kalibrasyonu — varsayılanlar güncellendi (multiple=3, persist_days=5) · ✅ TAMAM

`config/strategy.yaml`'daki `sell_alerts.ranking_collapse_multiple` ve
`ranking_collapse_persist_days` varsayılanları **2/3 → 3/5** olarak değiştirildi.
Kaynak: `results/diag_sensitivity_sweep.md` — 2016-2019 (tune) penceresinde,
kod değişikliği YOK, yalnız config override ile 4 tekil koşu
(`ranking_collapse_multiple {2,3} × persist_days {3,5}`, `slot_refill_cooldown_days`
ve diğer ayarlar sabit).

**Seçim kriteri: churn/uyarı yoğunluğu** (getiri değil). Izgaradaki en düşük
churn'ü mult=3/persist=5 verdi:

| kombinasyon | işlem | ranking_collapse | ayda ort. uyarı |
|---|---|---|---|
| mult=2, persist=3 (eski varsayılan) | 553 | 340 | 8.25 |
| mult=2, persist=5 | 393 | 169 | 4.73 |
| mult=3, persist=3 | 421 | 208 | 5.50 |
| **mult=3, persist=5 (yeni varsayılan)** | **320** | **90** | **3.00** |

Gerekçe **yalnız** churn kriterine (işlem sayısı + ranking_collapse sayısı +
aylık ortalama uyarı — hepsi ızgaradaki en düşük) dayanıyor; sweep raporunda
aynı tabloda görünen getiri sayıları (mult=3/persist=5 satırında en yüksek
getiri de vardı) **seçim gerekçesi olarak KULLANILMADI** — bu, dönem ayrımı
disiplininin (CLAUDE.md) churn-tabanlı, getiri-kör bir kalibrasyon kararı
olmasını sağlamak içindir. Nihai/geniş-kapsamlı parametre seçimi hâlâ B.3
konfig yarışmasının fazlı disiplinine (`--phase tune|validate|final`) tabidir;
bu değişiklik yalnız çöküş-tetiği varsayılanını teşhis bulgusuna göre düzeltir.

Test suite bu değişiklikle etkilendi: `tests/test_rotation_alerts.py`'de dört
mekanizma testi (`test_collapse_cutoff_per_basket_uses_positions_per_basket`,
`test_collapse_cutoff_global_uses_top_n`, `test_ranking_collapse_requires_persist_days`,
`test_persistence_resets_on_one_day_recovery`, `test_dropped_symbol_streak_resets_on_reentry`)
config'in kalibre edilmiş varsayılanına örtük olarak bağımlıydı (`multiple=2`
varsayıyordu); yeni `_strat_with_multiple(2, ...)` yardımcısıyla config
varsayılanından bağımsız hale getirildi — mekanizma testleri artık hangi
sayı kalibre edilirse edilsin kırılmaz.

## B.3 düzeltme: aday seçiminde etkin-konfigürasyon tekilleştirmesi · ✅ TAMAM

Teşhis: `results/competition_candidates.json`'da seçilen 2 adayın ikisi de
`s2_momentum·per_basket·N=6/8·biweekly·rejimK` idi — `selection=per_basket`
iken `top_n` hiçbir yerde okunmuyor (pozisyon sayısını `positions_per_basket`
belirler), yani bu iki ızgara noktası **aynı çalışan konfigürasyon**; aday
listesinin bir slotu gerçekte tekrar eden bir noktaya gitmişti. Ayrıca
"Seçilen adaylar" bölümündeki gerekçe metnine `render_report_md`'nin
`### {label}` başlığı yapışıyordu (metin tekrarı).

**Düzeltme (`backtest/competition.py`):** `GridPoint.effective_key` — kanonik
kimlik, `per_basket`'te `top_n`'i hariç tutar. `select_candidates` artık bu
anahtara göre tekilleştirir (en iyi sıralı olan tutulur); rapor satırı
`render_report_md` başlığını tekrar etmeden yalnız medyan/bant yazar.
Test: `tests/test_rotation_competition.py::test_select_candidates_dedupes_ineffective_top_n`;
`test_max_candidates_caps_selection` `global_top_n`'e taşındı (top_n orada etkin).

**Izgara yeniden koşulmadı** (deterministik, sonuçlar zaten `results/competition_tune.md`
tablosunda) — mevcut tablo parse edilip düzeltilmiş `select_candidates` ile
adaylar yeniden seçildi; `results/competition_candidates.json` ve
`competition_tune.md` güncellendi. Yeni adaylar: `s2_momentum·per_basket·N=6·
biweekly·rejimK` ve `...·rejimA` (önceki N=6/N=8 tekrarı yerine gerçekten
farklı iki konfigürasyon). Bu, dönem ayrımı disiplinini ihlal etmez — tune
penceresi sonuçlarına dokunulmadı, yalnız aynı pencereden aday çıkarma mantığı
düzeltildi.

## FAZ B koşuları tamamlandı (insan onayıyla) · ✅ TAMAM

`python -m backtest.competition --phase tune|validate|final` sırasıyla insan
onayıyla çalıştırıldı (dönem ayrımı disiplini korunarak, faz sınırı = commit
sınırı):
- **tune** (2016-2019): ızgara koşuldu, 2 aday seçildi (`results/competition_tune.md`,
  `competition_candidates.json`).
- **validate** (2020-2022): her aday BİR kez koşuldu; kazanan
  `s2_momentum·per_basket·N=6·biweekly·rejimK` — SPY'ı topluluk-medyanında
  geçti (`results/competition_validate.md`, `competition_winner.json`).
- **final** (2023-2026): kazanan TEK konfig BİR kez koşuldu — Strateji
  medyan **%+349.10** [%+323.76, %+370.93], SPY al-tut %+104.43
  (`results/competition_final.md`). ⏸ Faz C kararı bu rapora bağlı, insan
  değerlendirmesi bekliyor.

### Final rapora MaxDD, işlem sayısı, toplam maliyet sütunları · ✅ TAMAM

Talep: final raporunda getirinin yanında strateji + benchmark'lar için MaxDD
(medyan+bant), strateji için işlem sayısı ve toplam maliyet görülsün.
Tespit: bu değerler her ensemble koşusunda zaten hesaplanıyordu
(`RotationBacktestResult.max_drawdown_pct/num_trades/total_cost`) ama
`run_ensemble` yalnız `total_return_pct`'i tutup gerisini atıyordu — hiçbir
ham koşu verisi diskte saklı değildi, yani mevcut kayıtlardan hesaplanamadı.

**Değişiklik (`backtest/ensemble.py`):** her koşuda strateji için MaxDD/işlem/
maliyet örneklemi toplanıyor (`strategy_maxdd/trades/cost`, medyan+bant);
benchmark'lar (SPY al-tut, eşit-ağırlık, sepet-ağırlıklı) için de normalize
fiyat eğrisinden (`_normalized_curve`/`_composite_curve`) MaxDD medyan+bant
hesaplanıyor (`benchmark_maxdd`). `render_report_md` tabloya 3 yeni sütun
ekledi; işlem/maliyet yalnız Strateji satırında (benchmark'larda "—" —
gerçek işlem/maliyet modellenmiyor).

Final penceresi kurala göre BİR kez koşulur; bu sütunları eklemek ham
koşu verisi saklanmadığı için ikinci bir final koşusu gerektirdi — insan
onayı alınarak çalıştırıldı. Sabit `seed` + aynı kazanan config nedeniyle
getiri rakamları **birebir aynı** çıktı (%+349.10 vb., doğrulandı) — hiçbir
karar/parametre değişmedi, yalnız ek ölçüm sütunu eklendi.

## FAZ C — Canlı entegrasyon · ✅ KOD TAMAM, ⏸ CANLI DENEME İNSAN ONAYINDA

Dal `feature/live-switchover`; her görev ayrı commit; testler yeşil; Slack
mesajları snapshot-testli. Bağlayıcı kararlar (kullanıcı) uygulandı:

**Canlı konfig = Faz B kazananı** (`results/competition_winner.json`):
`s2_momentum · per_basket · N=6 · biweekly · rejim KAPALI`. `strategy.yaml`
canlı varsayılanları buna çekildi (score s1→s2, frequency monthly→biweekly);
`tests/test_live_config.py` kazananla eşitliği koruyan dönem-ayrımı bekçisidir
(kazanan parametresi yeniden doğrulama yapılmadan değişirse test kırılır).

| Görev | Durum | Çıktı |
|------|-------|-------|
| C.1 Ritim | ✅ | `bot/rotation/calendar.py` — `rotation_days`/`is_rotation_day`; backtest + canlı ORTAK kural. Takvim gerçek işlem günlerinden kurulur → tatil/hafta sonu kayması bedava doğru (testli). |
| C.1 Cooldown kalıcılığı | ✅ | `bot/rotation/cooldown_store.py` — GitHub Actions stateless; cooldown **tarih-çıpalı** saklanır (indeks değil → çekilen pencereden bağımsız), her koşu `reconstruct_cooldown` ile AYNI AlertCooldown'ı kurar. Sheets 'Cooldown' sekmesi; kapalıysa zarif düşüş. |
| C.1 Canlı akış | ✅ | `bot/rotation/live.py` `run_live_flow` — TEK "bugün" için öneri (icra manuel). Backtest deseniyle birebir: TEK AlertCooldown + rank_fn enjeksiyonu. Her gün uyarı taraması + slot doldurma + gözlem; rotasyon günü ek olarak giren(+💰)/çıkan/kalan/rebalans. Çöküş kalıcılığı fiyat geçmişinden yeniden türetilir (ayrı depo yok). |
| C.1 Slack v2 | ✅ | `bot/notify/slack.py` — v1 eşik BUY/SELL/HOLD biçimi TAMAMEN kaldırıldı; v2 rotasyon mesajı. Snapshot-testli (altın JSON `tests/snapshots/`). |
| C.1 v1 emekliliği | ✅ | `bot/main.py` artık `run_live_flow` çağırır (v1 motoru DEĞİL). `bot/legacy_engine/` — v1 SignalEngine+stop silinmedi ama isimli emekli façade'a taşındı; hiçbir çalıştırma yolu çağırmaz. `daily.yml` v2'ye güncellendi (komut aynı). |
| C.2 Karne | ✅ | `bot/reporting/scorecard.py` (saf) + Sheets 'Karne' sekmesi. Her öneri/uyarı sinyal tarihi+fiyatıyla; 5/20/60g ileri getiri elle müdahalesiz doldurulur (pencere kapandıkça). Aylık özet (portföy vs SPY vs evren al-tut) rotasyon gününde Slack'e. |
| C.2 Sistem-dışı | ✅ | `reconcile_positions` — Pozisyonlar'daki, sistemin hiç önermediği elle işlemler `sistem-dışı` etiketlenir ve karnede ayrı satırda izlenir (testli). |

### Cooldown kalıcılık tasarımı (kullanıcı "öner sonra uygula" dedi)
Seçim: **Sheets-tabanlı, tarih-çıpalı.** Sheets zaten operasyonel durum deposu
(Pozisyonlar/Performans); 'Cooldown' sekmesi eklemek repo yazma izni gerektirmez
(`daily.yml` `contents: read` kalır), commit/push churn'ü ve concurrency çakışması
yok. İndeks yerine **uyarı tarihi** saklanır: AlertCooldown'ın tam-sayı day_index'i
çekilen geçmiş penceresine bağlı (kararsız); tarih ise değildir → her koşu takvimi
kurup tarih→indeks çevirisiyle aynı nesneyi yeniden kurar.

### ⚠️ Canlıya almadan önce (insan)
- Gerçek Slack webhook + Google Sheets kimlikleri ile İLK canlı koşu insan
  gözetiminde yapılmalı (bu oturumda YAPILMADI — kullanıcı talebi).
- Temel kırmızı-bayrak tetiği canlıda şimdilik pasif (fundamentals boş geçiliyor);
  A.3 makinesi hazır, veri sağlayıcı bağlanması ayrı bir adım.

## FAZ D — Düşük bütçeli canlı dönem ve devreye alma · ✅ TAMAM

Dal `feature/live-switchover`; her görev ayrı commit; testler yeşil.

| Görev | Durum | Çıktı |
|------|-------|-------|
| D.2 Küçük bütçe uyumu | ✅ | `backtest/small_budget.py` — Faz B kazananını İKİ bütçe mekaniğiyle (standart $3.000/sabit $0/tam hisse **vs** küçük $1.000/sabit $1.50/kesirli) aynı final penceresinde topluluk (B.2 altyapısı, 50 koşu) koşup yan yana raporlar. Koşu-zamanı dönem-ayrımı bekçisi: aktif rotasyon config'i `competition_winner.json` ile eşleşmezse durur. Çıktı `results/small_budget_1000.md`. |
| D.1 Devreye alma sözleşmesi | ✅ | README "Beklentiler ve Devreye Alma" bölümü — 12 ay bağlılık / 3 yıl adil değerlendirme / ilk çeyrek gürültü; başarı kıstası (12a getiri ≥ SPY VE MaxDD ≤ 1.5×SPY, yalnız 12. ay); $1.000 operasyonel 3. ay kapısı; iki sınırlama; sayısal eşikler ✅ ONAYLANDI (tarih: 2026-07-15) — doluluk ≥%95, maliyet sapması tek yönlü ≤×1.25, uyarı yoğunluğu ayda 2-4 (yumuşak bant), 12. ay sermaye varsayımı README'ye eklendi. |

### D.2 sonucu (final penceresi 2023-2026, ölçüm koşusu)
- **Standart $3.000 satırı `competition_final.md`'yi BİREBİR yeniden üretti**
  (getiri %+349.10, MaxDD %-22.73, 264 işlem, maliyet $966.33) → deterministik,
  parametre kayması YOK kanıtı.
- **Küçük $1.000:** getiri %+192.33 [%+159.07, %+216.91], MaxDD %-26.35,
  248 işlem, maliyet $976.49, ortalama sermaye $1.844.
- **Yıllık maliyet / ortalama sermaye:** standart **%3.70** vs küçük **%14.68**
  → küçük bütçe **3.96×** daha ağır maliyet sürüklemesi (sabit $1.50 küçük
  pozisyonda oransal büyür). Bu oran README'ye tek cümleyle taşındı.

### Dönem ayrımı notu (D.2)
Bu bir **ölçüm/doğrulama** koşusudur — parametre SEÇMEZ. Kazananın rotasyon
ayarları (score/selection/top_n/frequency/regime) AYNEN kullanıldı (koşu-zamanı
bekçisi + `test_live_config` guard); yalnız bütçe mekaniği (sermaye/komisyon/
kesirlilik) değişti. Final penceresine "yeni bakış" değildir: zaten incelenmiş
pencerede, donmuş kazanan config'le, ölçüm sütunu eklemek için deterministik
yeniden koşu (competition_final.md'ye MaxDD/maliyet sütunu eklenirken kullanılan
aynı emsal). Getiri sayıları hiçbir parametre kararına girdi olmadı.

### Config değişikliği (strategy.yaml)
- `rotation_backtest.fractional_shares: false` (standart koşu tam-sayı hisse).
- `rotation_backtest.small_budget:` bloğu — initial_capital 1000,
  commission_fixed_usd 1.5, fractional_shares true, max_price_vs_target null
  (kesirli hisse destekli olduğu için pasif; broker değişirse tek satırla açılır).
  Bu blok YALNIZ `small_budget` koşusunda okunur; standart koşuları etkilemez.

## Testler
- **186 test yeşil** (184 → +2: PR #3 hotfix — NaN→int koruması sheets + live).
- **184 test yeşil** (180 → +4: fractional adet üretimi, sabit komisyon per-trade
  maliyeti, ensemble maliyet/sermaye oranı toplama, küçük bütçe daha yüksek oran).
- **180 test yeşil** (140 → +40: live_config 2, calendar 7, cooldown_store 7,
  live 9, scorecard 9, slack v2 +3, main_smoke 2, +1).
  Yeni: `tests/test_rotation_pingpong.py` (POWL
  2016-06 deseni regresyonu — aynı desen → en fazla bir çıkış, yeniden açılma
  cooldown'a takılır); `test_rotation_cooldown_unified.py` (KTOS teknik-acil →
  rotasyon-günü yeniden seçim engeli, gerçek fix'e karşı doğrulandı);
  `test_rotation_alerts.py`'ye taban hizalama + kalıcılık + cooldown birim
  testleri; `test_rotation_slots.py`'ye cooldown-dışlama + ortak-taban;
  `test_rotation_ensemble.py`'ye MaxDD/işlem/maliyet toplama + render testleri.
- FAZ A/B dosyaları: `tests/test_rotation_backtest.py`, `test_rotation_ensemble.py`,
  `test_rotation_competition.py`; `test_rotation_scoring.py` (`score_series`).
- Çalıştırma: `python -m pytest -q`.

## Sıradaki
- ⏸ **İNSAN ONAYI:** Faz C/D kod tamam ama gerçek Slack/Sheets'e karşı canlı deneme
  YAPILMADI (kullanıcı talebi). İlk canlı koşu insan gözetiminde ELLE tetiklenmeli
  (daily.yml cron devre dışı; yalnız `workflow_dispatch`).
- ✅ **EŞİKLER ONAYLANDI (2026-07-15):** README devreye-alma tablosundaki sayısal
  eşikler kullanıcı tarafından onaylandı (3. ay operasyonel + 12. ay performans
  kapıları); revize doluluk/maliyet/uyarı-yoğunluğu eşikleri ve 12. ay sermaye
  varsayımı README'ye işlendi.
- ✅ **MAIN'E MERGE TAMAM (2026-07-15):** Faz C+D main'e girdi.
  - PR #2 (`feature/live-switchover` → main, merge `d043d26`): tüm Faz C+D dosyaları
    (rotation/*, reporting/scorecard.py, backtest/*, testler).
  - PR #3 (hotfix, merge `7d7cc37`): canlı akışta NaN→int çökmesi düzeltmesi
    (sheets.py + live.py + testler).
  - main HEAD **`7d7cc37`**; 186 test yeşil. Cron hâlâ devre dışı → denetimsiz canlı
    koşu riski yok.
  - **Not (kafa karışıklığı kaydı):** Bir ara local `main` bayat (`1774eae`) kalmış,
    `bot/rotation/live.py` boş/iskelet sanılmıştı. Kod kaybı yoktu; sebep local repo'nun
    PR #2 merge'ünü fetch etmemesiydi. `git fetch` + FF senkron ile çözüldü.

## Notlar
- `strategy.yaml` dışında sabit değer (hardcode) yok kuralına uyuldu (ATR periyodu 14
  hariç — bu modüller arası yerleşik konvansiyon, ayarlanabilir parametre değil).
- Her değişiklik sonrası test suite yeşil bırakıldı.
