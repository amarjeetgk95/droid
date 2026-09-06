"""
AI Research Context Store & Background Precomputation Cache (§19, §33, §34)
Decouples high-frequency quantitative signal execution from asynchronous AI research.

Enforces:
  - Non-blocking instantaneous lookup (< 5ms) for Scalping signals (§33)
  - Configurable freshness TTLs per horizon (§19):
      * SCALP: 10 minutes
      * INTRADAY: 45 minutes
      * SWING: 4 hours
      * POSITIONAL: 24 hours
  - Deterministic AI failure policy (§34)
"""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import structlog

from app.ai.financial_research.schemas import (
    FinancialResearchReport,
    ResearchAssessment,
    AIImpact,
    ContradictionReport,
    EvidenceEffect,
)

logger = structlog.get_logger()

DEFAULT_FRESHNESS_TTL_SECONDS: dict[str, int] = {
    "SCALP": 600,       # 10 minutes
    "INTRADAY": 2700,   # 45 minutes
    "SWING": 14400,     # 4 hours
    "POSITIONAL": 86400 # 24 hours
}


class AIContextStore:
    """
    In-memory, thread-safe asynchronous research store.
    Background workers continually refresh research assessments,
    which trading signals read without latency penalties.
    """

    def __init__(self, ttl_config: Optional[dict[str, int]] = None):
        self._ttl_config = ttl_config or DEFAULT_FRESHNESS_TTL_SECONDS
        # Key: f"{underlying}_{horizon}_{direction}" -> (report, store_timestamp_utc)
        self._store: dict[str, tuple[FinancialResearchReport, datetime]] = {}

    def _make_key(self, underlying: str, horizon: str, direction: str) -> str:
        return f"{underlying.upper()}_{horizon.upper()}_{direction.upper()}"

    def set_report(self, report: FinancialResearchReport) -> None:
        key = self._make_key(report.underlying, report.horizon, report.proposed_direction)
        now_utc = datetime.now(timezone.utc)
        self._store[key] = (report, now_utc)
        logger.info(
            "ai_research_context_updated",
            key=key,
            assessment=report.research_assessment.value,
            impact=report.ai_impact.value,
        )

    def get_report(
        self,
        underlying: str,
        horizon: str,
        direction: str,
        as_of_time: Optional[datetime] = None,
    ) -> Optional[FinancialResearchReport]:
        """
        Retrieves precomputed research report if fresh. Returns None if stale or missing.
        """
        key = self._make_key(underlying, horizon, direction)
        entry = self._store.get(key)
        if not entry:
            return None

        report, store_time = entry
        now = as_of_time or datetime.now(timezone.utc)
        age_seconds = (now - store_time).total_seconds()

        max_allowed_age = self._ttl_config.get(horizon.upper(), 1800)
        if age_seconds > max_allowed_age:
            logger.warn("ai_research_context_stale", key=key, age_seconds=age_seconds, max_age=max_allowed_age)
            return None

        return report

    def get_or_fallback_default(
        self,
        underlying: str,
        horizon: str,
        direction: str,
    ) -> FinancialResearchReport:
        """
        Retrieves active report, or executes Deterministic Failure Policy (§34).
        Invariant: Never interprets missing AI as 'Approved'. Returns NEUTRAL / NO_CHANGE.
        """
        active = self.get_report(underlying, horizon, direction)
        if active:
            return active

        # §34 Deterministic Fallback Report
        return FinancialResearchReport(
            research_id=f"fallback-{underlying}-{int(time.time())}",
            underlying=underlying,
            proposed_direction=direction,  # type: ignore
            horizon=horizon,  # type: ignore
            research_status="FALLBACK_TIMEOUT",
            market_context=EvidenceEffect.NEUTRAL,
            macro_context=EvidenceEffect.NEUTRAL,
            fundamental_context=EvidenceEffect.NEUTRAL,
            news_context=EvidenceEffect.NEUTRAL,
            sentiment_context=EvidenceEffect.NEUTRAL,
            cross_asset_context=EvidenceEffect.NEUTRAL,
            supporting_evidence=[],
            contradiction_analysis=ContradictionReport(
                strongest_counter_argument="AI research unavailable or stale; quantitative signal proceeding without AI leverage",
                contradicting_evidence=[],
                key_risks=["Missing real-time macro/news AI validation"],
                invalidation_conditions=[],
                missing_information=["Live AI context unavailable"],
                counter_weight_score=0.0,
            ),
            key_catalysts=[],
            bull_case_summary="No active AI confirmation",
            bear_case_summary="No active AI disconfirmation",
            uncertainty_level="HIGH",
            research_assessment=ResearchAssessment.INSUFFICIENT_EVIDENCE,
            ai_impact=AIImpact.NO_CHANGE,
            impact_rationale=["Fallback Policy (§34): AI unavailable. Quant signal permitted with neutral score."],
        )


# Global singleton
ai_context_store = AIContextStore()
