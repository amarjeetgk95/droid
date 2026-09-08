"""
Crypto Scalping Risk & Sanity Filter
Validates candidates against strict stop-loss, risk-reward, and confidence thresholds.
"""
from __future__ import annotations

import structlog
from app.crypto_scalp.base import CryptoScalpCandidate
from app.models.crypto import SignalDirection

logger = structlog.get_logger()


class CryptoScalpRiskFilter:
    """Production risk filter for crypto scalping candidates."""

    # Max permissible stop loss distance
    MAX_SL_PCT_MAP: dict[str, float] = {
        "BTCUSDT": 1.5,
        "ETHUSDT": 2.0,
    }
    DEFAULT_MAX_SL_PCT = 2.0

    MIN_RR_RATIO = 1.5
    MIN_CONFIDENCE = 78.0

    def validate(self, candidate: CryptoScalpCandidate) -> tuple[bool, str]:
        """
        Validate whether candidate meets crypto scalping execution standards.
        Returns (is_valid, reason).
        """
        # 1. Price validity checks
        if candidate.entry_price <= 0 or candidate.stop_loss <= 0 or candidate.target_1 <= 0:
            return False, "Prices must be positive numbers"

        if candidate.direction == SignalDirection.LONG:
            if candidate.stop_loss >= candidate.entry_price:
                return False, "Long stop-loss must be below entry price"
            if candidate.target_1 <= candidate.entry_price:
                return False, "Long target must be above entry price"
        elif candidate.direction == SignalDirection.SHORT:
            if candidate.stop_loss <= candidate.entry_price:
                return False, "Short stop-loss must be above entry price"
            if candidate.target_1 >= candidate.entry_price:
                return False, "Short target must be below entry price"

        # 2. Risk percentage check
        max_allowed_sl_pct = self.MAX_SL_PCT_MAP.get(candidate.symbol, self.DEFAULT_MAX_SL_PCT)
        if candidate.risk_percent > max_allowed_sl_pct:
            return False, f"Risk {candidate.risk_percent:.2f}% exceeds maximum allowable ({max_allowed_sl_pct:.2f}%)"

        # 3. Minimum Risk-Reward Ratio
        if candidate.risk_reward_ratio < self.MIN_RR_RATIO:
            return False, f"Risk-Reward {candidate.risk_reward_ratio:.2f} below minimum ({self.MIN_RR_RATIO})"

        # 4. Confidence gate
        if candidate.confidence < self.MIN_CONFIDENCE:
            return False, f"Confidence {candidate.confidence:.1f}% below minimum ({self.MIN_CONFIDENCE}%)"

        return True, "PASSED"


crypto_scalp_risk_filter = CryptoScalpRiskFilter()
