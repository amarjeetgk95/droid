"""
Orthogonal Confluence Engine (§23, §24, §25).
Evaluates candidate setups against three orthogonal vectors:
  1. Structural Integrity (Price action, S/R, VWAP alignment, swing geometry)
  2. Kinetic Force (Momentum, ROC, price acceleration, RSI/MACD velocity)
  3. Participation (Scalp: RVOL, CVD, Aggressor flow / Intraday: Volume, OI, ΔOI, PCR)

Eliminates scalp latency by evaluating pre-calculated feature snapshots in <0.1ms.
"""
from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

from app.signals.strategies.base import SignalCandidate, TradeDirection
from app.signals.features.engine import FeatureSnapshot
from app.signals.participation.oi_volume_engine import ParticipationContext

ConfluenceStatus = Literal["SUPPORTIVE", "NEUTRAL", "CONTRADICTORY"]


class OrthogonalConfluenceResult(BaseModel):
    confluence_score: float = 50.0        # 0.0 to 100.0
    status: ConfluenceStatus = "NEUTRAL"
    passed: bool = True
    
    # 3 Orthogonal Vectors (each 0-100)
    structural_score: float = 50.0
    kinetic_score: float = 50.0
    participation_score: float = 50.0
    
    # Confirmed independent factors
    confirmed_factors: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    
    # Position Sizing Multiplier (Class B Continuous Modulation: 0.5x to 1.25x)
    sizing_multiplier: float = 1.0


# P0-2: only a strong, unanimous tape arms. A 72 bar let marginal
# chop through as SUPPORTIVE; 78 matches the confluence ARMED bar.
SUPPORTIVE_BAR = 78.0
# Below 60 there is no edge to size — the setup is blocked, not halved.
SIZING_BLOCK_LEVEL = 60.0


class OrthogonalConfluenceEngine:
    """
    Evaluates independent multi-domain confluence for any strategy candidate.
    Fail-closed (P0-2): missing features/participation, NEUTRAL verdicts and
    sub-60 scores all BLOCK — there is no 0.5x consolation size for no-edge.
    """

    def evaluate(
        self,
        candidate: SignalCandidate,
        features: Optional[FeatureSnapshot] = None,
        participation: Optional[ParticipationContext] = None,
    ) -> OrthogonalConfluenceResult:
        # P0-2 FAIL-CLOSE: unevaluated vectors are contradictory, not neutral.
        if features is None or participation is None:
            missing = []
            if features is None:
                missing.append("features=None")
            if participation is None:
                missing.append("participation=None")
            return OrthogonalConfluenceResult(
                confluence_score=0.0,
                status="CONTRADICTORY",
                passed=False,
                structural_score=0.0,
                kinetic_score=0.0,
                participation_score=0.0,
                confirmed_factors=[],
                rejection_reasons=[f"ORTHO_UNEVALUATED_{'_'.join(missing)}"],
                sizing_multiplier=0.0,
            )
        is_bullish = (candidate.direction == "LONG_CALL")
        is_scalp = candidate.is_scalp or candidate.timeframe in ("1M", "3M")
        spot = float(candidate.spot_price)

        struct_score = 50.0
        kinetic_score = 50.0
        part_score = 50.0
        factors: list[str] = []
        reasons: list[str] = []

        # ── 1. STRUCTURAL VECTOR ──
        if features:
            s = features.structure
            e = features.ema

            if is_bullish:
                # VWAP relationship
                if features.vwap and spot >= features.vwap:
                    struct_score += 15.0
                    factors.append("Price >= VWAP")
                elif features.vwap and candidate.strategy == "VWAP_SCALP":
                    # Mean reversion into VWAP is structurally valid
                    struct_score += 15.0
                    factors.append("Mean reversion toward VWAP")

                # Swing & Trend Structure
                if s.structure_type == "HH_HL" or s.trend_bias == "BULLISH":
                    struct_score += 15.0
                    factors.append("Bullish Market Structure (HH_HL)")
                elif s.structure_type == "LH_LL":
                    struct_score -= 15.0
                    reasons.append("Counter-structure: Bearish LH_LL")

                # EMA Alignment
                if e.is_bullish_ordered:
                    struct_score += 10.0
                    factors.append("EMA Ribbon Bullish")
                elif e.is_bearish_ordered and candidate.strategy not in ("MEAN_REVERSION", "VWAP_SCALP"):
                    struct_score -= 10.0
            else:
                # Bearish structural checks
                if features.vwap and spot <= features.vwap:
                    struct_score += 15.0
                    factors.append("Price <= VWAP")
                elif features.vwap and candidate.strategy == "VWAP_SCALP":
                    struct_score += 15.0
                    factors.append("Mean reversion toward VWAP")

                if s.structure_type == "LH_LL" or s.trend_bias == "BEARISH":
                    struct_score += 15.0
                    factors.append("Bearish Market Structure (LH_LL)")
                elif s.structure_type == "HH_HL":
                    struct_score -= 15.0
                    reasons.append("Counter-structure: Bullish HH_HL")

                if e.is_bearish_ordered:
                    struct_score += 10.0
                    factors.append("EMA Ribbon Bearish")
                elif e.is_bullish_ordered and candidate.strategy not in ("MEAN_REVERSION", "VWAP_SCALP"):
                    struct_score -= 10.0

        struct_score = max(0.0, min(100.0, struct_score))

        # ── 2. KINETIC VECTOR (P0-2: ATR-normalized ROC_3 gate) ──
        # A fixed 0.05% ROC is noise on a 60pt-ATR day and a mountain on a
        # 6pt-ATR day. Normalize: require |ROC_3| > max(0.05%, 0.5*ATR%).
        try:
            _atr = float(getattr(features, "atr", 0.0) or 0.0)
        except Exception:
            _atr = 0.0
        try:
            _atr_pct = (_atr / spot * 100.0) if spot > 0 and _atr > 0 else 0.0
        except Exception:
            _atr_pct = 0.0
        _roc_gate = max(0.05, 0.5 * _atr_pct)
        if features:
            if is_bullish:
                if features.roc_1 > 0:
                    kinetic_score += 10.0
                if features.roc_3 > _roc_gate:
                    kinetic_score += 15.0
                    factors.append(f"Positive 3-bar ROC (+{features.roc_3:.2f}% > {_roc_gate:.3f}% ATR-gate)")
                if features.momentum_acceleration > 0:
                    kinetic_score += 10.0
                    factors.append("Momentum accelerating")
                if features.rsi is not None and 50 <= features.rsi <= 75:
                    kinetic_score += 10.0
                elif features.rsi is not None and features.rsi > 82:
                    kinetic_score -= 15.0
                    reasons.append("RSI overbought exhaustion")
            else:
                if features.roc_1 < 0:
                    kinetic_score += 10.0
                if features.roc_3 < -_roc_gate:
                    kinetic_score += 15.0
                    factors.append(f"Negative 3-bar ROC ({features.roc_3:.2f}% < -{_roc_gate:.3f}% ATR-gate)")
                if features.momentum_acceleration < 0:
                    kinetic_score += 10.0
                    factors.append("Momentum accelerating downward")
                if features.rsi is not None and 25 <= features.rsi <= 50:
                    kinetic_score += 10.0
                elif features.rsi is not None and features.rsi < 18:
                    kinetic_score -= 15.0
                    reasons.append("RSI oversold exhaustion")

        kinetic_score = max(0.0, min(100.0, kinetic_score))

        # ── 3. PARTICIPATION VECTOR ──
        if participation:
            part_score = participation.participation_score * 100.0
            if participation.state == "SUPPORTIVE":
                factors.extend(participation.reasons[:2])
            elif participation.state == "CONTRADICTORY":
                reasons.extend(participation.reasons[:2])

        # Overall Confluence Score: Weighted across 3 Orthogonal Domains
        # Structure (40%) + Kinetic (35%) + Participation (25%)
        overall = round(
            0.40 * struct_score + 0.35 * kinetic_score + 0.25 * part_score,
            1
        )

        status: ConfluenceStatus = "NEUTRAL"
        if overall >= SUPPORTIVE_BAR and (not reasons or len(factors) >= 2):
            status = "SUPPORTIVE"
        elif overall <= 35.0 or len(reasons) >= 3:
            status = "CONTRADICTORY"

        # Continuous Sizing Multiplier (Section 62) — P0-2 FAIL-CLOSE:
        # sub-60 is BLOCKED (0.0x, passed=False), never a 0.5x consolation.
        # NEUTRAL also blocks: only SUPPORTIVE may arm.
        sizing = 1.0
        if overall >= 80.0:
            sizing = 1.25  # A+ setup
        elif overall >= 68.0:
            sizing = 1.0   # Standard setup
        elif overall >= SIZING_BLOCK_LEVEL:
            sizing = 0.75  # Moderate setup
        else:
            sizing = 0.0   # BLOCKED — no edge to size
            if "SIZING_BLOCK_BELOW_60" not in reasons:
                reasons.append(f"SIZING_BLOCK_BELOW_60_{overall:.1f}")

        passed = (status == "SUPPORTIVE") and (overall >= SIZING_BLOCK_LEVEL)
        if status == "NEUTRAL" and passed:
            passed = False
        if overall < SIZING_BLOCK_LEVEL:
            passed = False
            if status != "CONTRADICTORY":
                status = "CONTRADICTORY"

        return OrthogonalConfluenceResult(
            confluence_score=overall,
            status=status,
            passed=passed,
            structural_score=round(struct_score, 1),
            kinetic_score=round(kinetic_score, 1),
            participation_score=round(part_score, 1),
            confirmed_factors=factors,
            rejection_reasons=reasons,
            sizing_multiplier=sizing,
        )


orthogonal_confluence_engine = OrthogonalConfluenceEngine()
