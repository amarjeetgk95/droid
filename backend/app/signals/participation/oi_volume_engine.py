"""
Dedicated Participation Engine (§18, §19, §57).
Decouples fast microstructure flow (Scalp Desk: CVD, Aggressor Imbalance, RVOL, Volume Acceleration)
from macro options/futures positioning (Intraday Desk: OI, ΔOI velocity, PCR, Option Walls).
Outputs standardized context: SUPPORTIVE | NEUTRAL | CONTRADICTORY + continuous participation score.
"""
from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

ParticipationState = Literal["SUPPORTIVE", "NEUTRAL", "CONTRADICTORY"]
DeskType = Literal["SCALP", "INTRADAY"]
TradeDirection = Literal["LONG_CALL", "LONG_PUT"]


class ParticipationContext(BaseModel):
    state: ParticipationState = "NEUTRAL"
    desk: DeskType = "INTRADAY"
    participation_score: float = 0.50     # 0.0 to 1.0
    
    # Volume components
    volume_state: str = "NORMAL"          # EXPANDING | NORMAL | DRYING_UP | SPIKE
    rvol: float = 1.0
    volume_acceleration: float = 0.0
    
    # Microstructure (Scalp primary)
    cvd_proxy: float = 0.0                # Cumulative Volume Delta estimate (-1.0 to 1.0)
    aggressor_imbalance: float = 0.0      # Estimated buyer/seller dominance (-1.0 to 1.0)
    
    # OI & F&O components (Intraday primary)
    oi_state: str = "NEUTRAL"             # RISING | FALLING | FLAT | UNWINDING
    positioning_state: str = "NEUTRAL"    # LONG_BUILDUP | SHORT_BUILDUP | SHORT_COVERING | LONG_UNWINDING
    oi_change_pct: float = 0.0
    pcr: Optional[float] = None
    max_pain: Optional[float] = None
    
    reasons: list[str] = Field(default_factory=list)


class ParticipationEngine:
    """
    Evaluates order flow and Open Interest participation according to desk-specific time horizons.
    """

    @staticmethod
    def classify_positioning(price_change_pct: float, oi_change_pct: float) -> str:
        """Standard 4-quadrant positioning interpretation (§57)."""
        if price_change_pct > 0.05 and oi_change_pct > 0.5:
            return "LONG_BUILDUP"
        elif price_change_pct < -0.05 and oi_change_pct > 0.5:
            return "SHORT_BUILDUP"
        elif price_change_pct > 0.05 and oi_change_pct < -0.5:
            return "SHORT_COVERING"
        elif price_change_pct < -0.05 and oi_change_pct < -0.5:
            return "LONG_UNWINDING"
        return "NEUTRAL"

    def evaluate(
        self,
        direction: TradeDirection,
        desk: DeskType,
        rvol: float,
        volume_acceleration: float,
        price_change_pct: float,
        fno_data: Optional[dict[str, Any]] = None,
        candles: Optional[list[dict]] = None,
    ) -> ParticipationContext:
        """
        Evaluates participation for the proposed direction and desk.
        """
        fno = fno_data or {}
        reasons: list[str] = []
        is_bullish = (direction == "LONG_CALL")

        # 1. Volume State
        vol_state = "NORMAL"
        if rvol >= 2.0:
            vol_state = "SPIKE"
        elif rvol >= 1.3:
            vol_state = "EXPANDING"
        elif rvol < 0.7:
            vol_state = "DRYING_UP"

        # 2. Microstructure / Aggressor estimate from candles
        aggressor_imb = 0.0
        cvd_estimate = 0.0
        if candles and len(candles) >= 3:
            # Estimate buying/selling volume proxy from candle body vs wick
            last_c = candles[-1]
            o = float(last_c.get("open", 0))
            h = float(last_c.get("high", 0))
            l = float(last_c.get("low", 0))
            c = float(last_c.get("close", 0))
            rng = max(0.01, h - l)
            # Body proportion and direction
            body_bias = (c - o) / rng
            aggressor_imb = round(body_bias, 3)
            # CVD proxy
            cvd_estimate = round(sum(((float(x.get("close", 0)) - float(x.get("open", 0))) / max(0.01, float(x.get("high", 0)) - float(x.get("low", 0)))) for x in candles[-5:]) / 5.0, 3)

        # 3. F&O Data
        oi_chg = float(fno.get("oi_change_pct", 0.0) or fno.get("futures_oi_change_pct", 0.0) or 0.0)
        pcr = float(fno.get("pcr", 1.0) or 1.0) if fno.get("pcr") is not None else None
        max_pain = float(fno.get("max_pain", 0.0) or 0.0) if fno.get("max_pain") is not None else None

        pos_state = self.classify_positioning(price_change_pct, oi_chg)
        oi_state = "FLAT"
        if oi_chg > 1.5:
            oi_state = "RISING"
        elif oi_chg < -1.5:
            oi_state = "FALLING"

        # 4. Desk-Specific Participation Evaluation
        if desk == "SCALP":
            # Scalp: Fast participation rules
            score = 0.50
            
            # Volume expansion helps scalps
            if vol_state in ("EXPANDING", "SPIKE"):
                score += 0.20
                reasons.append(f"Volume expanding (RVOL={rvol:.2f})")
            elif vol_state == "DRYING_UP":
                score -= 0.20
                reasons.append(f"Volume weak for scalp (RVOL={rvol:.2f})")

            # Acceleration
            if volume_acceleration > 0.20:
                score += 0.15
            elif volume_acceleration < -0.30:
                score -= 0.10

            # Aggressor alignment
            if is_bullish and aggressor_imb > 0.20:
                score += 0.15
                reasons.append(f"Aggressor buying ({aggressor_imb:+.2f})")
            elif not is_bullish and aggressor_imb < -0.20:
                score += 0.15
                reasons.append(f"Aggressor selling ({aggressor_imb:+.2f})")
            elif (is_bullish and aggressor_imb < -0.30) or (not is_bullish and aggressor_imb > 0.30):
                score -= 0.25
                reasons.append(f"Aggressor counter-flow ({aggressor_imb:+.2f})")

            score = max(0.0, min(1.0, score))

            if score >= 0.65:
                state: ParticipationState = "SUPPORTIVE"
            elif score <= 0.35:
                state = "CONTRADICTORY"
            else:
                state = "NEUTRAL"

        else:
            # Intraday: Combines Volume + OI / F&O context
            score = 0.50

            # Volume
            if vol_state in ("EXPANDING", "SPIKE"):
                score += 0.15
                reasons.append(f"Volume supportive (RVOL={rvol:.2f})")
            elif vol_state == "DRYING_UP":
                score -= 0.15
                reasons.append(f"Volume lack of interest (RVOL={rvol:.2f})")

            # OI positioning alignment
            if is_bullish:
                if pos_state in ("LONG_BUILDUP", "SHORT_COVERING"):
                    score += 0.20
                    reasons.append(f"F&O structure {pos_state}")
                elif pos_state in ("SHORT_BUILDUP", "LONG_UNWINDING"):
                    score -= 0.25
                    reasons.append(f"F&O positioning counter-trend ({pos_state})")
            else:
                if pos_state in ("SHORT_BUILDUP", "LONG_UNWINDING"):
                    score += 0.20
                    reasons.append(f"F&O structure {pos_state}")
                elif pos_state in ("LONG_BUILDUP", "SHORT_COVERING"):
                    score -= 0.25
                    reasons.append(f"F&O positioning counter-trend ({pos_state})")

            # PCR alignment
            if pcr is not None:
                if is_bullish and pcr >= 1.15:
                    score += 0.10
                    reasons.append(f"Bullish PCR ({pcr:.2f})")
                elif not is_bullish and pcr <= 0.85:
                    score += 0.10
                    reasons.append(f"Bearish PCR ({pcr:.2f})")

            score = max(0.0, min(1.0, score))

            if score >= 0.65:
                state = "SUPPORTIVE"
            elif score <= 0.35:
                state = "CONTRADICTORY"
            else:
                state = "NEUTRAL"

        return ParticipationContext(
            state=state,
            desk=desk,
            participation_score=round(score, 2),
            volume_state=vol_state,
            rvol=rvol,
            volume_acceleration=volume_acceleration,
            cvd_proxy=cvd_estimate,
            aggressor_imbalance=aggressor_imb,
            oi_state=oi_state,
            positioning_state=pos_state,
            oi_change_pct=oi_chg,
            pcr=pcr,
            max_pain=max_pain,
            reasons=reasons,
        )


participation_engine = ParticipationEngine()
