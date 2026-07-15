"""Slot doldurma + günlük gözlem (Görev A.4).

İki eylemsiz/yarı-eylemli yardımcı:

  - slot_candidates: portföyde bir satış kapanıp slot boşaldığında, sıralamada
    portföy dışı en yüksek UYGUN adayı önerir (sepet ve tema kısıtlarına saygılı).
    Rotasyon günü beklenmez. Karar kullanıcınındır.
  - daily_observation: Slack mesajının sonuna eklenecek EYLEMSİZ bilgi —
    sıralamada son N günde en çok yükselen ilk-N-dışı semboller + portföydeki
    hisselerin güncel sıraları. Açıkça "bilgi amaçlı, eylem önerisi değildir".

Her ikisi de saf fonksiyondur (sıralama/holdings dışarıdan gelir), test edilebilir.
Canlı akışa (Sheets satış tespiti, takvim) bağlanması Faz C'dedir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from ..config import Strategy


@dataclass(frozen=True)
class SlotCandidate:
    symbol: str
    basket: str | None
    theme: str | None
    rank: int              # evren genelindeki güncel sıra (1 = en yüksek)
    score: float
    reason: str


def _rank_map(ranking: Sequence[tuple[str, float]]) -> dict[str, int]:
    """(symbol, skor) sıralı listesinden symbol -> sıra (1 tabanlı)."""
    return {sym: i for i, (sym, _) in enumerate(ranking, start=1)}


def slot_candidates(
    strategy: Strategy,
    holdings: Iterable[str],
    ranking: Sequence[tuple[str, float]],
    *,
    excluded: Iterable[str] = (),
) -> list[SlotCandidate]:
    """Boşalan slotlar için portföy dışı en yüksek uygun adayları öner.

    holdings: portföydeki açık pozisyon sembolleri.
    ranking : evren genelinde (symbol, skor) azalan sıralı liste (bir Ranker'dan).
    excluded: bu koşuda aday OLAMAYACAK semboller (ör. AlertCooldown bekleme
              süresindekiler) — uyarıyla yeni kapanan sembolün aynı gün yeniden
              alınmasını (aç-kapa döngüsü) yapısal olarak engeller.
    Kısıtlar seçim moduna göre:
      - per_basket   : her sepet `positions_per_basket` pozisyon tutar; eksik
        sepetin slotları o sepetin en yüksek sıralı, portföy dışı sembolüyle önerilir.
      - global_top_n : toplam `top_n` pozisyon; portföy dışı en yüksek sıralı.
    Her iki modda da tema başına `max_positions_per_theme` sınırına saygı duyulur.
    """
    held = {s.strip().upper() for s in holdings}
    blocked = {s.strip().upper() for s in excluded}
    rot = strategy.rotation
    mode = rot.get("selection", "per_basket")
    max_theme = int(rot.get("max_positions_per_theme", 2))
    rank_pos = _rank_map(ranking)

    # Portföydeki tema dağılımı (tema kapısı için başlangıç sayacı)
    theme_counts: dict[str | None, int] = {}
    for s in held:
        th = strategy.theme_of(s)
        theme_counts[th] = theme_counts.get(th, 0) + 1

    out: list[SlotCandidate] = []

    def _eligible(sym: str) -> bool:
        return (sym.upper() not in held and sym.upper() not in blocked
                and theme_counts.get(strategy.theme_of(sym), 0) < max_theme)

    if mode == "global_top_n":
        top_n = int(rot.get("top_n", 6))
        empty = top_n - len(held)
        if empty <= 0:
            return []
        for sym, score in ranking:
            if len(out) >= empty:
                break
            if not _eligible(sym):
                continue
            th = strategy.theme_of(sym)
            out.append(SlotCandidate(
                symbol=sym, basket=strategy.basket_of(sym), theme=th,
                rank=rank_pos[sym], score=float(score),
                reason=f"boşalan slot adayı (sırada #{rank_pos[sym]})",
            ))
            theme_counts[th] = theme_counts.get(th, 0) + 1
        return out

    # per_basket
    per_basket = int(strategy.portfolio.get("positions_per_basket", 2))
    for name in strategy.baskets:
        held_in_basket = [s for s in held if strategy.basket_of(s) == name]
        empty = per_basket - len(held_in_basket)
        if empty <= 0:
            continue
        filled = 0
        for sym, score in ranking:
            if filled >= empty:
                break
            if strategy.basket_of(sym) != name or not _eligible(sym):
                continue
            th = strategy.theme_of(sym)
            out.append(SlotCandidate(
                symbol=sym, basket=name, theme=th,
                rank=rank_pos[sym], score=float(score),
                reason=f"boşalan {name} slotu için en yüksek uygun aday (sırada #{rank_pos[sym]})",
            ))
            theme_counts[th] = theme_counts.get(th, 0) + 1
            filled += 1
    return out


# ---------------------------------------------------------------------------
#  Günlük gözlem (eylemsiz)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RankMover:
    symbol: str
    old_rank: int
    new_rank: int
    improvement: int       # old_rank - new_rank (pozitif = yükseldi)


@dataclass(frozen=True)
class Observation:
    top_movers: list[RankMover] = field(default_factory=list)
    portfolio_ranks: dict[str, int | None] = field(default_factory=dict)


# Gözlem bölümünde ASLA bulunmaması gereken eylem/imperatif dili (kabul kriteri).
_ACTION_WORDS = ("satın al", "alın", "satın", "ekleyin", "azaltın",
                 "🟢", "🔴", "🚨", "acil satış", "alış sinyal", "satış sinyal")

_OBS_DISCLAIMER = "ℹ️ Bu bölüm bilgi amaçlıdır; eylem önerisi değildir."


def daily_observation(
    rank_now: Mapping[str, int],
    rank_past: Mapping[str, int],
    holdings: Iterable[str],
    *,
    top_n: int,
    max_movers: int = 3,
) -> Observation:
    """Eylemsiz gözlem verisi üret.

    rank_now / rank_past: symbol -> sıra (1 tabanlı), güncel ve N gün önceki.
    Yükselenler: ŞU AN ilk-N DIŞINDA olup son N günde sırası yükselen (improvement>0)
    semboller; en çok yükselen `max_movers` tanesi.
    portfolio_ranks: portföydeki her sembolün güncel sırası (yoksa None).
    """
    movers: list[RankMover] = []
    for sym, new_rank in rank_now.items():
        if new_rank <= top_n:                 # ilk-N içindekiler hariç
            continue
        old_rank = rank_past.get(sym)
        if old_rank is None:
            continue
        improvement = old_rank - new_rank
        if improvement > 0:
            movers.append(RankMover(sym, old_rank, new_rank, improvement))
    movers.sort(key=lambda m: (-m.improvement, m.symbol))

    portfolio_ranks = {s.strip().upper(): rank_now.get(s.strip().upper())
                       for s in holdings}
    return Observation(top_movers=movers[:max_movers], portfolio_ranks=portfolio_ranks)


def render_observation_lines(obs: Observation) -> list[str]:
    """Gözlemi Slack için EYLEMSİZ metin satırlarına çevir (imperatif dil yok)."""
    lines: list[str] = ["*📊 Günlük gözlem*", _OBS_DISCLAIMER]
    if obs.top_movers:
        movers = ", ".join(f"{m.symbol} (#{m.old_rank}→#{m.new_rank})" for m in obs.top_movers)
        lines.append(f"📈 Sırada yükselen (ilk-N dışı): {movers}")
    if obs.portfolio_ranks:
        ranks = ", ".join(
            f"{sym} #{rank if rank is not None else '—'}"
            for sym, rank in obs.portfolio_ranks.items()
        )
        lines.append(f"📌 Portföy sıraları: {ranks}")
    return lines


def has_action_language(lines: Iterable[str]) -> bool:
    """Verilen satırlarda eylem/imperatif dili var mı (gözlem kontrolü)."""
    blob = "\n".join(lines).lower()
    return any(word in blob for word in _ACTION_WORDS)
