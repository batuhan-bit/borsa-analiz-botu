# Sinyal Botu v2 — Aylık Rotasyon İskeleti · İş Listesi

> Bu dosya, v1 doğrulama sürecinin (bkz. `docs/` altındaki raporlar) sonucunda
> alınan kararı uygular: günlük eşik-tetiklemeli BUY/SELL motoru emekli edilir,
> yerine kesitsel momentum rotasyonu kurulur. Bu bir "iyileştirme" değil,
> YENİ BİR HİPOTEZİN SIFIRDAN TESTİDİR — v1'in hiçbir backtest sonucu v2 için
> kanıt sayılmaz.
>
> ## Tasarım kararları (kullanıcıyla mutabık, tartışmasız uygulanır)
> - Aylık portföy rotasyonu; ilk-N portföyü; varsayılan N=6.
> - Ay içi işlem yalnız üç mekanizmayla: kural-bazlı satış uyarısı, satış
>   sonrası slot doldurma adayı, bilgi amaçlı günlük gözlem (eylemsiz).
> - Stop EMRİ yok (icra manuel), ama kural-bazlı satış UYARISI var.
> - Başarı kıstası: yuvarlanan 12 aylık getiri ≥ SPY, maks. düşüş ≤ 1.5×SPY
>   düşüşü; evren al-tut'u bilgi kolonu olarak her raporda gösterilir.
> - Ölçüm katmanı pazarlıksız: pertürbasyon topluluğu, dönem ayrımı disiplini,
>   maliyetler ilk günden, 3 aylık kağıt dönemi.
>
> ## Genel kurallar
> - Çalışma `feature/rotation-v2` dalında; main'e merge insan onayıyla.
> - Parametre ayarı YALNIZ 2016-2019 penceresinde yapılır. 2020-2022 doğrulama
>   penceresidir (aday konfigürasyon başına BİR kez koşulur). 2023-2026'ya
>   Faz B sonundaki nihai rapora kadar HİÇ bakılmaz, o raporda BİR kez koşulur.
>   Bu kural CLAUDE.md'ye de eklenir.
> - Her görev ayrı commit; test suite yeşil kalır; yeni davranış test edilir;
>   tüm ayarlar `strategy.yaml`'da, kodda sabit değer yok.
> - v1 kodu SİLİNMEZ: eşik motoru, R/R kapısı ve %20 stop mantığı
>   `legacy_engine` olarak korunur ama hiçbir çalıştırma yolundan çağrılmaz.
>   Veri katmanı, teknik göstergeler, sizing modülü, cache, Slack/Sheets ve
>   test altyapısı v2'ye taşınır.

---

## FAZ A — Rotasyon motoru

### Görev A.1 — Rotasyon çekirdeği (`bot/rotation/engine.py`)

**Bağlam:** v1'in ölçülemezliğinin kök nedeni eşik + nakit-açlığı yapısıydı.
Rotasyon deterministiktir: aynı veri → aynı portföy.

**Yapılacak:**
- Rotasyon günü (ayın ilk işlem günü, config): evrendeki tüm semboller
  sıralama skoruyla sıralanır, hedef portföy seçilir, mevcut portföyle fark
  ("giren/çıkan/kalan" listesi) üretilir.
- **Birincil seçim modu `per_basket`:** her sepetten skor sırasına göre 2
  hisse; sepet ağırlıkları (%40/35/25) korunur; pozisyon ağırlığı = sepet
  ağırlığı / 2. **Test modu `global_top_n`:** evren genelinde ilk N, eşit
  ağırlık, tema başına en çok 2 pozisyon (tema etiketleri Görev A.4).
- Rebalans: rotasyon günü tüm pozisyonlar hedef ağırlığa çekilir (kalan
  hisselerde de fark %X'i — config, örn. 20 — aşıyorsa ekle/azalt önerisi).
- Config: `rotation: {frequency: monthly, top_n: 6, selection: per_basket,
  rebalance_band_pct: 20}`.

**Kabul kriteri:** Aynı tarih ve veriyle iki koşu birebir aynı portföyü ve
fark listesini üretir (determinizm testi); sizing v2 modülü ağırlıkları
hesaplarken yeniden kullanılır.

---

### Görev A.2 — Sıralama skoru: iki varyant

**Bağlam:** v1 teknik skoru kanıtlanmamıştır; kesitsel momentumun (3-12 aylık
getiri) ise literatürü vardır. İkisi de hipotezdir, yarıştırılır.

**Yapılacak:**
- Varyant S1: mevcut teknik skor (v1'den taşınır, ağırlıklarına DOKUNULMAZ).
- Varyant S2: klasik momentum — son 126 işlem günü getirisi, son 21 gün hariç
  (12-1 momentumun 6 aylık hali; pencereler config'te).
- İkisi de aynı arayüzü uygular (`rank(symbols, date) -> sıralı liste`);
  seçim `rotation.score: s1_technical | s2_momentum`.

**Kabul kriteri:** İki skor da birim testli; Faz B her ikisini koşar.

---

### Görev A.3 — Kural-bazlı satış uyarıları (rotasyon dışı çıkışlar)

**Bağlam:** Stop emri yok; kural-bazlı SELL bildirimi var. v1 dökümü %20
eşiklerin gap'le -%40'a delindiğini gösterdi; kural, karar anını duygudan
arındırmak içindir. Karar her zaman kullanıcının.

**Yapılacak:** Günlük koşuda, portföydeki her pozisyon için üç tetik:
- **Teknik acil durum:** fiyat girişten `atr_exit_multiple` (varsayılan 3.0)
  × ATR aşağıda → SELL uyarısı ("pozisyon tezini kaybetti").
- **Sıralama çöküşü:** hisse güncel sıralamada ilk `2×top_n`'nin de dışına
  düştüyse → SELL uyarısı (ay sonu beklenmez).
- **Temel kırmızı bayrak:** v1 temel katmanı skora DEĞİL yalnız uyarıya
  bağlanır — kazanç çöküşü, zarar+daralma birlikteliği, yoğun içeriden satış
  (asimetrik ağırlık: alım > satım), iki haber kaynağının birlikte belirgin
  negatifliği. Eşikler config'te.
- Uyarı Slack'te vurgulu, tetik gerekçesi ve güncel sıra bilgisiyle gösterilir.

**Kabul kriteri:** Üç tetik ayrı ayrı testli; aynı pozisyon için aynı tetik
günde bir kez bildirilir (spam koruması).

---

### Görev A.4 — Slot doldurma + tema etiketleri + günlük gözlem

**Yapılacak:**
- **Slot doldurma:** Sheets Pozisyonlar'da bir satış kapandığında (veya
  kullanıcı satışı işlediğinde) ertesi koşuda bot, sıralamada portföy dışı en
  yüksek uygun adayı "boşalan slot adayı" olarak bildirir (sepet/tema
  kısıtlarına saygılı). Rotasyon günü beklenmez.
- **Tema etiketleri:** `universe.yaml`'a her sembol için `theme` alanı
  (semis_ai, biotech, defense, space, nuclear, defensive, energy_storage,
  robotics...); `global_top_n` modu ve yoğunlaşma uyarısı bunu kullanır.
- **Günlük gözlem bölümü:** Slack mesajının sonunda, eylemsiz kısa bilgi:
  sıralamada son 5 günde en çok yükselen ilk-N-dışı 3 sembol + portföydekilerin
  güncel sıraları. Açıkça "bilgi amaçlı, eylem önerisi değildir" ibaresiyle.

**Kabul kriteri:** 60/60 sembol tema etiketli; slot adayı kısıtlara uyuyor
(testli); gözlem bölümü eylem dili içermiyor.

---

## FAZ B — Backtest ve ölçüm katmanı

### Görev B.1 — Rotasyon backtest'i

**Yapılacak:**
- `backtest/rotation_backtest.py`: aylık (ve config'le iki haftalık) rotasyonu
  gün gün simüle eder. Dolgu: rotasyon sinyali ayın ilk işlem günü kapanış
  verisiyle, icra ERTESİ işlem günü açılışından. Maliyet: komisyon 5 bps +
  sepet bazlı kayma (`slippage_bps: {low_vol: 5, high_vol: 10, radar: 25}`).
  Temettüler ayarlı seriyle içeride (v1 doğrulaması geçerli).
- Satış-uyarısı tetikleri backtest'te de uygulanır (tetik → ertesi açılışta
  satış + slot doldurma), yoksa canlı davranış test edilmemiş olur.
- Kapsam politikası v1'deki gibi: sembol verisi başladığı gün evrene katılır;
  sepet bazlı kapsam raporu yazılır.

**Kabul kriteri:** Determinizm testi (aynı girdi → aynı sonuç, bit-bazında);
maliyetsiz/maliyetli fark raporlanabilir; işlem listesi dökülebilir
(v1 dökümündeki formatta).

---

### Görev B.2 — Pertürbasyon topluluğu: standart rapor formatı

**Bağlam:** v1'in Δ ayrıştırması tekil backtest rakamının anlamsız olduğunu
kanıtladı. v2'de hiçbir sonuç tekil sayıyla raporlanmaz.

**Yapılacak:**
- Her konfigürasyon 50 koşuluk toplulukla raporlanır: başlangıç tarihi
  ±10 işlem günü (tekdüze) ve kayma ±%50 (çarpansal) oynatılır; rapor medyan +
  [%10, %90] bandı verir. Benchmark'lar (SPY, eşit-ağırlık evren,
  sepet-ağırlıklı evren) aynı pencerelerle yan yana.
- **Tasarım sağlığı ölçütü:** topluluk bandının genişliği raporda ayrıca
  gösterilir. Rotasyon yapısında bant dar olmalıdır; medyan getirinin
  ±%30'undan geniş bant "yol-bağımlılığı geri geldi" uyarısı basar.

**Kabul kriteri:** `python -m backtest.report_v2` tek komutla topluluk
raporunu üretir; hiçbir tabloda bantsız getiri rakamı yok.

---

### Görev B.3 — Konfigürasyon yarışması (dönem ayrımı disipliniyle)

**Yapılacak:** Aşağıdaki ızgara YALNIZ 2016-2019'da koşulur ve karşılaştırılır:
- Skor: S1 vs S2 · Seçim: per_basket vs global_top_n · N: 6 vs 8 ·
  Ritim: aylık vs iki haftalık · Rejim anahtarı (aşağıda): açık vs kapalı.
- **Rejim anahtarı hipotezi:** SPY 200 günlük MA'sının altında kapanırsa
  dağıtım `deployment_pct`'ten `regime_deployment_pct`'e (örn. 50) düşürülür;
  üstüne dönünce normale. v1'in hisse-bazlı trend filtresi başarısızdı; bu
  portföy-bazlı anahtar AYRI bir hipotezdir ve rejim pencereleriyle test edilir.
- 2016-2019'dan EN FAZLA İKİ aday konfigürasyon seçilir (topluluk medyanı +
  bant + rejim davranışı birlikte değerlendirilerek); adaylar 2020-2022'de
  BİRER kez doğrulanır. Doğrulamayı geçen tek konfigürasyon, nihai raporda
  2023-2026'ya BİR kez bakar. Bu akış rapora aynen, tarih sırasıyla yazılır.

**Kabul kriteri:** Rapor üç pencereyi ayrı bölümlerde, hangi kararın hangi
pencereden ÖNCE verildiği okunacak şekilde belgeler. 2020-2022 ve 2023-2026'da
hiçbir parametre değişikliği yapılmadığı commit geçmişiyle doğrulanabilir.

> ⏸ **FAZ B SONUNDA DUR.** Nihai rapor insan değerlendirmesine sunulur.
> Faz C'ye geçiş kararı bu raporun sonucuna bağlıdır: aday konfigürasyon
> doğrulama penceresinde SPY'ı topluluk-medyanında geçemiyorsa, canlıya
> bağlanacak bir şey yoktur — tasarım masasına dönülür.

---

## FAZ C — Canlı entegrasyon (Faz B onayından sonra)

### Görev C.1 — Günlük/aylık akış ve Slack formatı

**Yapılacak:**
- `daily.yml` korunur; içerik değişir: her gün satış-uyarısı taraması + slot
  doldurma + günlük gözlem; ayın ilk işlem günü ek olarak rotasyon önerisi.
- Rotasyon mesajı: giren/çıkan/kalan listesi; her giren için 💰 önerilen
  tutar/adet (sizing modülü, NAKİT satırı sınırı dahil); her çıkan için
  gerekçe (sıra düşüşü); rebalans bandı aşan kalanlar için ekle/azalt notu.
- v1 eşik sinyalleri hiçbir mesajda görünmez.

**Kabul kriteri:** Mesajlar mock verinin üstünde snapshot-testli; rotasyon
günü tespiti (tatil/hafta sonu kayması) testli.

---

### Görev C.2 — Sheets: karne + sistem-dışı işlem etiketi

**Yapılacak:**
- Karne sekmesi (v1 iş listesindeki 4.2): her rotasyon önerisi ve satış
  uyarısı için sinyal tarihi/fiyatı + 5/20/60 işlem günü sonrası getiri
  otomatik doldurulur; aylık özet (portföy vs SPY vs evren al-tut) Slack'e.
- Pozisyonlar sekmesindeki işlemler rotasyon önerileriyle mutabakatlanır
  (v1 4.1): öneriyle eşleşmeyen elle işlemler `sistem-dışı` etiketlenir ve
  karnede ayrı satırda izlenir — 12. ay değerlendirmesinde sistemin ve elin
  katkısı ayrıştırılabilir olmalı.

**Kabul kriteri:** Karne elle müdahalesiz doluyor; sistem-dışı ayrımı testli.

---

## FAZ D — Düşük bütçeli canlı dönem ve devreye alma

### Görev D.1 — README: beklenti ve devreye alma sözleşmesi

**Yapılacak:** README'ye "Beklentiler ve Devreye Alma" bölümü:
- Minimum bağlılık 12 ay; adil değerlendirme 3 yıl; ilk çeyrek gürültüdür.
- Başarı kıstası: yuvarlanan 12 aylık getiri ≥ SPY VE maks. düşüş ≤ 1.5×SPY;
  evren al-tut'u bilgi kolonu. 12. ayda takvimli devam/revize/durdur
  gözden geçirmesi.
- **Düşük bütçeli canlı dönem (kağıt dönemi yerine, kullanıcı kararı):**
  $1,000 başlangıç, 3 ay boyunca nakit girişi yok. Tutar, kullanıcı
  tarafından tamamen kaybedilebilir risk sermayesi olarak tanımlanmıştır.
- **3. ay kapısının ölçütleri OPERASYONELDİR, performans DEĞİLDİR** —
  3 aylık getiri istatistiksel gürültüdür ve nakit-artırma kararına tek
  başına dayanak yapılmaz (README'ye açıkça yazılır). Ölçütler: karne elle
  müdahalesiz doluyor mu; gerçekleşen kayma vs backtest varsayımı (fark
  raporlanır); öneri→icra gecikmesi; sistem-dışı işlem sayısı (hedef 0);
  satış uyarılarının işlerliği; toplam maliyetin dönem getirisine oranı.
  Performans hükmü yalnız 12. ayda, mutabık kıstasla verilir.
- Dürüst beklenti bandı: uzun vadeli hisse ortalaması ~%10/yıl; bu sınıf
  stratejide -%25-35 düşüşler normaldir; %6.5/çeyrek türü hedefler bu ürünün
  vaadi değildir.

**Kabul kriteri:** Bölüm yazıldı; 3. ay operasyonel ölçütleri sayısallaştırılmış
taslak halinde işaretli (kullanıcı onayı bekliyor).

---

### Görev D.2 — Küçük bütçe uyumu ($1,000 gerçeği)

**Bağlam:** $1,000 ile pozisyon hedefi $125-200 bandındadır; tam sayı hisse
kısıtı ve sabit komisyonlar bu ölçekte backtest varsayımlarını geçersiz kılar.
Canlı ve backtest aynı kurallarla çalışmazsa v1'deki asimetri geri gelir.

**Yapılacak:**
- **Broker bilgisi (kullanıcı doğruladı):** kesirli hisse DESTEKLENİYOR →
  `fractional_shares: true`. İşlem başına sabit ücret **$1.50** →
  `commission_fixed_usd: 1.5` (bps kaymaya ek olarak uygulanır).
- Kesirli hisse desteklendiği için fiyat uygunluk kuralı (`max_price_vs_target`)
  ZORUNLU DEĞİL; yine de config'e pasif (null) olarak eklenir — broker değişirse
  tek satırla devreye alınabilsin. Sizing modülü kesirli adet üretir (2 ondalık).
- **Küçük bütçe backtest koşusu:** Faz B'nin kazanan konfigürasyonu $1,000
  başlangıç + `commission_fixed_usd: 1.5` ile ayrı topluluk koşusuna tabi
  tutulur; standart ($3,000+) koşuyla yan yana raporlanır. Dikkat: $1.50,
  ~$167'lik pozisyonda tek yön ~%0.9'dur — bu koşunun amacı tam olarak bu
  ölçek cezasını görünür kılmaktır; rapor, yıllık toplam maliyetin getiriye
  oranını ayrı satırda gösterir.
- Karne, gerçekleşen işlem maliyetlerini ayrıca loglar (kayma kalibrasyonu için).
- Kur/transfer maliyetleri bot kapsamı dışıdır; README'de not edilir.

**Kabul kriteri:** `fractional_shares: true` ve `commission_fixed_usd: 1.5`
config'te; kesirli adet üretimi testli; küçük bütçe topluluk raporu
maliyet/getiri oranı satırıyla üretildi.

---

## Önerilen çalışma sırası

A.1 → A.2 → A.4 (tema etiketleri B için gerekli) → A.3 → B.1 → B.2 → B.3 →
**DUR: insan onayı** → C.1 → C.2 → D.1 → 3 ay kağıt → devreye alma kararı.

Oturum planı önerisi: Faz A tek oturum, Faz B tek oturum (koşular uzun —
raporlar `results/` altına yazılır, ham log context'e alınmaz), Faz C+D tek
oturum. Her oturum sonunda `docs/DURUM.md` güncellenir.
