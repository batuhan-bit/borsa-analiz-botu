"""v1 eşik motoru — EMEKLİ (Faz C canlı geçişi). Hiçbir çalıştırma yolundan çağrılmaz.

Faz B doğrulama sürecinin sonucu bağlayıcıdır: günlük eşik-tetiklemeli BUY/SELL/HOLD
motoru, R/R kapısı ve %20 stop mantığı canlı akıştan ÇIKARILDI; yerini v2 kesitsel
momentum rotasyonu (bot.rotation.live + bot.main) aldı.

Bu kod SİLİNMEDİ (iş listesi kuralı): araştırma/karşılaştırma için korunur ve hâlâ
`backtest/backtest.py` (v1 araştırma aracı) ile ilgili testlerce kullanılır. Bu paket
yalnız o retire edilmiş parçalara isimlendirilmiş, tek bir erişim noktası verir —
"bunlar v1'in emekli parçaları; canlı yol bunları çağırmaz" demenin açık yoludur.

Canlı akışa YENİDEN bağlanması dönem-ayrımı disiplinine (CLAUDE.md) tabidir:
parametreleri kanıtlanmamıştır ve v2'nin doğrulanmış kazananıyla yarıştırılmadan
canlıya alınamaz.
"""
from __future__ import annotations

from ..risk.risk_manager import check_stop_loss
from ..signals.engine import SignalEngine

__all__ = ["SignalEngine", "check_stop_loss"]
