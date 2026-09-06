"""
Crypto Scalping Strategies Registry
Contains all 5 active crypto scalping strategies.
"""
from __future__ import annotations

from app.crypto_scalp.base import CryptoScalpStrategy
from app.crypto_scalp.strategies.vwap_bounce import VWAPBounceStrategy
from app.crypto_scalp.strategies.ema_cross_scalp import EMACrossScalpStrategy
from app.crypto_scalp.strategies.funding_squeeze import FundingSqueezeStrategy
from app.crypto_scalp.strategies.breakout_volume import BreakoutVolumeStrategy
from app.crypto_scalp.strategies.depth_flip import DepthFlipStrategy

CRYPTO_SCALP_STRATEGIES: dict[str, CryptoScalpStrategy] = {
    "VWAP_BOUNCE": VWAPBounceStrategy(),
    "EMA_CROSS_SCALP": EMACrossScalpStrategy(),
    "FUNDING_SQUEEZE": FundingSqueezeStrategy(),
    "BREAKOUT_VOLUME": BreakoutVolumeStrategy(),
    "DEPTH_FLIP": DepthFlipStrategy(),
}

__all__ = [
    "CRYPTO_SCALP_STRATEGIES",
    "VWAPBounceStrategy",
    "EMACrossScalpStrategy",
    "FundingSqueezeStrategy",
    "BreakoutVolumeStrategy",
    "DepthFlipStrategy",
]
