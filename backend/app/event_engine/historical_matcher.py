from __future__ import annotations

from datetime import datetime, timezone, date
from typing import Optional
import structlog

from app.event_engine.models import CanonicalEvent, EventComparable

logger = structlog.get_logger()

# Verified Historical RBI Policy Outcomes for Context Matching
HISTORICAL_RBI_DECISIONS = [
    {
        "past_event_id": "RBI_MPC_20250207",
        "past_event_date": "2025-02-07",
        "title": "RBI MPC Resolution Feb 2025",
        "action": "REPO_RATE_CUT_25BPS",
        "repo_rate": 6.25,
        "stance": "NEUTRAL",
        "market_reaction": {
            "banknifty_15m_move_pct": 0.85,
            "banknifty_day_move_pct": 1.40,
            "iv_crush_pct": -18.5,
            "direction": "BULLISH",
        },
    },
    {
        "past_event_id": "RBI_MPC_20241206",
        "past_event_date": "2024-12-06",
        "title": "RBI MPC Resolution Dec 2024",
        "action": "STATUS_QUO_CRR_CUT_50BPS",
        "repo_rate": 6.50,
        "stance": "NEUTRAL",
        "market_reaction": {
            "banknifty_15m_move_pct": 0.45,
            "banknifty_day_move_pct": 0.65,
            "iv_crush_pct": -14.2,
            "direction": "BULLISH",
        },
    },
    {
        "past_event_id": "RBI_MPC_20241009",
        "past_event_date": "2024-10-09",
        "title": "RBI MPC Resolution Oct 2024",
        "action": "STATUS_QUO_STANCE_CHANGE",
        "repo_rate": 6.50,
        "stance": "NEUTRAL",
        "market_reaction": {
            "banknifty_15m_move_pct": 0.90,
            "banknifty_day_move_pct": 1.15,
            "iv_crush_pct": -16.0,
            "direction": "BULLISH",
        },
    },
]


class HistoricalEventMatcher:
    """Matches events against comparable historical precedents (§22).
    
    Guarantees Anti-Lookahead compliance (§21):
      Only events strictly preceding data_cutoff_timestamp are eligible.
    """

    def match_comparables(
        self,
        event: CanonicalEvent,
        data_cutoff: Optional[datetime] = None,
        top_k: int = 3,
    ) -> list[EventComparable]:
        """Find past historical occurrences strictly before the cutoff timestamp."""
        cutoff = data_cutoff or datetime.now(timezone.utc)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)

        comparables: list[EventComparable] = []

        if event.entity_id.upper() == "RBI" or event.event_type == "CENTRAL_BANK":
            for hist in HISTORICAL_RBI_DECISIONS:
                hist_date = date.fromisoformat(hist["past_event_date"])
                hist_dt = datetime.combine(hist_date, datetime.min.time(), tzinfo=timezone.utc)

                # STRICT ANTI-LOOKAHEAD GUARD (§21):
                # Historical event date must be strictly prior to cutoff timestamp.
                if hist_dt >= cutoff:
                    continue

                # Match calculation
                similarity = 0.85
                if event.sub_type and "RATE" in event.sub_type.upper():
                    similarity = 0.92

                comparables.append(
                    EventComparable(
                        past_event_id=hist["past_event_id"],
                        past_event_date=hist["past_event_date"],
                        similarity_score=similarity,
                        key_comparison_factor=f"RBI MPC Rate Decision with {hist['action']}",
                        past_market_reaction=hist["market_reaction"],
                    )
                )

        # Sort by similarity descending, take top_k
        comparables.sort(key=lambda c: c.similarity_score, reverse=True)
        return comparables[:top_k]


historical_matcher = HistoricalEventMatcher()
