# Veri Tutarlılığı Doğrulaması — temettü+bölünme ayarlı fiyat serisi

_Soru: backtest, canlı motor ve benchmark üçü de temettü+bölünme düzeltmeli
AYNI fiyat serisini mi kullanıyor? Benchmark temettüsüz çıkarsa düzelt._

**Sonuç: Üçü de temettü+bölünme ayarlı. Benchmark temettüsüz DEĞİL —
düzeltilecek hata yok, `rapor.md` sayıları geçerli kaldı.**

## 1) Fiyat kaynakları (kod izi)

| Yol | Kaynak fonksiyonu | Ayarlama |
|---|---|---|
| **Backtest** | `load_bars` → `YFinanceClient.get_daily_bars` | `auto_adjust=True` (split + temettü) — `bot/data/yfinance_client.py:50` |
| **Benchmark** | `run_benchmarks` → **aynı** `load_bars` → `buy_and_hold` | aynı ayarlı seri, `df["close"]` — `backtest/benchmark.py:79` |
| **Canlı motor** | `SignalEngine._get_bars` → **Alpaca** (birincil), yfinance (yedek) | Alpaca `Adjustment.ALL` (`bot/data/alpaca_client.py:73`) + yfinance `auto_adjust=True` |

- Backtest ve benchmark **birebir aynı** veri yolunu (yfinance `auto_adjust=True`)
  paylaşır — benchmark, backtest'in kullandığı seriyi aynen kullanır.
- Canlı motor birincil olarak Alpaca'yı kullanır; o da tam (split+temettü)
  ayarlıdır. Anahtar yoksa yfinance `auto_adjust=True` yedeğine düşer.

## 2) Ampirik kanıt — benchmark gerçekten temettü içeriyor mu?

`auto_adjust=True` ile geçmiş fiyatlar gelecekteki temettüler için AŞAĞI
geri-düzeltilir; dolayısıyla ayarlı `close` üzerinden getiri = **toplam getiri**
(fiyat + yeniden yatırılan temettü). Benchmark'ın kullandığı cache serisinden:

**SPY, 2016-2022 (benchmark işlem penceresi)**

| Ölçüm | Değer | Yorum |
|---|---|---|
| İlk ayarlı kapanış (2016-01-04) | **$169.47** | SPY o gün fiilen ~$200'dı → temettü geri-düzeltmesi UYGULANMIŞ |
| Son ayarlı kapanış (2022-12-30) | $365.67 | |
| Toplam getiri | **+115.77%** | Fiyat-yalnız ~+91% olurdu; +115.77% ≈ toplam getiri (temettü dahil) |

Bu değer `rapor.md`'deki **SPY (al-tut) +115.77%** satırıyla birebir aynı →
benchmark temettü içeriyor. Ana dönem (2023-2026) SPY al-tut = +78.24% de aynı
seriden gelir.

> Doğrulama script'i: geçici (`scratchpad/verify_div.py`); cache'li ayarlı
> serilerden okur, ağ gerektirmez.

## 3) Tek nüans (hata değil, bilinçli tasarım)

Canlı motor **Alpaca** (IEX beslemesi), backtest/benchmark ise **yfinance**
kullanır. İkisi de tam temettü+bölünme ayarlıdır, ama farklı **sağlayıcıdır** —
yani "ayarlama metodolojisi" ortaktır, literal olarak "aynı vendor serisi"
değildir. Bu ayrım kasıtlıdır:

- Canlı yol taze/güncel veri için Alpaca'ya ihtiyaç duyar.
- Backtest derin geçmiş (2016+) için yfinance'e ihtiyaç duyar.

Sağlayıcılar arası küçük fiyat farkları olabilir; ancak temettü/bölünme
tutarlılığı üç yolda da korunur. Bu, sayısal sonuçları etkilemez.

## Karar

- Doğrulama **geçti**: üç yol da temettü+bölünme ayarlı.
- Benchmark temettüsüz **değil** → kod düzeltmesi yapılmadı.
- `rapor.md` (Rapor v2) **yeniden üretilmedi**; sayılar zaten doğru. Yeniden
  üretim, olmayan bir "düzeltmeyi" yansıtacağı için bilinçli olarak yapılmadı.
