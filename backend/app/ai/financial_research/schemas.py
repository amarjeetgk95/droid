"""
AI Financial Research Schemas (§18, §21, §22)
Defines structured data models for:
  - Source Hierarchy Tiers
  - Sourced Evidence Items & Claims
  - Contradiction & Invalidation Research
  - AI Financial Research Report
  - AI-to-Signal Impact Contract
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class SourceTier(IntEnum):
    """Source credibility hierarchy (§18). Lower number = higher institutional authority."""
    TIER_1_REGULATOR = 1       # RBI, SEBI, Government, Exchange notices
    TIER_2_CENTRAL_BANK = 2     # Central bank statements, monetary policy reports
    TIER_3_COMPANY_FILING = 3   # Official corporate disclosures, exchange filings
    TIER_4_TIER1_FINANCIAL = 4  # Bloomberg, Reuters, official exchange feeds
    TIER_5_FINANCIAL_PRESS = 5  # Economic Times, Mint, Moneycontrol, CNBC-TV18
    TIER_6_SECONDARY_RESEARCH = 6 # Brokerage notes, institutional research
    TIER_7_UNVERIFIED_SOCIAL = 7  # Social media, unverified retail sentiment


class EvidenceEffect(str, Enum):
    SUPPORTIVE = "SUPPORTIVE"
    CONTRADICTORY = "CONTRADICTORY"
    NEUTRAL = "NEUTRAL"
    UNCERTAIN = "UNCERTAIN"


class ResearchAssessment(str, Enum):
    STRONGLY_SUPPORTIVE = "STRONGLY_SUPPORTIVE"
    MODERATELY_SUPPORTIVE = "MODERATELY_SUPPORTIVE"
    MIXED = "MIXED"
    MODERATELY_ADVERSE = "MODERATELY_ADVERSE"
    STRONGLY_ADVERSE = "STRONGLY_ADVERSE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AIImpact(str, Enum):
    """The controlled effect AI can exert on a quantitative signal (§22)."""
    STRENGTHEN = "STRENGTHEN"
    NO_CHANGE = "NO_CHANGE"
    WEAKEN = "WEAKEN"
    BLOCK = "BLOCK"


class SourcedEvidence(BaseModel):
    claim: str = Field(..., description="Fact or assertion extracted from source")
    source_name: str = Field(..., description="Name of source, e.g. 'RBI Bulletin', 'NSE Filing'")
    source_tier: SourceTier = Field(..., description="Credibility tier (1=Highest to 7=Lowest)")
    source_url: Optional[str] = None
    publication_timestamp: datetime = Field(..., description="When the original document was published")
    retrieval_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effect: EvidenceEffect = Field(..., description="Directional impact on underlying trade thesis")
    confidence: float = Field(default=80.0, ge=0.0, le=100.0)
    is_sanitized: bool = Field(default=True, description="Passed adversarial sanitization filter")


class ContradictionReport(BaseModel):
    strongest_counter_argument: str = Field(..., description="Single most compelling thesis AGAINST the trade")
    contradicting_evidence: list[SourcedEvidence] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    counter_weight_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Weight of counter-evidence (0 = zero contradictory signal, 100 = overwhelming counter-signal)"
    )


class FinancialResearchReport(BaseModel):
    """Comprehensive structured output schema adhering strictly to §21."""
    research_id: str
    underlying: str
    proposed_direction: Literal["BULLISH", "BEARISH"]
    horizon: Literal["SCALP", "INTRADAY", "SWING", "POSITIONAL"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    research_status: Literal["COMPLETE", "PARTIAL", "FALLBACK_TIMEOUT"] = "COMPLETE"

    # Context classifications
    market_context: EvidenceEffect = EvidenceEffect.NEUTRAL
    macro_context: EvidenceEffect = EvidenceEffect.NEUTRAL
    fundamental_context: EvidenceEffect = EvidenceEffect.NEUTRAL
    news_context: EvidenceEffect = EvidenceEffect.NEUTRAL
    sentiment_context: EvidenceEffect = EvidenceEffect.NEUTRAL
    cross_asset_context: EvidenceEffect = EvidenceEffect.NEUTRAL

    # Evidence Breakdown
    supporting_evidence: list[SourcedEvidence] = Field(default_factory=list)
    contradiction_analysis: ContradictionReport
    key_catalysts: list[str] = Field(default_factory=list)
    
    # Framework synthesis (§17)
    bull_case_summary: str
    bear_case_summary: str
    uncertainty_level: Literal["LOW", "MODERATE", "HIGH", "EXTREME"] = "MODERATE"
    research_assessment: ResearchAssessment = ResearchAssessment.MIXED

    # AI -> Signal Contract Impact (§22)
    ai_impact: AIImpact = AIImpact.NO_CHANGE
    impact_rationale: list[str] = Field(default_factory=list)
    model_version: str = "financial-research-v1.0"
