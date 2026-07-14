# Görev A — Cooldown tek doğruluk kaynağı (rotasyon-günü açığının kapatılması)

> Kod değişikliği raporu (teşhis değil). Commit: `97d2983` — dal `feature/rotation-v2`.
> Önkoşul teşhis: `results/diag_548_check.md` (2016-2019 tune kompozisyon kontrolü).

## Sorun
`diag_548_check.md`'de tespit edildi: 384 alert-tetikli çıkışın **14'ü**,
`slot_refill_cooldown_days` (=5 işlem günü) sınırını ihlal ederek aynı sembolü
erken yeniden açıyordu. Bu 14 vakanın **tamamı rotasyon-icra gününde**
gerçekleşti (ör. KTOS: 2017-08-01 `technical_emergency` ile kapandı,
2017-08-02 rotasyon icrasında **anında** geri açıldı — gap=1 işlem günü).

## Kök neden
`AlertCooldown`, yalnız rotasyon-dışı günlerde çalışan `alert_orders` →
`slot_candidates(excluded=...)` çağrısında uygulanıyordu. Aylık
`rebalance_orders` (→ `engine.build_plan` → `RotationEngine._select_per_basket`
/ `_select_global_top_n`) cooldown durumundan tamamen habersizdi: rotasyon
günü geldiğinde, cooldown'daki bir sembol skoru yeterince yüksekse (per_basket
modunda sepetin tek/en iyi adayı bile olsa) sıradan seçilip anında geri
alınabiliyordu. Cooldown'un iki ayrı "doğruluk kaynağı" (biri alert-günü
doldurma, biri hiç yoktu — rotasyon günü) vardı; bu görev onları birleştirdi.

## Düzeltme (`backtest/rotation_backtest.py`)
- `calendar` hesaplandıktan hemen sonra `day_index_of = {d: i for i, d in enumerate(calendar)}`
  eklendi — hem `alert_orders`'ın hem `rank_fn_as_of`'un günü aynı işlem-günü
  indeksine çevirebilmesi için.
- `rank_fn_as_of(day)` — rotasyon seçiminin **TEK** skor kaynağı — artık
  `cooldown.blocked(day_index_of[day])` ile bekleme süresindeki sembolleri
  skorlanmadan eleyecek şekilde güncellendi. Bir sembol elendiğinde
  `RotationEngine._select_*` onu hiç göremez; per_basket/global_top_n seçimi
  otomatik olarak sıradaki uygun adaya kayar (engine.py'de değişiklik
  gerekmedi — enjeksiyon noktası zaten `rank_fn` idi).
- `slot_candidates(excluded=...)` çağrısı (alert-günü doldurma) **aynı**
  `cooldown` nesnesini kullanmaya devam ediyor — artık rotasyon ve alert-günü
  yolları **tek** `AlertCooldown` durumunu paylaşıyor, iki kopya/iki farklı
  mantık yok.
- Docstring/yorum güncellemeleri: `cooldown`'un artık "hiçbir yolda (rotasyon
  günü DAHİL) yeniden seçilemez" garantisi verdiği açıkça belirtildi.

## Regresyon testi (`tests/test_rotation_cooldown_unified.py`)
İki test, gerçek KTOS senaryosunu sentetik barlarla uçtan uca kurar (yalnız
IONQ + KTOS barı verilir → per_basket top-2 seçiminde ikisi de rekabetsiz
seçilir, skor gürültüsü devre dışı):

1. **`test_ktos_blocked_from_rotation_reentry_after_cooldown`** — KTOS Şubat
   rotasyonunda girer; Mart sinyalinden birkaç işlem günü önce çöker →
   `technical_emergency` ile satılır (cooldown'a kaydolur). Mart rotasyon
   icrası (satıştan ~3 işlem günü sonra, cooldown penceresi içinde) KTOS'u
   **yeniden seçmemeli** — test bunu doğruluyor.
2. **`test_cooldown_is_single_shared_instance_across_rotation_and_alert_paths`** —
   KTOS cooldown'dayken IONQ'nun (sepetin tek diğer adayı) normal işlem
   görmeye devam ettiğini doğrular — cooldown'un aşırı kısıtlama/yan etki
   yaratmadığını gösterir.

### Kanıt: test gerçekten önceki hatayı yakalıyor
Düzeltme commit'lenmeden önce `git stash` ile yalnız `rotation_backtest.py`
geçici olarak geri alındı ve test tekrar koşuldu:

```
FAILED tests/test_rotation_cooldown_unified.py::test_ktos_blocked_from_rotation_reentry_after_cooldown
AssertionError: KTOS cooldown içindeyken (Mart rotasyon icrasında) yeniden
açılmamalı — bulunan: [RotationTrade(symbol='KTOS', ... entry_date='2020-03-03', ...)]
```
Düzeltme geri yüklenince (`git stash pop`) aynı test **yeşile döndü**. Bu,
testin gerçek bir regresyonu (görünüşte geçerli ama hatalı davranışı)
yakaladığını, yalnızca kozmetik bir assertion olmadığını kanıtlar.

## Test suite durumu
- Düzeltme öncesi: 133 test yeşil.
- Düzeltme + regresyon testleri sonrası: **135 test yeşil** (`python -m pytest -q`).
- Determinizm testleri (`test_determinism_bitwise` vb.) etkilenmedi.

## Kapsam ve sınırlar
- Değişiklik yalnız **rotasyon seçimini** (rebalance_orders/build_plan) cooldown'a
  bağladı; alert-günü doldurma yolu zaten cooldown'luydu (önceki oturumun ilk
  düzeltmesi). Yani bu görev, ping-pong'un asıl kaynağını değil, **ikinci,
  daha dar bir açığı** (rotasyon günü istisnası) kapattı.
- `RotationEngine`/`engine.py` dosyasında hiçbir değişiklik gerekmedi — enjeksiyon
  noktası (`rank_fn`) zaten dışarıdan geldiği için düzeltme tamamen
  `rotation_backtest.py` (backtest orkestrasyonu) katmanında kaldı. Faz C'de
  canlı akış bağlandığında aynı `AlertCooldown` + `rank_fn` deseni izlenmeli.
- Kalibrasyon/parametre seçimi bu görevin kapsamı dışında; `ranking_collapse_multiple`,
  `persist_days`, `cooldown_days` değerleri hâlâ B.3 fazlı disipline tabidir
  (bkz. `results/diag_sensitivity_sweep.md`).
