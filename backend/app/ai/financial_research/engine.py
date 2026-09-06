"""
Dedicated AI Financial Research & Contradiction Engine (§9, §16, §17, §18, §22)
Synthesizes market, macro, news, and fundamentals, and enforces mandatory
disconfirmation research to evaluate whether a quantitative signal should be:
  STRENGTHENED, LEFT UNCHANGED, WEAKENED, or BLOCKED.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional
import structlog

from app.ai.financial_research.schemas import (
    FinancialResearchReport,
    SourcedEvidence,
    SourceTier,
    EvidenceEffect,
    ResearchAssessment,
    AIImpact,
    ContradictionReport,
)
from app.ai.financial_research.adversarial import AdversarialSanitizer
from app.ai.financial_research.context_store import ai_context_store

logger = structlog.get_logger()


class FinancialResearchEngine:
    """
    Evaluates market intelligence, macro context, and active contradictions
    for index options signals (NIFTY, BANKNIFTY, SENSEX).
    """

    # Weights by Source Tier (Tier 1 = 3.0x, Tier 7 = 0.2x)
    TIER_WEIGHTS = {
        SourceTier.TIER_1_REGULATOR: 3.0,
        SourceTier.TIER_2_CENTRAL_BANK: 2.8,
        SourceTier.TIER_3_COMPANY_FILING: 2.5,
        SourceTier.TIER_4_TIER1_FINANCIAL: 2.0,
        SourceTier.TIER_5_FINANCIAL_PRESS: 1.5,
        SourceTier.TIER_6_SECONDARY_RESEARCH: 1.0,
        SourceTier.TIER_7_UNVERIFIED_SOCIAL: 0.2,
    }

    def synthesize_research(
        self,
        underlying: str,
        proposed_direction: Literal["BULLISH", "BEARISH"],
        horizon: Literal["SCALP", "INTRADAY", "SWING", "POSITIONAL"],
        candidate_evidence: list[SourcedEvidence],
        macro_summary: Optional[str] = None,
        constituent_summary: Optional[str] = None,
        as_of_time: Optional[datetime] = None,
    ) -> FinancialResearchReport:
        """
        Processes evidence through adversarial filters, calculates source-weighted
        support vs contradiction, and produces the authoritative FinancialResearchReport.
        """
        now = as_of_time or datetime.now(timezone.utc)
        sanitized_evidence: list[SourcedEvidence] = []

        # 1. Sanitize all incoming evidence (§20)
        for ev in candidate_evidence:
            if AdversarialSanitizer.validate_evidence(ev, as_of_time=now):
                sanitized_evidence.append(ev)

        # 2. Segregate supporting vs contradictory
        supporting: list[SourcedEvidence] = []
        contradicting: list[SourcedEvidence] = []
        neutral: list[SourcedEvidence] = []

        for ev in sanitized_evidence:
            if ev.effect == EvidenceEffect.SUPPORTIVE:
                supporting.append(ev)
            elif ev.effect == EvidenceEffect.CONTRADICTORY:
                contradicting.append(ev)
            else:
                neutral.append(ev)

        # 3. Source-Weighted Scoring (§18)
        support_score = sum(
            (ev.confidence / 100.0) * self.TIER_WEIGHTS.get(ev.source_tier, 1.0)
            for ev in supporting
        )
        counter_score = sum(
            (ev.confidence / 100.0) * self.TIER_WEIGHTS.get(ev.source_tier, 1.0)
            for ev in contradicting
        )

        total_weight = support_score + counter_score
        counter_weight_ratio = (counter_score / total_weight * 100.0) if total_weight > 0 else 0.0

        # 4. Mandatory Contradiction Analysis (§16)
        strongest_counter = "No high-conviction contradicting fundamental or macro catalysts detected."
        key_risks = []
        invalidation = []

        if contradicting:
            # Pick highest weighted counter-claim
            top_counter = max(contradicting, key=lambda e: (e.confidence * self.TIER_WEIGHTS.get(e.source_tier, 1.0)))
            strongest_counter = f"[{top_counter.source_name}] {top_counter.claim}"
            key_risks = [f"{e.source_name}: {e.claim}" for e in contradicting[:3]]
            invalidation.append(f"Invalidate if {top_counter.claim.lower()} intensifies")
        else:
            key_risks.append("Market-wide sudden liquidity or macro volatility shock")
            invalidation.append("Violation of local market structure trigger")

        contradiction_rep = ContradictionReport(
            strongest_counter_argument=strongest_counter,
            contradicting_evidence=contradicting,
            key_risks=key_risks,
            invalidation_conditions=invalidation,
            missing_information=["Full real-time institutional block trade telemetry"],
            counter_weight_score=round(counter_weight_ratio, 1),
        )

        # 5. Bull / Bear Framework Assessment (§17)
        bull_summary = f"Support score {support_score:.2f} across {len(supporting)} validated sources."
        if supporting:
            bull_summary += f" Key driver: {supporting[0].claim}"

        bear_summary = f"Counter score {counter_score:.2f} across {len(contradicting)} sources. Counter: {strongest_counter}"

        # Determine Assessment
        if counter_weight_ratio >= 65.0:
            assessment = ResearchAssessment.STRONGLY_ADVERSE
            impact = AIImpact.BLOCK
            rationale = [f"Blocked: Counter-evidence weight ({counter_weight_ratio:.1f}%) exceeds safety ceiling (65%)", strongest_counter]
        elif counter_weight_ratio >= 45.0:
            assessment = ResearchAssessment.MODERATELY_ADVERSE
            impact = AIImpact.WEAKEN
            rationale = [f"Weakened: Material counter-evidence ({counter_weight_ratio:.1f}%) warrants defensive sizing"]
        elif support_score >= 3.5 and counter_weight_ratio <= 20.0:
            assessment = ResearchAssessment.STRONGLY_SUPPORTIVE
            impact = AIImpact.STRENGTHEN
            rationale = [f"Strengthened: High-conviction institutional confirmation (Support: {support_score:.1f}, Counter: {counter_weight_ratio:.1f}%)"]
        elif support_score >= 1.5 and counter_weight_ratio <= 35.0:
            assessment = ResearchAssessment.MODERATELY_SUPPORTIVE
            impact = AIImpact.NO_CHANGE  # Moderate support leaves signal unchanged per conservative policy (§2)
            rationale = ["Supportive financial context corroborates quantitative setup"]
        elif not supporting and not contradicting:
            assessment = ResearchAssessment.INSUFFICIENT_EVIDENCE
            impact = AIImpact.NO_CHANGE
            rationale = ["Insufficient external financial evidence; relying purely on quantitative setup"]
        else:
            assessment = ResearchAssessment.MIXED
            impact = AIImpact.NO_CHANGE
            rationale = [f"Mixed financial signals (Support: {support_score:.1f}, Counter: {counter_score:.1f})"]

        # Context indicators
        market_ctx = EvidenceEffect.SUPPORTIVE if support_score > counter_score else EvidenceEffect.NEUTRAL

        report = FinancialResearchReport(
            research_id=f"res-{underlying}-{uuid.uuid4().hex[:8]}",
            underlying=underlying,
            proposed_direction=proposed_direction,
            horizon=horizon,
            created_at=now,
            research_status="COMPLETE",
            market_context=market_ctx,
            macro_context=EvidenceEffect.SUPPORTIVE if "bullish" in (macro_summary or "").lower() else EvidenceEffect.NEUTRAL,
            fundamental_context=EvidenceEffect.SUPPORTIVE if "supportive" in (constituent_summary or "").lower() else EvidenceEffect.NEUTRAL,
            news_context=EvidenceEffect.SUPPORTIVE if support_score > 1.0 else EvidenceEffect.NEUTRAL,
            sentiment_context=EvidenceEffect.NEUTRAL,
            cross_asset_context=EvidenceEffect.NEUTRAL,
            supporting_evidence=supporting,
            contradiction_analysis=contradiction_rep,
            key_catalysts=[ev.claim for ev in supporting[:2]] or ["Technical breakout expansion"],
            bull_case_summary=bull_summary,
            bear_case_summary=bear_summary,
            uncertainty_level="HIGH" if counter_weight_ratio > 40.0 else "LOW" if support_score > 3.0 else "MODERATE",
            research_assessment=assessment,
            ai_impact=impact,
            impact_rationale=rationale,
            model_version="financial-research-v1.0",
        )

        # Automatically store in background cache (§33)
        ai_context_store.set_report(report)
        return report


# Global singleton
financial_research_engine = FinancialResearchEngine()
