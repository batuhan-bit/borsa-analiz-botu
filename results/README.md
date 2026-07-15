# results/ — Faz B ölçüm çıktıları

Rotasyon backtest ve topluluk raporları buraya markdown olarak yazılır (CLAUDE.md:
"Uzun koşuların ham logu context'e alınmaz; sonuçlar results/ altına md yazılır").
Bu klasördeki `.md` raporlar ve `.json` devir dosyaları commit edilir (dönem ayrımı
disiplininin commit geçmişiyle doğrulanabilir olması için) — ham CSV/log değil.

## Üretenler

| Komut | Çıktı |
|-------|-------|
| `python -m backtest.report_v2 --window tune` | `rotation_ensemble_tune_*.md` (medyan + bant) |
| `python -m backtest.competition --phase tune` | `competition_tune.md` + `competition_candidates.json` |
| `python -m backtest.competition --phase validate --i-understand-window-discipline` | `competition_validate.md` + `competition_winner.json` |
| `python -m backtest.competition --phase final --i-understand-window-discipline` | `competition_final.md` |

## Dönem ayrımı disiplini (İHLAL EDİLEMEZ — CLAUDE.md)

Fazlar SIRAYLA ve AYRI komutlarla koşulur; her faz kararını bir devir dosyasına
yazar, sonraki faz onu okur. Faz sınırı = commit sınırı; bir fazın sonucuna bakıp
önceki fazın parametresini değiştirmek bu yapıda mümkün değildir.

1. **tune (2016-2019):** ızgara serbestçe koşulur, en fazla 2 aday seçilir.
2. **validate (2020-2022):** aday başına BİR koşu; SPY'ı topluluk-medyanında geçen
   tek konfig kazanır. `--i-understand-window-discipline` zorunludur.
3. **final (2023-2026):** kazanan konfig TEK kez koşulur; rapor insan değerlendirmesine
   sunulur. **⏸ FAZ B SONUNDA DUR.**

> Bu raporları üretmek gerçek fiyat verisi (yfinance) ve uzun koşu gerektirir;
> validate/final pencerelerine bakmak geri döndürülemez bir karardır ve insan
> onayına tabidir.
