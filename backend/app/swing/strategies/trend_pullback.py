"""
20 EMA Trend Pullback Strategy (v5.0 §6.2).
Requirements:
  1. Established Stage 2 uptrend (Price > 50 SMA > 200 SMA or 50 SMA rising).
  2. Controlled pullback to the 20 EMA support zone.
  3. Pullback volume contraction (RVOL <= 1.10).
  4. Bullish reversal rejection of the 20 EMA.
"""
from __future__ import annotations

from typing import Any, Optional
from app.swing.models import SwingSetup, MarketRegime, SectorClassification
from app.swing.technical import SwingFeatures
from app.swing.scoring import calculate_setup_score
from app.swing.risk_engine import compute_swing_risk_levels
from app.swing.strategies.base import BaseSwingStrategy


class TrendPullbackStrategy(BaseSwingStrategy):
    strategy_id = "TREND_PULLBACK_20EMA"
    strategy_name = "20 EMA Trend Pullback"

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
        if len(candles) < 30 or features.ema_20 is None or features.sma_50 is None:
            return None

        # 1. Trend Filter: 50 SMA must be healthy
        if not features.price_above_sma50:
            return None

        # 2. Proximity to 20 EMA: Low touched or within 1.5% of 20 EMA
        ema20 = features.ema_20
        dist_to_ema20 = abs(features.low - ema20) / ema20
        if dist_to_ema20 > 0.025 and features.close < ema20:
            return None

        # 3. Pullback bar showed rejection (close near upper half of bar or above 20 EMA)
        bar_range = max(0.01, features.high - features.low)
        close_pos_in_bar = (features.close - features.low) / bar_range
        if close_pos_in_bar < 0.35:
            # Bearish close near low of bar: no reversal confirmation yet
            return None

        # 4. Volume check: Pullback should not be heavy institutional dumping
        if features.rvol > 1.4:
            return None

        # 5. Trigger is today's high (breakout above pullback bar)
        trigger = round(features.high, 2)
        structural_stop = round(min(c["low"] for c in candles[-3:]), 2)

        if structural_stop >= trigger:
            return None

        # 6. Risk levels
        risk_res = compute_swing_risk_levels(
            trigger_price=trigger,
            structural_stop_price=structural_stop,
            daily_atr=features.atr_14,
            portfolio_equity=portfolio_equity,
        )

        if risk_res.risk_reward_t1 < 1.2:
            return None

        # 7. Setup Score
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
            f"Pullback tested 20 EMA support at ₹{ema20:.2f}",
            f"Bullish wick/rejection: closed in upper {int(close_pos_in_bar * 100)}% of bar",
            f"Controlled volume on pullback (RVOL {features.rvol:.2f})",
            f"Trend intact: Price above 50 SMA (₹{features.sma_50:.2f})",
        ]

        risk_reasons = [
            f"Effective Stop: ₹{risk_res.effective_stop:.2f} (Structural low: ₹{risk_res.structural_stop:.2f})",
            f"Target 1: ₹{risk_res.target_1:.2f} (1.5R), Target 2: ₹{risk_res.target_2:.2f} (3.0R)",
            f"Risk per share: ₹{risk_res.risk_per_share:.2f}",
        ]

        invalidation = [
            f"Break below 20 EMA pullback low ₹{risk_res.effective_stop:.2f} invalidates setup",
            f"Void if opening gap exceeds ₹{risk_res.max_chase_price:.2f}",
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
            strategy="TREND_PULLBACK_20EMA",
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
            expected_holding_days=6,
            daily_atr=features.atr_14,
            market_regime=regime.regime,
            sector_state=sector_status.trend,
            technical_reasons=tech_reasons,
            risk_reasons=risk_reasons,
            invalidation_rules=invalidation,
            signal_state=state,
        )
