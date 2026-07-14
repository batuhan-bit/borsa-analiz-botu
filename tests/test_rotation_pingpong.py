"""Regresyon: POWL 2016-06 ping-pong deseni (teşhis: results/diag_1923_trades.md).

Teşhiste POWL art arda günlerde ranking_collapse ile kapanıp ertesi gün slot
doldurmayla yeniden açılıyordu (177 round-trip; 2016-2019 toplam 1923 işlemin
çoğu bu tür churn'dü). İki kök neden ve iki koruma:

  (A) Taban uyuşmazlığı: eski çöküş testi KÜRESEL sırayı (2×top_n = 12/60)
      kullanırken portföy/slot SEPET-İÇİ sıraya göre işliyordu. Taban hizalanınca
      (per_basket'te sepet-içi) meşru tutulan bir pozisyon artık her gün 'çökmüş'
      sayılmaz — churn'ün asıl kaynağı kapanır.
  (B) Ani toparlanma + anında yeniden alım: bir sembol çökse bile ertesi gün
      sırası toparlanınca hemen geri alınabiliyordu. Cooldown, uyarıyla kapanan
      sembolü N işlem günü aday havuzundan dışlayarak günlük aç-kapa döngüsünü
      YAPISAL olarak imkânsız kılar.

Testler ORTAK modülleri (RankingCollapseTracker + AlertCooldown + slot_candidates)
backtest'in alert-günü mantığıyla (alert_orders) aynı sırada sürer.
"""
from __future__ import annotations

from bot.config import Strategy
from bot.rotation.alerts import (
    AlertCooldown,
    RankingCollapseTracker,
    collapse_rank_map,
)
from bot.rotation.slots import slot_candidates

# under_radar sepetinden 6 sembol — HEPSİ farklı tema (tema-kapısı testi karıştırmasın).
# (universe.yaml: IONQ=quantum, RKLB=space, OKLO=nuclear, KTOS=defense,
#  CELH=consumer_growth, POWL=energy_infrastructure — hepsi under_radar.)
UR6 = ["IONQ", "RKLB", "OKLO", "KTOS", "CELH", "POWL"]


def _strategy() -> Strategy:
    s = Strategy.load()
    s.raw.setdefault("rotation", {}).update(selection="per_basket")
    sa = s.raw.setdefault("sell_alerts", {})
    sa["ranking_collapse_multiple"] = 2      # cutoff = 2×positions_per_basket = 4
    sa["ranking_collapse_persist_days"] = 3
    sa["slot_refill_cooldown_days"] = 5
    return s


def _ranking(symbols: list[str]):
    """Sıralı sembol listesini azalan skorlu (symbol, skor) listesine çevir."""
    return [(s, 1.0 - i * 0.001) for i, s in enumerate(symbols)]


def test_base_alignment_prevents_false_collapse_of_held_position():
    """(A) POWL sepet-içi #2 ama küresel sıra 12 dışı: taban-hizalı testte ÇÖKMEZ."""
    strat = _strategy()
    others = [s for s in strat.universe_symbols
              if strat.basket_of(s) in ("low_volatility", "high_volatility")][:12]
    ranking = _ranking(others + ["IONQ", "POWL", "RKLB"])
    # Eski KÜRESEL taban POWL'u 12 dışında görürdü (her gün 'çöküş' — churn kaynağı):
    g = _strategy()
    g.raw["rotation"]["selection"] = "global_top_n"
    g.raw["rotation"]["top_n"] = 6
    assert collapse_rank_map(g, ranking)["POWL"] > 12
    # Taban-hizalı (per_basket) test ise POWL'u sepet-içi #2 görür (<= cutoff 4):
    assert collapse_rank_map(strat, ranking)["POWL"] == 2
    tr = RankingCollapseTracker(strat)               # persist 3
    held = ["IONQ", "POWL"]
    collapsed: set[str] = set()
    for _ in range(6):                               # 6 gün üst üste
        collapsed |= tr.update(ranking, held)
    assert "POWL" not in collapsed                   # meşru pozisyon HİÇ çökmez


def test_powl_pattern_at_most_one_exit_and_cooldown_blocks_reopen():
    """(B) Aynı desen → en fazla BİR çıkış; toparlanma olsa da yeniden açılma cooldown'a takılır."""
    strat = _strategy()
    subject = "POWL"                                 # under_radar, benzersiz tema
    tr = RankingCollapseTracker(strat)               # persist 3
    cd = AlertCooldown(strat)                        # cooldown 5
    weak = _ranking(UR6)                             # POWL sepet-içi #6 (>4) -> çökecek
    strong = _ranking([subject] + [s for s in UR6 if s != subject])  # POWL sepet-içi #1

    held = ["IONQ", subject]                         # per_basket: under_radar 2 pozisyon
    exits = 0
    day = 0
    # Zayıf günler: kalıcılık dolana dek satış YOK; 3. günde TEK çıkış.
    for _ in range(3):
        collapsed = tr.update(weak, held)
        if subject in collapsed:
            exits += 1
            cd.register(subject, day)                # uyarıyla kapandı -> cooldown
            held = ["IONQ"]                          # slot boşaldı
        day += 1
    assert exits == 1                                # günde bir değil; kalıcılık -> tek çıkış
    # POWL day=2'de kapandı: release = 2 + 5 = 7. day 3..6 boyunca aday OLAMAZ.
    reopened: list[int] = []
    while day < 7:
        blocked = cd.blocked(day)
        cand_syms = [c.symbol for c in slot_candidates(strat, held, strong, excluded=blocked)]
        if subject in cand_syms:                     # cooldown olmasa POWL en iyi aday olurdu
            reopened.append(day)
        day += 1
    assert reopened == []                            # cooldown süresince hiç yeniden açılmadı
    # Cooldown dolunca (day 7) yapısal engel kalkar — normal aday havuzuna döner.
    blocked = cd.blocked(7)
    back = [c.symbol for c in slot_candidates(strat, held, strong, excluded=blocked)]
    assert subject in back


def test_without_cooldown_powl_would_reopen_immediately():
    """Kontrast: cooldown OLMASAYDI POWL toparlanınca aynı gün yeniden aday olurdu."""
    strat = _strategy()
    subject = "POWL"
    strong = _ranking([subject] + [s for s in UR6 if s != subject])
    held = ["IONQ"]                                  # POWL az önce satıldı, slot boş
    # excluded boş (cooldown yok) -> POWL sepet-içi #1, hemen en iyi aday:
    cand_syms = [c.symbol for c in slot_candidates(strat, held, strong, excluded=[])]
    assert subject in cand_syms                      # işte engellenmesi gereken aç-kapa
