"""
Paper Execution Provider for Crypto Scalping
Calculates realistic exchange execution friction: bid/ask spread, adverse slippage,
and taker exchange fees to eliminate paper trading over-optimism.
"""
from __future__ import annotations

from dataclasses import dataclass
from app.models.crypto import SignalDirection
from app.crypto_scalp.models_execution import CryptoScalpExecutionConfig


@dataclass
class PaperFillResult:
    observed_market_price: float
    spread_usd: float
    slippage_usd: float
    fill_price: float
    fee_usd: float
    notional_usd: float


class PaperExecutionProvider:
    """Simulates realistic exchange fill mechanics for 24/7 crypto micro-scalps."""

    def __init__(self, config: CryptoScalpExecutionConfig | None = None):
        self.config = config or CryptoScalpExecutionConfig()

    def calculate_fill(
        self,
        market_price: float,
        direction: SignalDirection,
        is_entry: bool,
        quantity: float,
        spread: float = 0.0,
    ) -> PaperFillResult:
        """
        Calculate realistic execution fill accounting for half-spread and adverse slippage.
        """
        half_spread = max(0.0, spread / 2.0)
        slippage_bps = self.config.entry_slippage_bps if is_entry else self.config.exit_slippage_bps
        slippage_factor = slippage_bps / 10_000.0

        if direction == SignalDirection.LONG:
            if is_entry:
                # Long entry fills on the Ask + adverse upward slippage
                base_p = market_price + half_spread
                slip_p = base_p * slippage_factor
                fill_p = base_p + slip_p
            else:
                # Long exit fills on the Bid - adverse downward slippage
                base_p = max(0.0001, market_price - half_spread)
                slip_p = base_p * slippage_factor
                fill_p = max(0.0001, base_p - slip_p)
        else:
            if is_entry:
                # Short entry fills on the Bid - adverse downward slippage
                base_p = max(0.0001, market_price - half_spread)
                slip_p = base_p * slippage_factor
                fill_p = max(0.0001, base_p - slip_p)
            else:
                # Short exit fills on the Ask + adverse upward slippage
                base_p = market_price + half_spread
                slip_p = base_p * slippage_factor
                fill_p = base_p + slip_p

        notional = quantity * fill_p
        fee = notional * (self.config.taker_fee_bps / 10_000.0)
        slippage_usd = quantity * slip_p

        return PaperFillResult(
            observed_market_price=round(market_price, 4),
            spread_usd=round(quantity * half_spread, 4),
            slippage_usd=round(slippage_usd, 4),
            fill_price=round(fill_p, 4 if fill_p < 10 else 2),
            fee_usd=round(fee, 4),
            notional_usd=round(notional, 2),
        )

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
    ) -> tuple[float, float, float]:
        """
        Calculate risk-based position size so every scalp risks exactly configured % of equity.
        Returns: (quantity, notional_usd, risk_amount_usd).
        """
        risk_amount = self.config.account_equity * (self.config.risk_per_trade_pct / 100.0)
        stop_distance = max(0.0001, abs(entry_price - stop_loss))
        quantity = risk_amount / stop_distance
        notional = quantity * entry_price

        # Standard crypto precision
        qty_precision = 4 if "BTC" in str(entry_price) or entry_price > 1000 else 2
        return (
            round(quantity, qty_precision),
            round(notional, 2),
            round(risk_amount, 2),
        )


paper_execution_provider = PaperExecutionProvider()
