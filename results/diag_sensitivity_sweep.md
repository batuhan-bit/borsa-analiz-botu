# Çöküş kalibrasyonu duyarlılık taraması (ön-kalibrasyon)

> Salt teşhis; kod **değiştirilmedi** — yalnız `sell_alerts.ranking_collapse_multiple`
> ve `sell_alerts.ranking_collapse_persist_days` config override'ıyla 4 **tekil**
> koşu (topluluk/pertürbasyon YOK — bu B.2 ensemble'ının yerine geçmez, kaba bir
> ön-kalibrasyon taramasıdır). Pencere: 2016-2019 (tune) — dönem ayrımına uygun.
> `slot_refill_cooldown_days` ve diğer tüm ayarlar `strategy.yaml` varsayılanında
> sabit tutuldu. Koşular Görev A'nın (cooldown/rotasyon birleştirme) commit'inden
> SONRAKİ kod üzerinde alındı.

## Izgara ve sonuçlar

| ranking_collapse_multiple | persist_days | işlem | rotation | ranking_collapse | technical_emergency | backtest_end | toplam getiri % | maliyet $ | ayda ort. uyarı |
|---|---|---|---|---|---|---|---|---|---|
| 2 | 3 | 553 | 151 | 340 | 56 | 6 | +23.72 | 983.95 | 8.25 |
| 2 | 5 | 393 | 160 | 169 | 58 | 6 | +94.29 | 893.81 | 4.73 |
| 3 | 3 | 421 | 151 | 208 | 56 | 6 | +69.70 | 915.69 | 5.50 |
| 3 | 5 | 320 | 170 | 90 | 54 | 6 | +160.40 | 849.87 | 3.00 |

*"Ayda ort. uyarı" = (ranking_collapse + technical_emergency çıkış sayısı) / 48 ay
(tune penceresindeki takvim ay sayısı) — uygulanan alert-tetikli satış sayısının
aylık ortalaması.*

**Not (mult=2, persist=3 satırı):** bu, `strategy.yaml`'daki güncel varsayılan
kombinasyondur. 553 işlem, Görev A'nın rotasyon-cooldown birleştirme düzeltmesinden
SONRAKİ rakamdır; o düzeltmeden önce aynı kombinasyon 548 işlem veriyordu (bkz.
`results/diag_548_check.md`). Fark (548→553), cooldown'un artık rotasyon
seçimini de etkilemesinin bir yan etkisidir: engellenen bir sembolün yerine
seçilen farklı sembol, sonraki ayların tetik zincirini hafifçe değiştiriyor —
kendi başına bir regresyon değil, aynı mekanizmanın rotasyon yoluna da
uygulanmasının doğal sonucu.

## Gözlemler (yalnız betimleyici — kalibrasyon kararı değil)

- **persist_days arttıkça** (3→5) her iki `multiple` değerinde de işlem sayısı,
  ranking_collapse sayısı ve aylık ortalama uyarı belirgin düşüyor
  (mult=2: 553→393 işlem, 8.25→4.73 uyarı/ay; mult=3: 421→320 işlem,
  5.50→3.00 uyarı/ay). Beklenen yön: daha uzun kalıcılık şartı, geçici
  sıralama dalgalanmalarını daha çok filtreliyor.
- **multiple arttıkça** (2→3, eşik sepet-içi 4→6'ya çıkıyor) aynı yönde:
  ranking_collapse sayısı ciddi düşüyor (persist=3: 340→208; persist=5: 169→90),
  çünkü eşik gevşedikçe daha az pozisyon "çökmüş" sayılıyor.
- **technical_emergency sayısı ızgarada neredeyse sabit** (54-58 arası) —
  beklenen: bu tetik `ranking_collapse_multiple`/`persist_days`'ten bağımsız,
  yalnız ATR eşiğine (`atr_exit_multiple`, sabit tutuldu) bağlı.
- En sıkı kombinasyon (mult=3, persist=5) en düşük churn'ü veriyor (320 işlem,
  ayda 3.0 uyarı) ve bu koşuda en yüksek toplam getiri de bu satırda — ancak
  bu **rastlantısal bir tune-penceresi gözlemi**, parametre seçim gerekçesi
  DEĞİLDİR (aşağıdaki uyarıya bakın).

## Dönem ayrımı uyarısı
Bu tablo yalnız **churn/uyarı yoğunluğunun** parametrelere nasıl tepki
verdiğini göstermek için üretildi (ön-kalibrasyon, teşhis amaçlı). Getiri/maliyet
sütunları izlenebilirlik için var; **parametre seçimi bu sayılara bakılarak
yapılmamalıdır** (CLAUDE.md: "Parametre ayarı ve konfigürasyon seçimi YALNIZ
2016-2019 verisinde yapılır" doğru, ama seçim disiplini `backtest/competition.py`
(B.3) fazlı yarışması üzerinden, tekil ad-hoc taramalarla değil, yürütülmelidir).
Nihai `ranking_collapse_multiple`/`persist_days` değerleri için karar B.3
konfig yarışmasına (`--phase tune`) bırakılmalıdır.
