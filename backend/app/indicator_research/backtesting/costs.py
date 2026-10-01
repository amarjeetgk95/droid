"""Trading cost model (§12).

A backtest without costs is not a backtest, it is a curve-fit. Every result this
module produces therefore carries **both** gross and net figures, and the
difference between them (``cost_drag_pct``) is surfaced in the metrics rather
than buried.

The default numbers are a reference profile for Indian index derivatives. They
are deliberately visible, versioned and overridable, because they are the single
biggest source of over-optimistic research results and the user must be able to
see and replace them:

- ``slippage_bps`` — market impact / spread crossing, applied to the fill price.
  Real fills are worse than the screen; assuming otherwise is the most common
  hidden cost leak in a research platform.
- ``brokerage_bps``, ``exchange_bps``, ``sebi_bps`` — per-side fees, with
  ``gst_on_fees_pct`` charged on those three only (as GST is).
- ``stt_sell_bps`` — securities transaction tax, sell side.
- ``stamp_buy_bps`` — stamp duty, buy side.

These are not promises about any specific broker's contract note. They are a
stated, replaceable assumption, and every result records which cost version
produced it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

COSTS_VERSION = "indicator-research-costs-v1"

Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class CostModel:
    """Per-side cost assumptions, expressed in basis points of notional."""

    version: str = COSTS_VERSION
    slippage_bps: float = 2.0
    brokerage_bps: float = 3.0
    exchange_bps: float = 0.19
    sebi_bps: float = 0.01
    gst_on_fees_pct: float = 18.0
    stt_sell_bps: float = 1.25
    stamp_buy_bps: float = 0.20

    # -- derived -----------------------------------------------------------
    def _fee_bps(self, side: Side) -> float:
        """Fee basis points for one side, excluding slippage."""
        taxable = self.brokerage_bps + self.exchange_bps + self.sebi_bps
        gst_bps = taxable * (self.gst_on_fees_pct / 100.0)
        statutory = self.stt_sell_bps if side == "sell" else self.stamp_buy_bps
        return taxable + gst_bps + statutory

    def buy_bps(self) -> float:
        """Total buy-side cost: slippage plus fees."""
        return self.slippage_bps + self._fee_bps("buy")

    def sell_bps(self) -> float:
        """Total sell-side cost: slippage plus fees."""
        return self.slippage_bps + self._fee_bps("sell")

    def round_trip_bps(self) -> float:
        return self.buy_bps() + self.sell_bps()

    def fill_price(self, price: float, side: Side) -> float:
        """Price after slippage. Buying pays up, selling receives less."""
        if price <= 0:
            return price
        factor = 1.0 + (self.slippage_bps / 10_000.0)
        if side == "buy":
            return price * factor
        return price / factor

    def fee_amount(self, notional: float, side: Side) -> float:
        """Fee (excluding slippage, which is already in the fill) in currency."""
        return abs(notional) * self._fee_bps(side) / 10_000.0

    def transaction_cost(self, entry_notional: float, exit_notional: float) -> float:
        """Total round-trip fee for a completed trade."""
        return self.fee_amount(entry_notional, "buy") + self.fee_amount(exit_notional, "sell")

    def with_overrides(self, **kwargs: Any) -> "CostModel":
        return replace(self, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["buy_bps_total"] = round(self.buy_bps(), 6)
        data["sell_bps_total"] = round(self.sell_bps(), 6)
        data["round_trip_bps_total"] = round(self.round_trip_bps(), 6)
        return data


#: Costs switched off entirely. Useful for isolating signal quality from cost
#: drag — but a strategy that only works at zero cost does not work.
ZERO_COSTS = CostModel(
    version="indicator-research-costs-zero",
    slippage_bps=0.0,
    brokerage_bps=0.0,
    exchange_bps=0.0,
    sebi_bps=0.0,
    gst_on_fees_pct=0.0,
    stt_sell_bps=0.0,
    stamp_buy_bps=0.0,
)

#: The default profile, named so results can record which one was used.
REFERENCE_COSTS_V1 = CostModel()


def cost_model_from(payload: dict[str, Any] | None) -> CostModel:
    """Build a cost model from a partial request payload.

    Unknown keys are ignored rather than raising so the frontend can echo a
    richer settings object than the backend consumes; known keys are validated
    as non-negative numbers.
    """
    if not payload:
        return REFERENCE_COSTS_V1
    allowed = {
        "slippage_bps",
        "brokerage_bps",
        "exchange_bps",
        "sebi_bps",
        "gst_on_fees_pct",
        "stt_sell_bps",
        "stamp_buy_bps",
    }
    overrides: dict[str, float] = {}
    for key in allowed:
        if key not in payload:
            continue
        try:
            value = float(payload[key])
        except (TypeError, ValueError):
            raise ValueError(f"Cost field '{key}' must be a number") from None
        if value < 0 or value != value:  # NaN check
            raise ValueError(f"Cost field '{key}' must be non-negative")
        if value > 1_000:
            raise ValueError(
                f"Cost field '{key}' of {value} bps looks like a unit error "
                "(basis points, not percent); refusing to run"
            )
        overrides[key] = value
    version = str(payload.get("version") or COSTS_VERSION)
    return replace(REFERENCE_COSTS_V1, version=version, **overrides)


__all__ = [
    "COSTS_VERSION",
    "CostModel",
    "REFERENCE_COSTS_V1",
    "ZERO_COSTS",
    "cost_model_from",
]
