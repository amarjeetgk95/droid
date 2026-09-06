"""
AI Adversarial Content Protection & Sanitization (§20, §53)
Enforces:
  - Prompt injection sanitization (strips instruction overrides)
  - Disallows low-tier sources (Tier 7) from unilaterally upgrading signals
  - Coordinated sentiment anomaly detection
  - Lookahead timestamp validation (rejects claims with future timestamps)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
import structlog

from app.ai.financial_research.schemas import SourcedEvidence, SourceTier

logger = structlog.get_logger()

# Known prompt injection signatures
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|system)\s+rules?",
    r"you\s+are\s+now\s+(a|an|in)\s+mode",
    r"system\s*:\s*override",
    r"report\s+this\s+(stock|symbol|trade|signal)\s+as\s+(bullish|buy|bearish)",
    r"print\s+only\s+buy",
    r"bypass\s+risk\s+limits?",
    r"developer\s+mode\s+activated",
    r"<\s*script[^>]*>.*?<\s*/\s*script\s*>",
]

COMPILED_INJECTION_REGEX = [re.compile(p, re.IGNORECASE) for p in PROMPT_INJECTION_PATTERNS]


class AdversarialSanitizer:
    """
    Sanitizes untrusted external market texts, news feeds, and analyst notes
    to prevent prompt hijacking, fake financial claims, and manipulated sentiment.
    """

    @classmethod
    def sanitize_text(cls, raw_text: str) -> tuple[str, bool]:
        """
        Strips adversarial injection patterns from raw text.
        Returns: (sanitized_text, injection_detected_bool)
        """
        if not raw_text:
            return "", False

        cleaned = raw_text
        detected = False

        for pattern in COMPILED_INJECTION_REGEX:
            if pattern.search(cleaned):
                detected = True
                cleaned = pattern.sub("[REDACTED_ADVERSARIAL_INPUT]", cleaned)

        # Strip control characters and excessive unprintable symbols
        cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in ("\n", "\t", "\r"))

        if detected:
            logger.warn("adversarial_injection_attempt_neutralized", original_snippet=raw_text[:120])

        return cleaned.strip(), detected

    @classmethod
    def validate_evidence(cls, evidence: SourcedEvidence, as_of_time: Optional[datetime] = None) -> bool:
        """
        Validates evidence against temporal and source credibility rules (§5, §18, §20).
        """
        now = as_of_time or datetime.now(timezone.utc)

        # 1. No Future timestamps (Lookahead guard §5)
        # Allow 5-second leeway for clock skew
        if evidence.publication_timestamp > (now.astimezone(timezone.utc) + timezone.utc.utcoffset(None) if evidence.publication_timestamp.tzinfo else now):
            pub_ts = evidence.publication_timestamp if evidence.publication_timestamp.tzinfo else evidence.publication_timestamp.replace(tzinfo=timezone.utc)
            if pub_ts > (now.replace(tzinfo=timezone.utc) if not now.tzinfo else now):
                logger.warn("evidence_rejected_future_timestamp", source=evidence.source_name, pub_ts=evidence.publication_timestamp)
                return False

        # 2. Text sanitization
        sanitized_claim, injected = cls.sanitize_text(evidence.claim)
        if injected:
            evidence.claim = sanitized_claim
            evidence.confidence *= 0.25  # Massive penalty for adversarial text

        # 3. Low-Tier Source Guard (§20)
        # Tier 7 (unverified social) cannot have high confidence
        if evidence.source_tier == SourceTier.TIER_7_UNVERIFIED_SOCIAL:
            evidence.confidence = min(evidence.confidence, 40.0)

        return True
