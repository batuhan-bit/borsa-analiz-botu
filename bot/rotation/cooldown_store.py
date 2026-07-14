"""Cooldown durumunun koşular arası kalıcılığı (Görev C.1 — canlı akış).

GitHub Actions stateless: her günlük koşu temiz başlar. Ama satış-uyarısıyla
kapanan sembolün `slot_refill_cooldown_days` (5) işlem günü yeniden seçilememesi
kuralının işlemesi için cooldown durumu koşular arası KALICI olmalı (yoksa aç-kapa
koruması her gün sıfırlanır). Bu modül o durumu saklar/yükler.

TASARIM — tarih çıpalı (window-bağımsız):
  AlertCooldown MONOTON bir tam-sayı `day_index` ile çalışır (backtest: takvim
  konumu). İndeks, çekilen geçmiş penceresinin uzunluğuna bağlıdır → koşular arası
  KARARSIZ. Bu yüzden depo İNDEKS değil UYARI TARİHİ saklar: {sembol: uyarı_tarihi}.
  Her koşu, o günkü gerçek işlem-günü takvimini kurar ve `uyarı_tarihi → indeks`
  çevirisiyle AYNI AlertCooldown nesnesini yeniden kurar (reconstruct_cooldown).
  Böylece canlı akış, backtest'teki "tek AlertCooldown + rank_fn enjeksiyonu"
  desenini BİREBİR izler; yalnız durumun kaynağı bir depo olur.

Depo arka uçları: Sheets (kalıcı, önerilen) veya bellek (test / Sheets kapalı).
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Mapping, Protocol, runtime_checkable

import pandas as pd

from .alerts import AlertCooldown

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Takvim ↔ indeks çevirisi + AlertCooldown yeniden kurulumu
# ---------------------------------------------------------------------------
def _norm(day) -> pd.Timestamp:
    return pd.Timestamp(day).normalize()


def _alert_index(alert_day, calendar: list, index_of: Mapping) -> int | None:
    """Uyarı tarihini takvimdeki işlem-günü indeksine çevir.

    Tam eşleşme yoksa (veri boşluğu/tatil) <= alert_day olan son işlem gününün
    indeksi kullanılır. alert_day takvim başından da önceyse (süresi çoktan
    dolmuş) None döner → yeniden kurulmaz.
    """
    ts = _norm(alert_day)
    hit = index_of.get(ts)
    if hit is not None:
        return hit
    if not calendar or ts < _norm(calendar[0]):
        return None
    pos = 0
    for j, d in enumerate(calendar):
        if _norm(d) <= ts:
            pos = j
        else:
            break
    return pos


def reconstruct_cooldown(strategy, stored: Mapping[str, date], calendar: list) -> AlertCooldown:
    """Kayıtlı {sembol: uyarı_tarihi} durumundan AlertCooldown'ı yeniden kur.

    Her sembol, uyarı tarihinin takvimdeki indeksinde register edilir; canlı akış
    böylece backtest ile aynı AlertCooldown'ı `.blocked(idx)` ile sorgular. Süresi
    dolmuş (takvim başından önceki) kayıtlar atlanır.
    """
    cooldown = AlertCooldown(strategy)
    index_of = {_norm(d): i for i, d in enumerate(calendar)}
    for sym, alert_day in stored.items():
        idx = _alert_index(alert_day, calendar, index_of)
        if idx is not None:
            cooldown.register(sym, idx)
    return cooldown


def active_cooldown_dates(
    cooldown: AlertCooldown,
    stored: Mapping[str, date],
    newly_cooled_today: Iterable[str],
    today: date,
    today_index: int,
) -> dict[str, date]:
    """Bugün itibarıyla HÂLÂ bekleyen sembollerin {sembol: uyarı_tarihi} durumu.

    Depoya yalnız bu küme yazılır (süresi dolanlar düşer, depo küçük kalır).
    Yeni kapananların uyarı tarihi `today`, önceden bekleyenlerinki `stored`'daki
    orijinal tarih. AlertCooldown.blocked upper-case sembol döndürür.
    """
    stored_upper = {s.strip().upper(): v for s, v in stored.items()}
    new_upper = {s.strip().upper() for s in newly_cooled_today}
    out: dict[str, date] = {}
    for sym in cooldown.blocked(today_index):
        if sym in new_upper:
            out[sym] = today
        elif sym in stored_upper:
            out[sym] = stored_upper[sym]
        else:
            out[sym] = today   # emniyet: bloklu ama kaynağı bilinmiyor
    return out


# ---------------------------------------------------------------------------
#  Depo arka uçları
# ---------------------------------------------------------------------------
@runtime_checkable
class CooldownStore(Protocol):
    def load(self) -> dict[str, date]: ...
    def save(self, state: Mapping[str, date]) -> None: ...


class InMemoryCooldownStore:
    """Bellekte cooldown deposu (test / Sheets kapalı) — kalıcı DEĞİL."""

    def __init__(self, initial: Mapping[str, date] | None = None) -> None:
        self._state: dict[str, date] = dict(initial or {})

    def load(self) -> dict[str, date]:
        return dict(self._state)

    def save(self, state: Mapping[str, date]) -> None:
        self._state = dict(state)


class SheetsCooldownStore:
    """Google Sheets 'Cooldown' sekmesinde kalıcı cooldown deposu.

    SheetsLogger devre dışıysa (kimlik/ID yok) load boş döner, save no-op olur —
    tüm diğer Sheets özellikleriyle aynı zarif düşüş. Bu durumda cooldown yalnız
    o koşu içinde geçerli olur (kalıcılık kaybolur; akış çökmez).
    """

    def __init__(self, sheets_logger, cooldown_days: int) -> None:
        self._sheets = sheets_logger
        self._cd = int(cooldown_days)

    def load(self) -> dict[str, date]:
        raw = self._sheets.read_cooldown_state()
        out: dict[str, date] = {}
        for sym, iso in raw.items():
            try:
                out[str(sym).strip().upper()] = date.fromisoformat(str(iso)[:10])
            except (ValueError, TypeError):
                log.warning("Cooldown satırı okunamadı: %s=%s (atlandı).", sym, iso)
        return out

    def save(self, state: Mapping[str, date]) -> None:
        self._sheets.write_cooldown_state(state, self._cd)
