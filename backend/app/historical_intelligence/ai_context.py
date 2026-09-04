"""
AI Context Layer & Structured Evidence Generator — §§26, 27
Prepares prompt-ready factual evidence for the LLM Decision Layer without mathematical hallucinations.
"""
from __future__ import annotations

from app.historical_intelligence.schemas import (
    HistoricalIntelligenceResult,
    AIStructuredContext,
)
from app.historical_intelligence.statistics import classify_sample_reliability


class AIContextGenerator:
    """
    Transforms numerical historical analytics into a structured evidence payload
    for AI / LLM Contextual Analysis (§26).
    """

    def generate_context(
        self,
        result: HistoricalIntelligenceResult,
    ) -> AIStructuredContext:
        reliability = classify_sample_reliability(result.sample_count)

        # 1. Summary Narrative
        summary_lines = [
            f"Historical Intelligence Analysis ({result.sample_count} matching states, ESS={result.effective_sample_size}):",
            f"- 15m Horizon: Bullish {int(result.probability_15m * 100)}%, Bearish {int((1.0 - result.probability_15m) * 100)}%, Median Return {result.median_return_15m:+.2f}%",
            f"- 30m Horizon: Bullish {int(result.probability_30m * 100)}%, Bearish {int((1.0 - result.probability_30m) * 100)}%, Median Return {result.median_return_30m:+.2f}%",
            f"- 60m Horizon: Bullish {int(result.probability_60m * 100)}%, Bearish {int((1.0 - result.probability_60m) * 100)}%, Median Return {result.median_return_60m:+.2f}%",
            f"- Historical Edge Dynamic: Continuation {int(result.continuation_probability * 100)}%, Failure Rate {int(result.failure_probability * 100)}%, Reversal {int(result.reversal_probability * 100)}%",
            f"- Risk/Reward Geometry: Median Favorable Excursion (MFE) {result.median_MFE:+.2f}%, Median Adverse Excursion (MAE) {result.median_MAE:+.2f}%",
            f"- Historical Confidence: {result.confidence:.2f} ({reliability.value})",
        ]
        summary_text = "\n".join(summary_lines)

        # 2. Evidence Table
        evidence = {
            "sample_count": result.sample_count,
            "effective_sample_size": result.effective_sample_size,
            "similarity_score": result.similarity_score,
            "horizons": {
                "15m": {
                    "bullish_prob": result.probability_15m,
                    "median_return": result.median_return_15m,
                },
                "30m": {
                    "bullish_prob": result.probability_30m,
                    "median_return": result.median_return_30m,
                },
                "60m": {
                    "bullish_prob": result.probability_60m,
                    "median_return": result.median_return_60m,
                },
            },
            "mfe_pct": result.median_MFE,
            "mae_pct": result.median_MAE,
            "target_hit_rate": result.target_hit_rate,
            "stop_hit_rate": result.stop_hit_rate,
        }

        # 3. Failure & Persistence Analysis
        decay_text = "PERSISTENT"
        if result.probability_15m > result.probability_30m > result.probability_60m:
            decay_text = "DECAYING_OVER_TIME"
        elif result.probability_15m < result.probability_30m < result.probability_60m:
            decay_text = "ACCELERATING_OVER_TIME"

        failure_info = {
            "failure_rate": result.failure_probability,
            "stop_hit_rate": result.stop_hit_rate,
            "reversal_rate": result.reversal_probability,
            "primary_failure_mode": "EARLY_STOP_BREACH" if result.stop_hit_rate > 0.4 else "MOMENTUM_STALL",
        }

        regime_note = f"Analogues conditioned on regime {result.historical_regime}. Evidence indicates {decay_text} edge."

        return AIStructuredContext(
            historical_summary_text=summary_text,
            total_analogs=result.sample_count,
            effective_sample_size=result.effective_sample_size,
            sample_reliability=reliability,
            evidence_table=evidence,
            failure_analysis=failure_info,
            regime_consistency_note=regime_note,
            historical_edge_status=decay_text,
        )


ai_context_generator = AIContextGenerator()
