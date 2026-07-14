# DURUM — Sinyal Botu v2

> Oturum sonu durum özeti (CLAUDE.md kuralı). Son güncelleme: **2026-07-14**.
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

## Testler
- **100 test yeşil.** Yeni dosyalar: `tests/test_universe.py`,
  `test_rotation_engine.py`, `test_rotation_scoring.py`,
  `test_rotation_slots.py`, `test_rotation_alerts.py`.
- Çalıştırma: `python -m pytest -q`.

## Sıradaki: FAZ B — Backtest ve ölçüm katmanı
Ayrı oturum (koşular uzun; ham log context'e alınmaz, sonuç `results/` md).
- B.1 Rotasyon backtest'i (`backtest/rotation_backtest.py`) — ertesi-gün-açılış
  dolgu, komisyon 5 bps + sepet-bazlı kayma, satış-uyarısı tetikleri dahil.
- B.2 Pertürbasyon topluluğu (50 koşu, medyan + [%10,%90] bandı; bantsız rakam yok).
- B.3 Konfig yarışması **YALNIZ 2016-2019**; en fazla 2 aday → 2020-2022 birer
  doğrulama → tek kazanan → 2023-2026 nihai (bir kez). ⏸ **FAZ B SONUNDA DUR.**

## Notlar
- `strategy.yaml` dışında sabit değer (hardcode) yok kuralına uyuldu.
- Her değişiklik sonrası test suite yeşil bırakıldı.
