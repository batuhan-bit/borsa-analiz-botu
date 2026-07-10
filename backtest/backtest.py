"""Backtesting scripti — stratejiyi son 3 yıllık veriyle doğrular.

Aynı sinyal motoru mantığını geçmiş veri üzerinde gün gün çalıştırır,
pozisyon bazlı %20 stop-loss'u uygular ve portföy getirisini raporlar.
Amaç: 3 aylık %15 hedefinin geçmiş piyasa döngülerinde ne kadar
gerçekçi olduğunu görmek.

Kullanım:
    python -m backtest.backtest
"""
from __future__ import annotations

from bot.config import Settings  # noqa: F401 (adım 4'te kullanılacak)


def run_backtest(settings=None) -> dict:
    """Backtest çalıştır ve özet metrik sözlüğü döndür.

    Metrikler: toplam getiri, yıllık getiri, max drawdown, kazanma oranı,
    Sharpe (yaklaşık), işlem sayısı.
    """
    raise NotImplementedError("Adım 4'te doldurulacak")


if __name__ == "__main__":
    print(run_backtest())
