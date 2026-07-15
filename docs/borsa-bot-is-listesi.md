# Borsa Analiz Botu — İyileştirme İş Listesi

> Bu dosya, botun bağımsız değerlendirmesinden çıkan bulguların Claude Code'da
> uygulanabilir görevlere dönüştürülmüş halidir. Görevler faz sırasıyla
> yapılmalıdır: Faz 1 kod eklemeden önce mevcut sonuçların gerçek mi yanılsama
> mı olduğunu ölçer; sonraki fazlar bu ölçüme göre anlam kazanır.
>
> Genel kurallar:
> - Faz 1 ve 2 boyunca `strategy.yaml` parametrelerine DOKUNMA (eşikler,
>   ağırlıklar donduruldu). Amaç mevcut konfigürasyonu görülmemiş veride test
>   etmek; parametre ayarı yapılırsa test in-sample'a döner.
> - Her görev kendi PR'ı/commit'i olacak şekilde küçük tutulmalı; mevcut 57
>   birim test yeşil kalmalı, yeni davranışlar için test eklenmeli.
> - Tüm yeni ayarlar `config/strategy.yaml`'a eklenmeli, kodda sabit değer
>   (hardcode) olmamalı.

---

## FAZ 1 — Doğrulama (önce gerçeği öğren)

### Görev 1.1 — Buy-and-hold kıyas çizgisi (benchmark)

**Bağlam:** 60 sembollük evren bugünden geriye bakılarak seçildi ve son 3 yılın
kazanan temalarını içeriyor (survivorship/hindsight bias). Backtest'teki +188%
ile +683% arası getirilerin ne kadarının stratejiden, ne kadarının evrenin
kendisinden geldiği bilinmiyor. Botun katma değeri ancak aynı evrenin pasif
getirisiyle kıyaslanarak ölçülebilir.

**Yapılacak:**
- `backtest/benchmark.py` oluştur: aynı 60 sembolü, aynı başlangıç sermayesiyle,
  eşit ağırlıkla (ve ayrıca sepet ağırlıklarıyla: %40/%35/%25) al-ve-tut olarak
  simüle et. Aynı dönem, aynı veri kaynağı (yfinance), temettü dahil
  (adjusted close — bkz. Görev 2.2).
- İkinci bir varyant: sadece SPY al-ve-tut (piyasa kıyası).
- `backtest.py` çıktısına kıyas tablosu ekle: strateji vs eşit-ağırlık evren vs
  sepet-ağırlıklı evren vs SPY. Her biri için: toplam getiri, yıllıklandırılmış
  getiri, maksimum düşüş, Sharpe (rf=0 kabul edilebilir), Calmar.

**Kabul kriteri:** Backtest raporu artık "strateji şu kıyas çizgilerine göre
şu kadar alfa üretti/üretmedi" cümlesini sayıyla kurabiliyor. Sonuç ne çıkarsa
çıksın rapora dürüstçe yazılıyor.

---

### Görev 1.2 — Backtest dönemini 2016'ya kadar uzat (ayı piyasası testi)

**Bağlam:** "Ayı piyasası verisi yok" tespiti yanlıştı — yfinance 2016 ve
öncesine gider. 2018 Q4 düzeltmesi, Mart 2020 çöküşü ve 2022 tam yıllık ayı
piyasası serbestçe erişilebilir. Trend filtresi / yönlü hacim / R/R kapısının
gerçek değeri ancak bu rejimlerde ölçülebilir. Parametreler 2023-2026'ya
bakılarak ayarlandığı için 2016-2022 fiilen out-of-sample dönemdir.

**Yapılacak:**
- `backtest.py`'a başlangıç/bitiş tarihi parametresi ekle (CLI argümanı +
  config), varsayılan davranış bozulmasın.
- Verisi olmayan semboller (ör. 2021 sonrası halka arzlar: LUNR vb.) için
  politika: sembol, verisi başladığı tarihte evrene katılır; öncesinde yok
  sayılır. Her koşuda sepet bazında "kapsam raporu" yaz (dönem başında kaç
  sembol aktifti).
- 2016-2022 dönemini, mevcut (dondurulmuş) parametrelerle, üç konfigürasyonda
  koş: (a) trend filtresi kapalı, (b) trend filtresi açık, (c) trend filtresi +
  yönlü hacim + R/R kapısı. Görev 1.1'deki kıyas çizgileriyle birlikte raporla.
- Rejim bazlı alt-rapor: 2018-10→2018-12, 2020-02→2020-04, 2022-01→2022-12
  pencerelerinde strateji vs benchmark düşüşü ayrıca gösterilsin.

**Kabul kriteri:** "Koruyucu özellikler ayı piyasasında gerçekten koruyor mu?"
sorusuna sayısal cevap veren tek bir rapor üretiliyor. Parametrelere
dokunulmadığı commit geçmişinden doğrulanabiliyor.

---

### Görev 1.3 — İstatistiksel dürüstlük katmanı

**Bağlam:** 3 yılda 32-51 işlem, konfigürasyonlar arası kazanma oranı farkını
(%42 vs %68) anlamlı saymak için çok küçük bir örneklem. Raporlar bunu
söylemiyor ve yanlış güven veriyor.

**Yapılacak:**
- Backtest raporuna her koşu için: işlem sayısı, işlem başına ortalama
  getiri, getiri dağılımının bootstrap %90 güven aralığı (işlemleri
  yerine-koymalı 10.000 kez örnekleyerek toplam getiri dağılımı).
- İki konfigürasyon karşılaştırılırken güven aralıkları çakışıyorsa rapora
  otomatik uyarı bas: "Fark örneklem gürültüsünden ayırt edilemiyor."

**Kabul kriteri:** Hiçbir backtest raporu artık ham getiri rakamını güven
aralığı ve işlem sayısı olmadan sunmuyor.

---

## FAZ 2 — Backtest gerçekçiliği

### Görev 2.1 — Dolgu fiyatı, komisyon ve kayma (slippage)

**Bağlam:** Sinyal kapanış sonrası üretiliyor, kullanıcı en erken ertesi gün
manuel işlem yapıyor. Backtest sinyal günü kapanışından dolduruyorsa bu bir
look-ahead türüdür ve gerçek icrayı temsil etmez. Komisyon/kayma da
modellenmiyor.

**Yapılacak:**
- Önce mevcut durumu denetle: backtest hangi fiyattan alıyor/satıyor?
  Bulguyu rapora yaz.
- Dolgu modelini "sinyal gününü izleyen ilk işlem gününün AÇILIŞ fiyatı"
  olarak değiştir. Stop-loss tetiklenmesi için gün içi düşük (Low) fiyatı
  kullan; gap-down durumunda dolgu = açılış (stop fiyatı değil).
- `strategy.yaml`'a ekle: `costs: {commission_per_trade_usd: X,
  slippage_bps: 15}` (varsayılan 15 baz puan, ayarlanabilir). Her işleme
  uygula.
- Eski (kapanış dolgulu, maliyetsiz) ve yeni (açılış dolgulu, maliyetli)
  sonuçları bir kez yan yana raporla ki fark görülsün.

**Kabul kriteri:** Backtest, manuel-ertesi-gün icra gerçeğine uygun dolgu
kullanıyor; maliyetler config'ten yönetiliyor; birim test var (gap-down'da
stop dolgusunun açılıştan olduğunu doğrulayan test dahil).

---

### Görev 2.2 — Toplam getiri (temettü) denetimi

**Bağlam:** Düşük volatilite sepetinin (XLU, XLP, savunmacılar) getirisinin
önemli kısmı temettüdür. Backtest düzeltilmemiş kapanış kullanıyorsa bu sepet
sistematik olarak cezalandırılıyor demektir.

**Yapılacak:**
- yfinance çağrılarında `auto_adjust` durumunu denetle; backtest ve benchmark
  her ikisi de temettü+bölünme düzeltmeli fiyat (adjusted close) kullansın.
- Dikkat: canlı sinyal motorundaki GÖSTERGE hesapları (RSI, MA, ATR) ile
  backtest aynı fiyat serisini kullanmalı — biri düzeltilmiş biri ham olursa
  sinyaller ayrışır. Tek bir veri erişim katmanında standardize et
  (`bot/data/`), testle sabitle.

**Kabul kriteri:** Fiyat serisi tercihi tek yerde tanımlı, backtest/canlı/
benchmark tutarlı; temettü etkisi benchmark raporunda görünür.

---

## FAZ 3 — Tasarım düzeltmeleri

### Görev 3.1 — Temel analiz katmanını veto moduna alma (veya gölge kayıt)

**Bağlam:** Zenginleştirilen 6 sembol karma skorla, diğer 54 sembol saf teknik
skorla yarışıyor — aynı eşiğe farklı cetvellerle giriyorlar. Teknik 1. sıradaki
hisse vasat temellerle eşiğin altına itilirken 7. sıradaki saf teknikle
geçebiliyor. Ayrıca temel katman (%35 ağırlık) hiç backtest edilmedi.

**Yapılacak:**
- `strategy.yaml`'a mod anahtarı ekle: `fundamental.mode: blend | veto`
  (mevcut davranış `blend`, geriye uyumlu).
- `veto` modu: nihai skor = saf teknik skor. Temel veriler yalnızca şu
  durumlarda BUY'ı HOLD'a düşürür (eşikler config'te): şirket zarar ediyor VE
  kazançlar daralıyor; iki haber kaynağı da belirgin negatif; içeriden yoğun
  net satış. Aksi halde dokunmaz. Notlar Slack'te aynen gösterilmeye devam
  eder.
- Her iki modda da GÖLGE KAYIT: her koşuda hem saf-teknik kararı hem karma/veto
  kararı Sheets'e ayrı kolonlara logla. Amaç: birkaç ay sonra iki mantığın
  ayrıştığı vakaları gerçek sonuçlarla karşılaştırabilmek (temel katmanın
  point-in-time backtest'i yapılamadığı için bu, elimizdeki en iyi doğrulama).

**Kabul kriteri:** Veto modu testli ve çalışıyor; her günlük koşuda iki
kararın da kaydı düşüyor; hangi modun aktif olduğu Slack mesajında görünüyor.

---

### Görev 3.2 — Dönüşümlü temel tarama (tüm evreni kapsa)

**Bağlam:** Alpha Vantage 25 istek/gün limiti yüzünden koşu başına yalnızca en
güçlü 6 aday zenginleştiriliyor; temeli güçlü ama teknik olarak 10. sıradaki
hisse asla görülemiyor. Oysa temel veriler günlük değişmez — haftalık tazelik
yeterlidir.

**Yapılacak:**
- Günlük koşuya "dönüşümlü tarama" ekle: her gün evrenden sıradaki ~8-10
  sembolün temel verisi çekilip mevcut TTL disk cache'ine yazılır (TTL ~7 gün).
  6-7 günde tüm 60 sembol dönmüş olur. Günlük bütçe: dönüşümlü tarama + o günün
  en güçlü adayları toplamda 25 isteği aşmayacak şekilde önceliklendirilir
  (adaylar öncelikli; artan kota dönüşüme).
- Sinyal motoru temel skoru artık "o gün çekilen" değil "cache'te taze olan"
  veriden okur; veri yaşı (kaç günlük) skor notlarına eklenir.
- GitHub Actions ortamında cache kalıcılığı için `actions/cache` veya
  Sheets/artefakt tabanlı bir kalıcı depolama kur — aksi halde her koşu sıfır
  cache ile başlar ve dönüşüm işe yaramaz. (Bu altyapı detayı görevin parçası.)

**Kabul kriteri:** 7 günlük pencere içinde 60 sembolün tamamının temel verisi
cache'te; günlük API isteği ≤25; veri yaşı loglanıyor.

---

### Görev 3.3 — R/R kapısını gerçek bir filtreye dönüştür (veya dürüstçe etiketle)

**Bağlam:** Hedef1 (60 günlük zirve) ve stop (ATR+destek) aynı fiyat
geometrisinden türediği için R/R≥1.0 neredeyse totolojik sağlanıyor; kapı
backtest'te hiç tetiklenmiyor. Hiç tetiklenmeyen kapı test edilmemiş kapıdır.

**Yapılacak:**
- Backtest'e R/R eşik taraması ekle: 1.0 / 1.25 / 1.5 / 2.0 değerleriyle koş
  (2016-2026, Görev 1.2 altyapısıyla), her eşikte kaç BUY elendi + performans
  etkisi raporla.
- Sonuca göre: anlamlı bir eşik varsa `min_risk_reward`'ı ona çek; hiçbir eşik
  değer katmıyorsa kapıyı koru ama kod yorumunda ve README'de "aktif filtre
  değil, uç durum sigortası" olarak etiketle (yanlış güven vermesin).

**Kabul kriteri:** Eşik taraması raporu üretildi; config değeri veya
dokümantasyon bulguya göre güncellendi.

---

### Görev 3.4 — Stop / hedef / ufuk tutarlılığı

**Bağlam:** %20 pozisyon stop'u, 3 aylık %6.5 hedefle tutarsız: tek stop-out
portföyden ~%2.5-4 götürür, iki stop-out çeyrek hedefini fiilen siler. Ayrıca
yüksek-vol ve radar-altı sepetleri büyük ölçüde aynı AI/yarı iletken makro
riskine maruz — korelasyonlu pozisyonlar aynı anda stop'a yürüyebilir.

**Yapılacak:**
- `strategy.yaml`'da stop'u sepet bazında yapılandırılabilir yap:
  `risk.position_stop_loss_pct: {low_vol: X, high_vol: Y, radar: Z}` — ve/veya
  ATR tabanlı seçenek (`stop_mode: fixed_pct | atr`, örn. 2.5×ATR).
- Backtest'te (2016-2026) stop taraması: %10 / %12 / %15 / %20, sabit vs ATR
  tabanlı — getiri, maks. düşüş, stop-out sayısı raporla. Karar kullanıcıya
  bırakılır; görevin çıktısı karar verdirecek tablodur.
- Portföy seviyesi otomatik durdurma İSTENMİYOR (bilinçli tercih) — bunun
  yerine Slack'e bilgilendirme ekle: mevcut pozisyonların toplam açık
  kar/zararı (Sheets giriş fiyatlarına göre) her koşuda raporlansın; toplam
  düşüş config'teki uyarı eşiğini (örn. %8) aşarsa mesaj vurgulu uyarı içersin.
  Karar yine kullanıcının.

**Kabul kriteri:** Stop yapılandırması sepet bazında/ATR'li çalışıyor ve
testli; stop taraması raporu üretildi; portföy açık K/Z ve uyarı eşiği Slack
mesajında.

---

### Görev 3.5 — Tema/korelasyon yoğunlaşma raporu

**Bağlam:** 6 pozisyon "bağımsız" varsayılıyor ama sepetler arası tema
çakışması var (AI/yarı iletken). Otomatik engelleme istenmiyor; görünürlük
isteniyor.

**Yapılacak:**
- Sembol listesine (`strategy.yaml` veya ayrı bir `universe.yaml`) her sembol
  için `theme` etiketi ekle (semis_ai, biotech, defense, space, nuclear,
  defensive, energy_storage, robotics...).
- Günlük koşuda: mevcut pozisyonlar + o günkü BUY adayları için tema dağılımı
  hesapla. Aynı temada pozisyon+aday sayısı config eşiğini (örn. 3) aşarsa
  Slack'te "⚠️ Tema yoğunlaşması: semis_ai ×3" uyarısı.
- Ek (opsiyonel, ucuz): pozisyonların son 90 günlük getiri korelasyon matrisini
  hesapla; 0.7 üzeri çiftleri uyarıda listele.

**Kabul kriteri:** Tema etiketleri tam (60/60); yoğunlaşma uyarısı testli;
Slack mesajında görünüyor.

---

## FAZ 4 — Operasyonel güvenlik ve ileriye dönük ölçüm

### Görev 4.1 — Sheets mutabakat uyarısı (unutulan pozisyon)

**Bağlam:** Pozisyonlar sekmesi tamamen manuel; kullanıcı bir alımı girmeyi
unutursa o pozisyon için stop-loss ve SELL sessizce devre dışı kalıyor.

**Yapılacak:**
- Her koşuda: son N gün (config, örn. 5) içinde üretilmiş BUY sinyalleri ile
  Pozisyonlar sekmesini karşılaştır. BUY verilmiş ama pozisyon girilmemiş
  semboller için Slack'te hatırlatma: "3 gün önce X için BUY üretildi,
  Pozisyonlar'da kaydı yok — aldıysan gir, almadıysan yoksay."
- Tersi kontrol: Pozisyonlar'da olup evrende/sinyal geçmişinde hiç olmayan
  sembol varsa (yazım hatası ihtimali) uyar.

**Kabul kriteri:** İki yönlü mutabakat testli; uyarılar Slack'te; N config'te.

---

### Görev 4.2 — Sinyal karnesi (ileriye dönük performans kaydı)

**Bağlam:** Sistemin gerçek out-of-sample kanıtı ancak canlı sinyallerin
ileriye dönük sonuçlarıyla oluşur. Şu an sinyaller loglanıyor ama sonuçları
ölçülmüyor.

**Yapılacak:**
- Sheets'e "Karne" sekmesi: her BUY/SELL sinyali için sinyal tarihi, sinyal
  fiyatı ve +5 / +20 / +60 işlem günü sonraki fiyat + getiri kolonları.
- Günlük koşunun sonuna doldurma adımı ekle: vadesi gelmiş boş hücreleri
  yfinance'ten tamamla (ertesi-gün-açılış referanslı, Görev 2.1 ile tutarlı).
- Aylık özet: BUY sinyallerinin ortalama 20 günlük getirisi vs SPY aynı dönem;
  gölge kayıttaki saf-teknik vs karma/veto kararlarının karşılaştırması
  (Görev 3.1 ile birleşir). Slack'e ayda bir özet mesaj.

**Kabul kriteri:** Karne otomatik doluyor; aylık özet üretiliyor; hiçbir adım
manuel değil.

---

### Görev 4.3 — İçeriden işlem sinyalinin gürültüsünü azalt

**Bağlam:** İçeriden satışların büyük kısmı planlı (10b5-1) satıştır ve bilgi
içermez; ham net alım/satım skoru gürültülü.

**Yapılacak:**
- Finnhub insider-transactions yanıtında işlem kodu/plan bilgisi alanı var mı
  denetle. Varsa planlı satışları skordan düş veya ağırlığını kır.
- Yoksa: "içeriden net satış" bileşeninin skor ağırlığını düşür (config'te),
  alımlara satışlardan daha yüksek ağırlık ver (alımlar bilgi açısından daha
  anlamlıdır — insanlar birçok sebeple satar, tek sebeple alır). Not olarak
  gösterilmeye devam etsin.

**Kabul kriteri:** Asimetrik ağırlık config'te; davranış testli; README'de
gerekçesi bir cümleyle açıklanmış.

---

### Görev 4.4 — Kağıt üzerinde takip dönemi (süreç, kod değil)

**Bağlam:** Bot hiç gerçek alım-satım döngüsünden geçmedi. Gerçek para
öncesinde 1-3 aylık, sinyallerin karne (Görev 4.2) üzerinden izlendiği bir
kağıt dönemi tanımlanmalı.

**Yapılacak:**
- README'ye "Devreye alma kriterleri" bölümü ekle: kağıt döneminin süresi,
  başarı ölçütü (örn. 20 günlük sinyal getirisi ≥ SPY, maks. tekil sinyal
  kaybı eşiği), dönem sonunda gerçek paraya en alt bütçeyle geçiş kuralı.
  Kriterler kullanıcıyla birlikte netleştirilecek — Claude Code bu bölümü
  taslak olarak yazsın, kesinleştirmeyi kullanıcıya bıraksın.

**Kabul kriteri:** README'de ölçülebilir devreye alma kriterleri taslağı var.

---

## Faz-dışı not: Evren önyargısı (tam çözümü kapsam dışı)

Survivorship/hindsight bias'ın tam çözümü, tarihsel S&P 500 bileşen listeleri
gibi point-in-time bir evrenle backtest gerektirir — bu ağır bir iş ve ücretsiz
kaynaklarla zor. Şimdilik yapılacak: (1) Görev 1.1'in benchmark kıyası bu
önyargının etkisini büyük ölçüde görünür kılar (evren şişkinse benchmark da
şişer, alfa doğru ölçülür); (2) README'nin sınırlamalar bölümüne bu önyargı
açıkça yazılsın; (3) radar-altı listesinin elle seçildiği ve otomatik
güncellenmediği aynı bölümde belirtilsin.

## Önerilen çalışma sırası (özet)

1.1 → 1.2 → 1.3 (tam gün, sonuçları OKU ve değerlendir — sonraki fazların
önceliği bu sonuçlara göre değişebilir) → 2.1 → 2.2 → 3.1 → 3.3 → 3.4 → 3.2 →
3.5 → 4.1 → 4.2 → 4.3 → 4.4
