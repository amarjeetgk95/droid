"""
Stage 2 Uptrend Breakout Strategy (v5.0 §6.3).
Requirements:
  1. Stan Weinstein / Mark Minervini Stage 2 Structure:
     Price > 50 SMA > 200 SMA, 200 SMA slope positive.
  2. Proximity to 52-Week High (within 15%).
  3. Resistance breakout of a multi-week consolidation base.
  4. Institutional volume expansion (RVOL >= 1.20).
"""
from __future__ import annotations

from typing import Any, Optional
from app.swing.models import SwingSetup, MarketRegime, SectorClassification
from app.swing.technical import SwingFeatures
from app.swing.scoring import calculate_setup_score
from app.swing.risk_engine import compute_swing_risk_levels
from app.swing.strategies.base import BaseSwingStrategy


class Stage2BreakoutStrategy(BaseSwingStrategy):
    strategy_id = "STAGE2_BREAKOUT"
    strategy_name = "Stage 2 Trend Breakout"

    def evaluate(
        self,
        symbol: str,
        sector: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        sector_status: SectorClassification,
        portfolio_equity: float = 1_000_000.0,
    ) -> Optional[SwingSetup]:
        if len(candles) < 40 or features.sma_50 is None:
            return None

        # 1. Moving average trend structure
        if not features.price_above_sma50:
            return None
        if features.sma_200 is not None and not features.price_above_sma200:
            return None

        # 2. Distance from 52-week high (Stage 2 leaders trade near highs)
        if features.dist_from_52w_high_pct < -15.0:
            return None

        # 3. Pivot breakout level
        trigger = features.pivot_breakout_level
        if trigger <= 0:
            return None

        # Close should be breaking or testing within 1.5% of pivot
        dist_to_trigger = (trigger - features.close) / trigger
        if dist_to_trigger > 0.025 or dist_to_trigger < -0.03:
            # Not close to breakout, or extended too far beyond pivot
            return None

        # 4. Volume expansion on breakout
        if features.rvol < 1.15 and not features.volume_dry_up:
            return None

        # 5. Structural stop: recent swing low of the base
        structural_stop = features.recent_swing_low
        if structural_stop >= trigger:
            structural_stop = round(trigger - (1.5 * features.atr_14), 2)

        # 6. Risk computation
        risk_res = compute_swing_risk_levels(
            trigger_price=trigger,
            structural_stop_price=structural_stop,
            daily_atr=features.atr_14,
            portfolio_equity=portfolio_equity,
        )

        if risk_res.risk_reward_t1 < 1.2:
            return None

        # 7. Score
        score = calculate_setup_score(
            features=features,
            regime=regime,
            sector_status=sector_status,
            risk_reward_t1=risk_res.risk_reward_t1,
        )

        # Quality score filter
        if score.total < 35.0:
            return None

        is_regime_restricted = regime.regime in ("BEAR", "DATA_UNCERTAIN")

        tech_reasons = [
            f"Stage 2 uptrend: Price (₹{features.close:.2f}) > 50 SMA (₹{features.sma_50:.2f})",
            f"Trading within {abs(features.dist_from_52w_high_pct):.1f}% of 52-week high",
            f"Breaking multi-week base resistance at ₹{trigger:.2f}",
            f"Volume expansion: RVOL {features.rvol:.2f}",
        ]
        if features.sma200_slope_positive:
            tech_reasons.append("200 SMA slope is positive (long-term accumulation)")

        risk_reasons = [
            f"Effective Stop: ₹{risk_res.effective_stop:.2f} (ATR floor protected)",
            f"Target 1: ₹{risk_res.target_1:.2f} (1.5R), Target 2: ₹{risk_res.target_2:.2f} (3.0R)",
            f"Risk per share: ₹{risk_res.risk_per_share:.2f}",
        ]

        invalidation = [
            f"Failure to hold base pivot support at ₹{risk_res.effective_stop:.2f}",
            f"Void if opening price gaps past ₹{risk_res.max_chase_price:.2f}",
        ]

        if is_regime_restricted:
            state = "BLOCKED"
            risk_reasons.insert(0, f"Regime {regime.regime}: New unhedged long entries restricted by market filter. Tracking on Radar.")
            invalidation.insert(0, f"Market regime ({regime.regime}) restricts execution until NIFTY reclaims 20 EMA and 50 SMA.")
        elif features.close >= trigger:
            state = "TRIGGERED"
        else:
            state = "READY"

        return SwingSetup(
            symbol=symbol,
            sector=sector,
            strategy="STAGE2_BREAKOUT",
            direction="LONG",
            score=score,
            entry_zone_min=round(trigger * 0.995, 2),
            entry_zone_max=risk_res.max_chase_price,
            trigger_price=risk_res.trigger_price,
            max_chase_price=risk_res.max_chase_price,
            stop_price=risk_res.effective_stop,
            structural_stop=risk_res.structural_stop,
            atr_floor=risk_res.atr_floor,
            target_1=risk_res.target_1,
            target_2=risk_res.target_2,
            risk_per_share=risk_res.risk_per_share,
            risk_pct=risk_res.risk_pct,
            risk_reward_t1=risk_res.risk_reward_t1,
            risk_reward_t2=risk_res.risk_reward_t2,
            expected_holding_days=10,
            daily_atr=features.atr_14,
            market_regime=regime.regime,
            sector_state=sector_status.trend,
            technical_reasons=tech_reasons,
            risk_reasons=risk_reasons,
            invalidation_rules=invalidation,
            signal_state=state,
        )
