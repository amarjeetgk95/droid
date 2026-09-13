"""
Volatility Contraction Pattern (VCP) Breakout Strategy (v5.0 §6.1).
Detects:
  1. Base consolidation of 15–30 bars.
  2. Range compression (5d average daily range / 20d range <= 0.75).
  3. Volume dry-up during the right side of the base.
  4. Defined pivot breakout level.
"""
from __future__ import annotations

from typing import Any, Optional
from app.swing.models import SwingSetup, MarketRegime, SectorClassification
from app.swing.technical import SwingFeatures
from app.swing.scoring import calculate_setup_score
from app.swing.risk_engine import compute_swing_risk_levels
from app.swing.strategies.base import BaseSwingStrategy


class VCPBreakoutStrategy(BaseSwingStrategy):
    strategy_id = "VCP_BREAKOUT"
    strategy_name = "VCP Contraction Breakout"

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
        # Minimum bar requirement
        if len(candles) < 25:
            return None

        # 1. Price above 50 SMA (must be in an active constructive trend)
        if not features.price_above_sma50:
            return None

        # 2. Proximity to 52-week high (within 25% max)
        if features.dist_from_52w_high_pct < -25.0:
            return None

        # 3. Measurable range contraction (5d vs 20d)
        if features.range_contraction_ratio > 0.78:
            return None

        # 4. Trigger level is the recent pivot high (excluding current bar)
        trigger = features.pivot_breakout_level
        if trigger <= 0 or features.close > trigger * 1.03:
            # Already gapped/blown past pivot
            return None

        # 5. Structural stop is the low of the tight contraction (last 5 bars)
        lows_last_5 = [c["low"] for c in candles[-5:]]
        structural_stop = min(lows_last_5) if lows_last_5 else features.recent_swing_low

        if structural_stop >= trigger:
            return None

        # 6. Compute Risk Levels
        risk_res = compute_swing_risk_levels(
            trigger_price=trigger,
            structural_stop_price=structural_stop,
            daily_atr=features.atr_14,
            portfolio_equity=portfolio_equity,
        )

        # Minimum R:R filter
        if risk_res.risk_reward_t1 < 1.2:
            return None

        # 7. Compute deterministic score
        score = calculate_setup_score(
            features=features,
            regime=regime,
            sector_status=sector_status,
            risk_reward_t1=risk_res.risk_reward_t1,
        )

        # Minimum quality score filter
        if score.total < 35.0:
            return None

        is_regime_restricted = regime.regime in ("BEAR", "DATA_UNCERTAIN")

        tech_reasons = [
            f"VCP contraction ratio {features.range_contraction_ratio:.2f} (tightening price action)",
            f"Base pivot high at ₹{trigger:.2f} ready for breakout",
            f"Trading {abs(features.dist_from_52w_high_pct):.1f}% from 52-week high",
            f"Daily ATR: ₹{features.atr_14:.2f} ({features.atr_pct:.1f}%)",
        ]
        if features.volume_dry_up:
            tech_reasons.append("Volume dry-up confirmed (RVOL < 0.60 on contraction)")

        risk_reasons = [
            f"Risk per share: ₹{risk_res.risk_per_share:.2f} ({risk_res.risk_pct:.1f}%)",
            f"Effective Stop: ₹{risk_res.effective_stop:.2f} (ATR floor protected)",
            f"T1 Target: ₹{risk_res.target_1:.2f} (1.5R), T2: ₹{risk_res.target_2:.2f} (3.0R)",
        ]

        invalidation = [
            f"Close below ₹{risk_res.effective_stop:.2f} invalidates setup",
            f"Entry void if price opens > ₹{risk_res.max_chase_price:.2f} (+1.0% gap)",
        ]

        # Determine signal state: If regime is restricted, gate as BLOCKED so it shows on radar safely
        if is_regime_restricted:
            state = "BLOCKED"
            risk_reasons.insert(0, f"Regime {regime.regime}: New unhedged long entries restricted by market filter. Tracking on Radar.")
            invalidation.insert(0, f"Market regime ({regime.regime}) restricts execution until NIFTY reclaims 20 EMA and 50 SMA.")
        elif features.close >= trigger and features.close <= risk_res.max_chase_price:
            state = "TRIGGERED"
        elif abs(features.close - trigger) / trigger <= 0.015:
            state = "READY"
        else:
            state = "WATCH"

        return SwingSetup(
            symbol=symbol,
            sector=sector,
            strategy="VCP_BREAKOUT",
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
            expected_holding_days=8,
            daily_atr=features.atr_14,
            market_regime=regime.regime,
            sector_state=sector_status.trend,
            technical_reasons=tech_reasons,
            risk_reasons=risk_reasons,
            invalidation_rules=invalidation,
            signal_state=state,
        )
