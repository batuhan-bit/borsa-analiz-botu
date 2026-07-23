# Teşhis + Düzeltme: Slack'e sahte-veri raporu düştü

## Belirti
Elle işlemlerden sonra Slack'e şu mesaj düştü: tarih **2022-06-08** (2026 değil),
portföy **SPY/COST/NVDA/IONQ** (kullanıcının gerçek pozisyonları MO/MRK/LUNR/MU/MRVL/POWL),
sepet büyüklükleri **8 ve 3** (gerçek evren sepet başına 20), fiyatlar gerçek dışı
(**RGTI ~$329**).

## Kök neden (kanıtlı)
Mesaj **canlı akıştan (`bot.main`) gelmedi.** Byte-byte kaynağı
`scripts/send_test_report.py` — sepet-içi sıra PR'ında eklenen test script'i:
tarih 2022-06-08, `_HELD = SPY/COST/NVDA/IONQ`, sepet 8/3, `RGTI @ $329.66` hepsi
script çıktısıyla birebir. Script `os.getenv("SLACK_WEBHOOK_URL")` okuyordu — **üretimle
aynı** değişken — ve yerel `--send` ile gerçek kanala POST etti.

Doğrulayıcı kanıtlar:
- `bot/main.py`'de hiçbir fixture/geom/2022/fallback kodu yok; sentetik geometrik
  bar'lar yalnız script'te ve testlerde.
- Bugünkü gerçek koşu logu (07:44 UTC, schedule, success):
  `Portföy (6): MO, MRK, LUNR, MU, MRVL, POWL` + `Slack bildirimi gönderildi (2026-07-22)`
  → gerçek pipeline 6 pozisyonu okudu, sahte veriye DÜŞMEDİ.
- Merge 16:30 UTC; o saatten sonra hiç workflow koşusu yok → PR/merge bu mesajı
  tetiklemedi. PR `bot/main.py`'ye veya veri kaynağı/`as_of` seçimine dokunmadı.

## Üç soruya cevap
1. **Hangi kod yolu?** `scripts/send_test_report.py` (test script'i), üretim
   webhook'una yerel `--send`. Canlı akış fixture'a düşmedi.
2. **Merge tetikledi mi?** Hayır. PR yalnız gözlem render'ını değiştirdi + script'i
   ekledi; veri kaynağını/`as_of`'u etkilemedi. Merge sonrası koşu yok.
3. **Gerçek koşu 6 pozisyonu okudu mu?** Evet (log kanıtı). Sahte veriye düşme yok.

## Yapısal koruma (uygulandı — 3 katman, savunma derinliği)

**(A) Bayat-tarih kapısı** — `SlackNotifier.send()` karar tarihi bugünden
`notification.max_report_age_days` (3) günden eskiyse `ValueError`, POST etmez.
2022-06-08 mesajını kesin durdururdu.

**(B) Canlı akış veri-bütünlüğü kapısı** — `bot.main._assert_live_data`: fiyat verisi
(bars) boşsa ya da geçerli işlem günü yoksa (today_index<0) `RuntimeError`, gönderme.
`notification.abort_on_unreadable_data` (varsayılan açık).

**(C) Test script'i üretimden fiziksel ayrım** — `LiveDecision.synthetic` bayrağı;
üretim notifier'ı (`allow_synthetic=False`) sentetik kararı reddeder. Script artık
YALNIZ ayrı `SLACK_TEST_WEBHOOK_URL` okur (üretim `SLACK_WEBHOOK_URL`'ini asla),
ikisi aynıysa reddeder, `--send` için `--i-know-this-is-synthetic` onayı ister.

Eşikler `strategy.yaml notification:` altında (hardcode yok).

## Testler (+12)
- `test_slack.py`: bayat engel/taze geçiş/sentetik-red/test-kanalı-izin/yaş-kapısı-kapalı (5).
- `test_main_smoke.py`: `_assert_live_data` boş-bars/geçersiz-gün/geçerli (3);
  script sentetik-bayrak + webhook-reddi 4. Smoke bar'ları güncel tarihe taşındı
  (bayat kapısı canlı gönderimi engellemesin diye).
- Suite: **224 yeşil**.
