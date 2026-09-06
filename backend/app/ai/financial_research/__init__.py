"""
AI Financial Research Module
Provides sourced evidence extraction, contradiction detection,
adversarial sanitization, and non-blocking background context store.
"""
from app.ai.financial_research.schemas import (
    SourceTier,
    EvidenceEffect,
    ResearchAssessment,
    AIImpact,
    SourcedEvidence,
    ContradictionReport,
    FinancialResearchReport,
)
from app.ai.financial_research.adversarial import AdversarialSanitizer
from app.ai.financial_research.context_store import (
    AIContextStore,
    ai_context_store,
)
from app.ai.financial_research.engine import (
    FinancialResearchEngine,
    financial_research_engine,
)

__all__ = [
    "SourceTier",
    "EvidenceEffect",
    "ResearchAssessment",
    "AIImpact",
    "SourcedEvidence",
    "ContradictionReport",
    "FinancialResearchReport",
    "AdversarialSanitizer",
    "AIContextStore",
    "ai_context_store",
    "FinancialResearchEngine",
    "financial_research_engine",
]
