# Slack 💰 Öneri Düzeltmesi — nakit-sınırlı pozisyon önerisi

_Değişiklik: canlı Slack/konsol bildiriminde önerilen tutar artık
`min(hedef ağırlık × özsermaye, serbest nakit)`. Sheets'te NAKİT satırı varken
elde olan nakitten fazlası önerilmez._

## Sorun

Öneri tutarı yalnızca `hedef ağırlık × portföy özsermayesi` idi. Özsermaye,
pozisyon değeri + serbest nakidi içerdiğinden, elde nakit az olsa bile öneri
tam hedef ağırlığı gösterebiliyordu — yani alınamayacak bir tutar önerilebiliyordu.

## Çözüm

`suggested_position`'a keyword-only `free_cash` parametresi eklendi (geriye
uyumlu — mevcut pozisyonel çağrılar bozulmaz):

- `free_cash` verilmişse (Sheets NAKİT satırı var):
  `amount = min(hedef ağırlık × özsermaye, serbest nakit)`.
- `free_cash = None` (nakit satırı yok): eski davranış, sınır uygulanmaz.

Dönüş sözlüğüne iki alan eklendi:
- `target_amount` — cap öncesi asıl hedef tutar.
- `cash_capped` — öneri serbest nakde çekildiyse `True`.

## Değişen dosyalar

| Dosya | Değişiklik |
|---|---|
| `bot/signals/sizing.py` | `suggested_position(..., *, free_cash=None)`; nakit cap'i, `target_amount` + `cash_capped` alanları |
| `bot/main.py` | `_attach_sizing` → `suggested_position`'a `free_cash` geçirir; `_format_sizing` cap durumunu yansıtır |
| `bot/notify/slack.py` | Slack satırı cap durumunu gösterir (`· serbest nakitle sınırlı`) |
| `tests/test_sizing.py` | 4 yeni test (cap, cap yok, nakit<1 hisse, NAKİT satırı yok) |

## Davranış (özsermaye $5000, %20 hedef = $1000, fiyat $100)

| Serbest nakit | Öneri mesajı | Açıklama |
|---|---|---|
| $350 | `~$350 (%20 ağırlık · serbest nakitle sınırlı) → 3 adet ≈ $300` | nakde çekildi |
| $50 | `~$50 hedef (%20 ağırlık) — serbest nakit 1 hisseye yetmiyor, atlanabilir` | 0 adet |
| $5000 (>hedef) | `~$1,000 (%20 ağırlık) → 10 adet ≈ $1,000` | sınır yok |
| NAKİT satırı yok (None) | `~$1,000 (%20 ağırlık) → 10 adet ≈ $1,000` | eski davranış |

## Notlar

- `weight_pct` alanı hedef sepet ağırlığını göstermeye devam eder (bilgi amaçlı);
  cap olduğunda mesaja `serbest nakitle sınırlı` ibaresi eklenir.
- Cap yalnızca serbest nakit **biliniyorken** (NAKİT satırı) uygulanır; canlıda
  `execution: manual` olduğundan öneri bağlayıcı değildir.
- Test durumu: tüm süit **94/94 geçti**.
