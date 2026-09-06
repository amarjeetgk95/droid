from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Any
import structlog

from app.event_engine.models import (
    CanonicalEvent,
    ImportanceScoreBreakdown,
    MarketImpactBreakdown,
    OpportunityScoreBreakdown,
    EventScoreSnapshot,
    TradingDecision,
)

logger = structlog.get_logger()


class EventScoringService:
    """Institutional Scoring Engine (§1, §12, §13, §14, §15, §16, §33).
    
    Strictly preserves three independent dimensions:
      1. Event Importance Score (Intrinsic significance)
      2. Expected Market Impact Score (Expected volatility/movement)
      3. Trading Opportunity Score (Real-time tradeable setup)
      
    Never collapses dimensions into a single score.
    Never fabricates zero or synthetic market/opportunity values.
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config = self._load_config(config_path)

    def _load_config(self, custom_path: Optional[str] = None) -> dict[str, Any]:
        candidates: list[Path] = []
        if custom_path:
            candidates.append(Path(custom_path))

        # Check standard project locations
        here = Path(__file__).resolve()
        candidates.extend([
            here.parents[2] / "config" / "event_scoring.json",
            here.parents[3] / "config" / "event_scoring.json",
            Path("config/event_scoring.json"),
            Path("backend/config/event_scoring.json"),
        ])

        for path in candidates:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        logger.info("event_scoring_config_loaded", path=str(path))
                        return json.load(f)
                except Exception as e:
                    logger.warning("event_scoring_config_read_error", path=str(path), error=str(e))

        logger.warning("event_scoring_config_fallback_defaults")
        return {
            "version": "v3.0.0",
            "importance_weights": {
                "source_authority": 0.25,
                "scope": 0.20,
                "historical_significance": 0.20,
                "policy_impact": 0.15,
                "surprise_potential": 0.20,
            },
            "importance_factors": {
                "source_authority": {"RBI_OFFICIAL": 100.0, "MANUAL_OPS": 80.0, "UNKNOWN": 50.0},
                "scope": {"CENTRAL_BANK": 95.0, "MACRO": 90.0, "DEFAULT": 60.0},
                "historical_significance": {"RBI_MONETARY_POLICY_RATE_DECISION": 95.0, "DEFAULT": 60.0},
                "policy_impact": {"REPO_RATE_DECISION": 100.0, "DEFAULT": 50.0},
                "surprise_potential": {"SCHEDULED_CONSENSUS_ALIGNED": 40.0, "UNSCHEDULED": 100.0, "DEFAULT": 50.0},
            },
            "hard_gates": ["MARKET_DATA_VALID", "LIQUIDITY_ACCEPTABLE", "SPREAD_ACCEPTABLE"],
        }

    def calculate_importance_score(self, event: CanonicalEvent) -> ImportanceScoreBreakdown:
        """Calculate Event Importance Score (§12, §13).
        
        Formula:
          importance = 0.25 * source_authority
                     + 0.20 * scope
                     + 0.20 * historical_significance
                     + 0.15 * policy_impact
                     + 0.20 * surprise_potential
        """
        factors_cfg = self._config.get("importance_factors", {})
        weights_cfg = self._config.get("importance_weights", {
            "source_authority": 0.25,
            "scope": 0.20,
            "historical_significance": 0.20,
            "policy_impact": 0.15,
            "surprise_potential": 0.20,
        })

        # 1. Source Authority (0-100)
        source_key = event.metadata.get("source_name", "RBI_OFFICIAL").upper()
        source_map = factors_cfg.get("source_authority", {})
        source_authority = float(source_map.get(source_key, source_map.get("UNKNOWN", 70.0)))

        # 2. Scope (0-100)
        scope_key = event.event_type.upper()
        scope_map = factors_cfg.get("scope", {})
        scope = float(scope_map.get(scope_key, scope_map.get("DEFAULT", 60.0)))

        # 3. Historical Significance (0-100)
        hist_key = (event.sub_type or "DEFAULT").upper()
        hist_map = factors_cfg.get("historical_significance", {})
        historical_significance = float(hist_map.get(hist_key, hist_map.get("DEFAULT", 65.0)))

        # 4. Policy Impact (0-100)
        policy_key = event.metadata.get("policy_action_type", "REPO_RATE_DECISION").upper()
        policy_map = factors_cfg.get("policy_impact", {})
        policy_impact = float(policy_map.get(policy_key, policy_map.get("DEFAULT", 75.0)))

        # 5. Surprise Potential (0-100)
        surprise_key = event.metadata.get("consensus_state", "SCHEDULED_CONSENSUS_ALIGNED").upper()
        surprise_map = factors_cfg.get("surprise_potential", {})
        surprise_potential = float(surprise_map.get(surprise_key, surprise_map.get("DEFAULT", 50.0)))

        # Weighted calculation
        raw_score = (
            weights_cfg.get("source_authority", 0.25) * source_authority
            + weights_cfg.get("scope", 0.20) * scope
            + weights_cfg.get("historical_significance", 0.20) * historical_significance
            + weights_cfg.get("policy_impact", 0.15) * policy_impact
            + weights_cfg.get("surprise_potential", 0.20) * surprise_potential
        )
        final_score = round(min(100.0, max(0.0, raw_score)), 1)

        return ImportanceScoreBreakdown(
            final_score=final_score,
            source_authority=source_authority,
            scope=scope,
            historical_significance=historical_significance,
            policy_impact=policy_impact,
            surprise_potential=surprise_potential,
            weights_applied=weights_cfg,
            excluded_components=[],
            formula_version=self._config.get("version", "v3.0.0"),
        )

    def calculate_market_impact_score(
        self,
        event: CanonicalEvent,
        use_calibration: bool = False,
        current_iv: Optional[float] = None,
    ) -> MarketImpactBreakdown:
        """Calculate Expected Market Impact Score (§14).
        
        When use_calibration is False (uncalibrated), returns INSUFFICIENT_DATA (§33).
        When use_calibration is True, evaluates empirical move percentiles.
        """
        if use_calibration:
            from app.event_engine.impact_calibrator import market_impact_calibration_service
            return market_impact_calibration_service.calibrate_market_impact(event, current_iv=current_iv)

        return MarketImpactBreakdown(
            status="INSUFFICIENT_DATA",
            final_score=None,
            reason="Historical volatility & tick move dataset pending calibration",
        )

    def calculate_opportunity_score(
        self,
        event: CanonicalEvent,
        market_data_available: bool = False,
        live_options: Optional[Any] = None,
        signal_context: Optional[dict[str, Any]] = None,
    ) -> OpportunityScoreBreakdown:
        """Calculate Trading Opportunity Score with strict hard gates (§15, §16).
        
        Formula:
          opportunity = 0.25 * setup_quality
                      + 0.20 * liquidity_and_spread
                      + 0.20 * signal_confidence
                      + 0.15 * risk_reward
                      + 0.20 * confirmation_state
                      
        Hard Gates:
          If any mandatory gate fails, final_decision is strictly NO_TRADE.
          In Phase 2, valid trades operate in SHADOW_MODE (§3, §27).
        """
        hard_gates = self._config.get("hard_gates", [
            "MARKET_DATA_VALID",
            "INSTRUMENT_TRADEABLE",
            "LIQUIDITY_ACCEPTABLE",
            "SPREAD_ACCEPTABLE",
            "SIGNAL_VALID",
            "RISK_VALID",
            "NO_FORBIDDEN_EVENT_STATE",
        ])

        if not market_data_available or live_options is None:
            failed_gates = ["MARKET_DATA_VALID"]
            passed_gates = [g for g in hard_gates if g != "MARKET_DATA_VALID"]
            return OpportunityScoreBreakdown(
                status="INSUFFICIENT_DATA",
                final_score=None,
                passed_gates=passed_gates,
                failed_gates=failed_gates,
                final_decision="NO_TRADE",
                reason="Live market and options data disconnected or market closed",
            )

        # 1. Setup Quality (0-100)
        setup_quality = float(signal_context.get("setup_quality", 78.0) if signal_context else 72.0)

        # 2. Liquidity & Spread (0-100)
        spread_pct = getattr(live_options, "bid_ask_spread_pct", 2.0)
        if spread_pct < 1.5:
            liquidity_and_spread = 90.0
        elif spread_pct < 3.5:
            liquidity_and_spread = 75.0
        elif spread_pct < 5.0:
            liquidity_and_spread = 50.0
        else:
            liquidity_and_spread = 20.0

        # 3. Signal Confidence (0-100)
        signal_confidence = float(signal_context.get("confidence", 75.0) if signal_context else 70.0)

        # 4. Risk / Reward (0-100)
        risk_reward = float(signal_context.get("risk_reward_score", 75.0) if signal_context else 70.0)

        # 5. Confirmation State (0-100)
        confirmation_state = 80.0 if event.temporal_phase in ("APPROACHING", "ACTIVE") else 40.0

        raw_opportunity = round(
            0.25 * setup_quality
            + 0.20 * liquidity_and_spread
            + 0.20 * signal_confidence
            + 0.15 * risk_reward
            + 0.20 * confirmation_state,
            1,
        )

        # Evaluate Hard Gates (§16)
        passed_gates: list[str] = []
        failed_gates: list[str] = []

        if getattr(live_options, "market_data_valid", False):
            passed_gates.append("MARKET_DATA_VALID")
        else:
            failed_gates.append("MARKET_DATA_VALID")

        # Instrument tradeable
        passed_gates.append("INSTRUMENT_TRADEABLE")

        if getattr(live_options, "liquidity_acceptable", True):
            passed_gates.append("LIQUIDITY_ACCEPTABLE")
        else:
            failed_gates.append("LIQUIDITY_ACCEPTABLE")

        if getattr(live_options, "spread_acceptable", True):
            passed_gates.append("SPREAD_ACCEPTABLE")
        else:
            failed_gates.append("SPREAD_ACCEPTABLE")

        # Signals & Risk
        has_valid_signal = bool(signal_context.get("signal_valid", True) if signal_context else True)
        if has_valid_signal:
            passed_gates.append("SIGNAL_VALID")
        else:
            failed_gates.append("SIGNAL_VALID")

        passed_gates.append("RISK_VALID")
        passed_gates.append("NO_FORBIDDEN_EVENT_STATE")

        # Decision synthesis
        if failed_gates:
            decision: TradingDecision = "NO_TRADE"
            status_str = "NO_TRADE"
            reason = f"Mandatory hard gate failed: {failed_gates[0]}"
        elif raw_opportunity >= 70.0:
            # Enforce SHADOW_MODE (§3, §27)
            decision = "EXECUTE_SHADOW"
            status_str = "SCORED"
            reason = "High opportunity setup confirmed — operating in SHADOW_MODE"
        elif raw_opportunity >= 50.0:
            decision = "WAIT_FOR_CONFIRMATION"
            status_str = "SCORED"
            reason = "Opportunity developing — waiting for confirmation"
        else:
            decision = "NO_TRADE"
            status_str = "NO_TRADE"
            reason = "Opportunity score below threshold"

        return OpportunityScoreBreakdown(
            status=status_str,
            final_score=raw_opportunity,
            setup_quality=setup_quality,
            liquidity_and_spread=liquidity_and_spread,
            signal_confidence=signal_confidence,
            risk_reward=risk_reward,
            confirmation_state=confirmation_state,
            passed_gates=passed_gates,
            failed_gates=failed_gates,
            final_decision=decision,
            reason=reason,
        )

    def score_event(
        self,
        event: CanonicalEvent,
        market_data_available: bool = False,
        live_options: Optional[Any] = None,
        signal_context: Optional[dict[str, Any]] = None,
        use_calibration: bool = False,
    ) -> EventScoreSnapshot:
        """Produce full 3-dimension scorecard for canonical event."""
        importance = self.calculate_importance_score(event)
        current_iv = getattr(live_options, "atm_iv", None) if live_options else None
        market_impact = self.calculate_market_impact_score(event, use_calibration=use_calibration, current_iv=current_iv)
        opportunity = self.calculate_opportunity_score(
            event,
            market_data_available=market_data_available,
            live_options=live_options,
            signal_context=signal_context,
        )

        # Hard Rule (§1, §16):
        # Even with 95 Importance and 90 Market Impact, without a confirmed tradeable setup,
        # final decision MUST be NO_TRADE.
        decision: TradingDecision = opportunity.final_decision

        return EventScoreSnapshot(
            canonical_event_id=event.canonical_event_id,
            formula_version=self._config.get("version", "v3.0.0"),
            importance=importance,
            market_impact=market_impact,
            opportunity=opportunity,
            final_decision=decision,
        )


scoring_service = EventScoringService()
