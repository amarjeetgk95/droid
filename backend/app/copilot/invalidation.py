"""Invalidation Engine (spec §11).

Every directional view must state what would prove it wrong. Nothing is
confirmed by a single tick — the confirmation rule mirrors the DROID signal
module's acceptance standard (5m close beyond the level, then no immediate
reversal candle).
"""
from __future__ import annotations

from app.copilot.models import ConfluenceResult, InvalidationBlock, LevelsBlock, MarketContext

CONFIRMATION_RULE = (
    "Confirmation standard (DROID signal module): a 5-minute close beyond the level plus an acceptance "
    "buffer of ≈0.15×ATR, with no immediate reversal candle. A single tick through the level is ignored."
)


def build_invalidation(
    ctx: MarketContext,
    confluence: ConfluenceResult,
    levels: LevelsBlock,
) -> InvalidationBlock:
    regime = ctx.regime.name.replace("_", " ").title() if ctx.regime.name else "Unknown"
    state_label = {"BULLISH": "Bullish", "BEARISH": "Bearish"}.get(confluence.dominant_state)
    if state_label is None:
        current = f"Neutral / {regime} — {confluence.label.lower()}"
    else:
        current = f"{state_label} / {regime} — {confluence.label.lower()}"

    bull = levels.bull_trigger
    bear = levels.bear_trigger
    if confluence.dominant_state in ("BULLISH", "MILD_BULLISH"):
        invalidation = (
            f"The bullish scenario loses validity on acceptance back below {bear:,.0f}."
            if bear is not None
            else "The bullish scenario has no validated invalidation level (support levels unavailable)."
        )
    elif confluence.dominant_state in ("BEARISH", "MILD_BEARISH"):
        invalidation = (
            f"The bearish scenario loses validity on acceptance back above {bull:,.0f}."
            if bull is not None
            else "The bearish scenario has no validated invalidation level (resistance levels unavailable)."
        )
    elif confluence.dominant_state == "NEUTRAL":
        if bull is not None and bear is not None:
            invalidation = (
                f"The range-bound scenario loses validity on acceptance outside {bear:,.0f} – {bull:,.0f}; "
                "the expansion scenario that triggers then becomes the dominant one."
            )
        else:
            invalidation = "No validated boundary is available, so the range-bound scenario cannot be invalidated yet."
    else:
        invalidation = (
            "No directional scenario is published (insufficient directional evidence), so there is nothing to invalidate."
        )

    return InvalidationBlock(
        current_state=current,
        bullish_trigger=levels.bull_trigger_note,
        bearish_trigger=levels.bear_trigger_note,
        invalidation=invalidation,
        confirmation_rule=CONFIRMATION_RULE,
    )
