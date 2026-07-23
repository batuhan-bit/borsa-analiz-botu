"""Slack Incoming Webhook bildirimi — v2 rotasyon akışı (Görev C.1).

Günde 1 kez, piyasa kapanışı sonrası üretilen ROTASYON kararını (bot.rotation.live
.LiveDecision) okunabilir bir Slack mesajına (Block Kit) çevirir. v1 eşik-tetiklemeli
BUY/SELL/HOLD biçimi TAMAMEN kaldırılmıştır — bu mesajda v1 sinyali görünmez.

Mesaj yapısı:
  - Başlık + özet (rotasyon günü mü, kaç satış uyarısı, kaç aday)
  - Rotasyon günü: 🟢 giren (💰 tutar/adet) · 🔴 çıkan (gerekçe) · ⚪ kalan · rebalans
  - Her gün: 🚨 satış uyarıları · (rotasyon-dışı) slot doldurma · 📊 günlük gözlem
  - Manuel icra hatırlatması

format_message ağdan bağımsız test edilebilir (snapshot); send yalnızca POST yapar.
"""
from __future__ import annotations

import logging

import requests

from ..rotation.live import (
    BuySuggestion,
    ExitSuggestion,
    LiveDecision,
    RebalanceNote,
)
from ..rotation.slots import render_observation_lines

log = logging.getLogger(__name__)

# Block Kit sınırları
_MAX_SECTION_CHARS = 2900   # section text limiti 3000; güvenli marj
_MAX_BLOCKS = 48            # limit 50; başlık/özet için pay bırak

_BASKET_LABEL = {
    "low_volatility": "Düşük Vol",
    "high_volatility": "Yüksek Vol",
    "under_radar": "Radar Altı",
}

_MANUAL_REMINDER = "ℹ️ Bu öneriler bilgi amaçlıdır; alım-satımı kendiniz yürütürsünüz. Karar sizindir."


def _basket_label(value) -> str:
    return _BASKET_LABEL.get(value, value or "—")


def _rank_str(rank) -> str:
    return f"#{rank}" if rank is not None else "#—"


def _buy_line(b: BuySuggestion) -> str:
    return (
        f"🟢 *{b.symbol}* — 💰 {b.shares:g} adet ≈ ${b.value:,.2f} @ ${b.price:,.2f}  "
        f"_(sıra {_rank_str(b.rank)}, {_basket_label(b.basket)})_\n"
        f"      {b.reason}"
    )


def _exit_line(e: ExitSuggestion) -> str:
    return f"🔴 *{e.symbol}*  _({_basket_label(e.basket)})_\n      {e.reason}"


def _rebalance_line(r: RebalanceNote) -> str:
    arrow = "↑ ekle" if r.action == "ekle" else "↓ azalt"
    return (
        f"⚖️ *{r.symbol}*: {arrow} — güncel %{r.current_weight * 100:.0f} → "
        f"hedef %{r.target_weight * 100:.0f} (sapma %{r.drift_pct:g})"
    )


def _alert_line(alert) -> str:
    reasons = "\n      ".join(f"• {t.reason}" for t in alert.triggers)
    head = f"🚨 *{alert.symbol}* (sıra {_rank_str(alert.current_rank)})"
    return f"{head}\n      {reasons}"


def _pct(v) -> str:
    return f"%{v:+.2f}" if v is not None else "—"


def _monthly_summary_lines(summary) -> list[str]:
    """Aylık özet dict'ini tek satırlık karşılaştırmaya çevir (yoksa boş liste)."""
    if not summary:
        return []
    lb = summary.get("lookback_days", 21)
    return [
        f"Son {lb} işlem günü — 📦 Portföy {_pct(summary.get('portfolio_pct'))} · "
        f"🇺🇸 SPY {_pct(summary.get('spy_pct'))} · "
        f"🌐 Evren al-tut {_pct(summary.get('universe_pct'))}",
        "_Bilgi kolonu: 3 aylık getiri gürültüdür; hüküm 12. ayda (bkz. README)._",
    ]


def _chunk_sections(lines: list[str]) -> list[dict]:
    """Satırları 3000 karakter sınırına uyacak şekilde section bloklarına böl."""
    blocks: list[dict] = []
    buffer = ""
    for line in lines:
        candidate = f"{buffer}\n{line}" if buffer else line
        if len(candidate) > _MAX_SECTION_CHARS:
            if buffer:
                blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": buffer}})
            buffer = line
        else:
            buffer = candidate
    if buffer:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": buffer}})
    return blocks


def _titled_section(blocks: list[dict], title: str, lines: list[str]) -> None:
    if not lines:
        return
    blocks.append({"type": "divider"})
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": title}})
    blocks.extend(_chunk_sections(lines))


class SlackNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def format_message(self, decision: LiveDecision) -> dict:
        """LiveDecision'ı Slack mesaj gövdesine (blocks + fallback text) çevir."""
        day = decision.as_of.isoformat()
        badge = "🔄 ROTASYON GÜNÜ" if decision.is_rotation_day else "👀 İzleme"
        header = f"📊 Günlük Rotasyon — {day}"
        summary = (
            f"{badge} · 🚨 {len(decision.sell_alerts)} satış uyarısı"
        )
        if decision.is_rotation_day:
            summary += (
                f" · 🟢 {len(decision.rotation_entries)} giren"
                f" · 🔴 {len(decision.rotation_exits)} çıkan"
            )
        else:
            summary += f" · 🟢 {len(decision.slot_fills)} slot adayı"

        blocks: list[dict] = [
            {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
        ]

        # --- Sessiz-veri-kaybı uyarısı (EN ÜSTTE) ---
        # Pozisyonlar sekmesinde ayrıştırılamayan satır varsa portföy eksik okunmuştur;
        # bu koşuda öneriler bastırıldı. Kullanıcı bunu ilk satırda görmeli.
        if decision.read_warnings:
            n = len(decision.read_warnings)
            warn_text = (
                f"⚠️ *{n} pozisyon satırı okunamadı* — bu koşunun önerileri EKSİK "
                f"portföyle hesaplandı; rotasyon/slot önerileri bu koşuda bastırıldı.\n"
                + "\n".join(f"• {w}" for w in decision.read_warnings)
            )
            blocks.extend(_chunk_sections([warn_text]))

        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": summary}})

        # --- Satış uyarıları (her gün, en öne) ---
        _titled_section(blocks, "*🚨 SATIŞ UYARILARI*",
                        [_alert_line(a) for a in decision.sell_alerts])

        # --- Rotasyon (yalnız rotasyon günü) ---
        if decision.is_rotation_day:
            _titled_section(blocks, "*🟢 GİREN (önerilen)*",
                            [_buy_line(b) for b in decision.rotation_entries])
            _titled_section(blocks, "*🔴 ÇIKAN (önerilen)*",
                            [_exit_line(e) for e in decision.rotation_exits])
            if decision.rotation_holds:
                blocks.append({"type": "divider"})
                blocks.append({"type": "context", "elements": [{
                    "type": "mrkdwn",
                    "text": f"⚪ *Kalan ({len(decision.rotation_holds)}):* "
                            + ", ".join(decision.rotation_holds),
                }]})
            _titled_section(blocks, "*⚖️ REBALANS (bant dışı)*",
                            [_rebalance_line(r) for r in decision.rebalance_notes])
        else:
            # --- Slot doldurma (rotasyon-dışı gün) ---
            _titled_section(blocks, "*🟢 SLOT DOLDURMA ADAYLARI*",
                            [_buy_line(b) for b in decision.slot_fills])

        # --- Aylık özet (portföy vs SPY vs evren al-tut) — varsa ---
        summary_block = _monthly_summary_lines(decision.monthly_summary)
        if summary_block:
            _titled_section(blocks, "*🏁 AYLIK KARNE*", summary_block)

        # --- Günlük gözlem (eylemsiz) ---
        if decision.observation is not None:
            obs_lines = render_observation_lines(decision.observation, basket_label=_basket_label)
            if len(obs_lines) > 2:      # başlık + disclaimer'dan fazlası varsa
                blocks.append({"type": "divider"})
                blocks.extend(_chunk_sections(obs_lines))

        # --- Manuel icra hatırlatması ---
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _MANUAL_REMINDER}]})

        # Blok sınırını aşarsak kırp
        if len(blocks) > _MAX_BLOCKS:
            blocks = blocks[:_MAX_BLOCKS]
            blocks.append({"type": "context", "elements": [
                {"type": "mrkdwn", "text": "… (mesaj kısaltıldı)"}]})

        return {"text": f"{header} — {summary}", "blocks": blocks}

    def send(self, decision: LiveDecision) -> None:
        """Rotasyon kararını Slack webhook'una gönder."""
        if not self._webhook_url:
            log.warning("SLACK_WEBHOOK_URL boş — bildirim atlanıyor.")
            return
        payload = self.format_message(decision)
        resp = requests.post(self._webhook_url, json=payload, timeout=30)
        if resp.status_code != 200 or resp.text.strip().lower() != "ok":
            raise RuntimeError(f"Slack gönderimi başarısız: {resp.status_code} {resp.text[:200]}")
        log.info("Slack rotasyon bildirimi gönderildi (%s).", decision.as_of.isoformat())
