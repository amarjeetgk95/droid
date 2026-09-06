"""
Expected Move & Timing Engine (§8, §30, §32)
Calculates directional move magnitude, timing, and velocity across multi-horizons:
  - SCALP (1m - 15m)
  - INTRADAY (15m - EOD, 1 - 4 hours)
  - SWING (1 - 3 days)
  - POSITIONAL (5 - 10 days)

Core Institutional Invariant (§8):
  Distinguishes between "large move eventually" vs "large move quickly enough for option buying",
  measuring expected price velocity against option theta decay drag.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field


TradingHorizon = Literal["SCALP", "INTRADAY", "SWING", "POSITIONAL"]
DirectionalBias = Literal["BULLISH", "BEARISH", "NEUTRAL"]


class HorizonParameters(BaseModel):
    horizon: TradingHorizon
    duration_hours: float
    typical_bars: int
    atr_timeframe: str
    target_multiple_atr: float
    min_velocity_threshold_pts_per_hr: float


DEFAULT_HORIZON_CONFIGS: dict[str, dict[TradingHorizon, HorizonParameters]] = {
    "NIFTY": {
        "SCALP": HorizonParameters(
            horizon="SCALP",
            duration_hours=0.33,  # 20 minutes
            typical_bars=20,
            atr_timeframe="1M",
            target_multiple_atr=1.8,
            min_velocity_threshold_pts_per_hr=45.0,
        ),
        "INTRADAY": HorizonParameters(
            horizon="INTRADAY",
            duration_hours=2.5,   # 2.5 hours
            typical_bars=30,
            atr_timeframe="5M",
            target_multiple_atr=2.2,
            min_velocity_threshold_pts_per_hr=18.0,
        ),
        "SWING": HorizonParameters(
            horizon="SWING",
            duration_hours=12.5,  # 2 trading sessions (6.25h each)
            typical_bars=2,
            atr_timeframe="1D",
            target_multiple_atr=1.5,
            min_velocity_threshold_pts_per_hr=10.0,
        ),
        "POSITIONAL": HorizonParameters(
            horizon="POSITIONAL",
            duration_hours=37.5,  # 6 trading sessions
            typical_bars=6,
            atr_timeframe="1D",
            target_multiple_atr=2.5,
            min_velocity_threshold_pts_per_hr=5.0,
        ),
    },
    "BANKNIFTY": {
        "SCALP": HorizonParameters(
            horizon="SCALP",
            duration_hours=0.33,
            typical_bars=20,
            atr_timeframe="1M",
            target_multiple_atr=1.8,
            min_velocity_threshold_pts_per_hr=140.0,
        ),
        "INTRADAY": HorizonParameters(
            horizon="INTRADAY",
            duration_hours=2.5,
            typical_bars=30,
            atr_timeframe="5M",
            target_multiple_atr=2.2,
            min_velocity_threshold_pts_per_hr=65.0,
        ),
        "SWING": HorizonParameters(
            horizon="SWING",
            duration_hours=12.5,
            typical_bars=2,
            atr_timeframe="1D",
            target_multiple_atr=1.5,
            min_velocity_threshold_pts_per_hr=35.0,
        ),
        "POSITIONAL": HorizonParameters(
            horizon="POSITIONAL",
            duration_hours=37.5,
            typical_bars=6,
            atr_timeframe="1D",
            target_multiple_atr=2.5,
            min_velocity_threshold_pts_per_hr=18.0,
        ),
    },
    "SENSEX": {
        "SCALP": HorizonParameters(
            horizon="SCALP",
            duration_hours=0.33,
            typical_bars=20,
            atr_timeframe="1M",
            target_multiple_atr=1.8,
            min_velocity_threshold_pts_per_hr=200.0,
        ),
        "INTRADAY": HorizonParameters(
            horizon="INTRADAY",
            duration_hours=2.5,
            typical_bars=30,
            atr_timeframe="5M",
            target_multiple_atr=2.2,
            min_velocity_threshold_pts_per_hr=90.0,
        ),
        "SWING": HorizonParameters(
            horizon="SWING",
            duration_hours=12.5,
            typical_bars=2,
            atr_timeframe="1D",
            target_multiple_atr=1.5,
            min_velocity_threshold_pts_per_hr=50.0,
        ),
        "POSITIONAL": HorizonParameters(
            horizon="POSITIONAL",
            duration_hours=37.5,
            typical_bars=6,
            atr_timeframe="1D",
            target_multiple_atr=2.5,
            min_velocity_threshold_pts_per_hr=25.0,
        ),
    },
}


class ExpectedMoveProjection(BaseModel):
    underlying: str
    horizon: TradingHorizon
    direction: DirectionalBias
    spot_price: float
    expected_move_points: float = Field(..., description="Projected magnitude of move in underlying points")
    expected_move_pct: float = Field(..., description="Projected move as percentage of spot price")
    conservative_move_points: float = Field(..., description="Minimum reliable target move (T1)")
    aggressive_move_points: float = Field(..., description="Extended momentum target move (T2)")
    iv_implied_1sigma_move: float = Field(..., description="1-Standard Deviation move implied by IV over horizon")
    atr_excursion_points: float = Field(..., description="Volatility-based excursion from ATR")
    expected_duration_hours: float = Field(..., description="Expected time required to reach target in trading hours")
    expected_velocity_pts_per_hour: float = Field(..., description="Expected price movement speed in points/hour")
    
    # Velocity vs Theta Analysis (§8)
    is_fast_enough_for_option: bool = Field(..., description="True if velocity comfortably outpaces theta decay")
    velocity_assessment: str = Field(..., description="Institutional verdict on move speed vs option theta")
    calibration_confidence: float = Field(..., description="Model calibration confidence (0-100)")
    forecast_rationale: list[str] = Field(default_factory=list)


class ExpectedMoveEngine:
    """
    Quantitative Expected Move & Timing Engine.
    Synthesizes IV-implied volatility distribution, multi-timeframe ATR,
    and market structure levels to predict move magnitude and time requirements.
    """

    ANNUAL_TRADING_HOURS = 252.0 * 6.25  # 1,575 market trading hours per year

    def __init__(self, horizon_configs: Optional[dict] = None):
        self.configs = horizon_configs or DEFAULT_HORIZON_CONFIGS

    def calculate_iv_implied_move(
        self,
        spot: float,
        iv: float,
        duration_hours: float,
    ) -> float:
        """
        Calculates 1-sigma expected move from Implied Volatility:
          Move = Spot * IV * sqrt(t_years)
        """
        if spot <= 0 or iv <= 0 or duration_hours <= 0:
            return 0.0
        t_years = duration_hours / self.ANNUAL_TRADING_HOURS
        return spot * iv * math.sqrt(t_years)

    def project_move(
        self,
        underlying: str,
        spot: float,
        direction: DirectionalBias,
        horizon: TradingHorizon = "INTRADAY",
        current_iv: float = 0.15,
        atr: Optional[float] = None,
        structural_target: Optional[float] = None,
        regime: str = "TREND_UP",
        hourly_theta_decay: Optional[float] = None,
    ) -> ExpectedMoveProjection:
        """
        Generates comprehensive expected move projection for underlying instrument.
        """
        u = underlying.upper()
        if spot <= 0:
            raise ValueError("Spot price must be positive and non-zero")
        inst_configs = self.configs.get(u, self.configs["NIFTY"])
        params = inst_configs.get(horizon, inst_configs["INTRADAY"])

        duration_hours = params.duration_hours

        # 1. IV-Implied Move (1 Sigma)
        iv_move = self.calculate_iv_implied_move(spot, current_iv, duration_hours)

        # 2. ATR-Based Excursion
        if atr is None or atr <= 0:
            # Fallback baseline ATR
            if u == "BANKNIFTY":
                atr_val = 55.0 if horizon in ("SCALP", "INTRADAY") else 380.0
            elif u == "SENSEX":
                atr_val = 85.0 if horizon in ("SCALP", "INTRADAY") else 600.0
            else:
                atr_val = 22.0 if horizon in ("SCALP", "INTRADAY") else 150.0
        else:
            atr_val = atr

        # Regime adjustment factor
        r_upper = regime.upper()
        if "TREND" in r_upper or "BREAKOUT" in r_upper:
            regime_mult = 1.25
        elif "RANGE" in r_upper or "LOW_VOL" in r_upper:
            regime_mult = 0.80
        elif "HIGH_VOL" in r_upper:
            regime_mult = 1.35
        else:
            regime_mult = 1.0

        atr_move = atr_val * params.target_multiple_atr * regime_mult

        # 3. Structural target integration (if provided by strategy price level)
        if structural_target is not None and structural_target > 0:
            struct_diff = abs(structural_target - spot)
            # Weighted blend: 50% structural, 30% ATR, 20% IV
            blended_move = (struct_diff * 0.50) + (atr_move * 0.30) + (iv_move * 0.20)
        else:
            # Weighted blend: 65% ATR excursion, 35% IV-implied move
            blended_move = (atr_move * 0.65) + (iv_move * 0.35)

        blended_move = max(atr_val * 0.8, blended_move)
        expected_move_pts = round(blended_move, 2)
        expected_move_pct = round((expected_move_pts / spot * 100.0), 2) if spot > 0 else 0.0

        conservative_pts = round(expected_move_pts * 0.70, 2)
        aggressive_pts = round(expected_move_pts * 1.45, 2)

        # 4. Velocity Calculation (Points per Hour)
        velocity_pts_per_hr = round(expected_move_pts / duration_hours, 2) if duration_hours > 0 else 0.0

        # 5. Velocity vs Option Theta Decoupling (§8)
        # Check if move speed outpaces option theta
        is_fast_enough = True
        rationale: list[str] = []

        if velocity_pts_per_hr < params.min_velocity_threshold_pts_per_hr:
            is_fast_enough = False
            assessment = f"TOO_SLOW_FOR_OPTION: Projected velocity ({velocity_pts_per_hr:.1f} pts/hr) below minimum threshold ({params.min_velocity_threshold_pts_per_hr:.1f} pts/hr)"
            rationale.append(assessment)
        else:
            assessment = f"FAST_EXPANSION: Projected velocity ({velocity_pts_per_hr:.1f} pts/hr) supports option buying"
            rationale.append(assessment)

        if hourly_theta_decay is not None and hourly_theta_decay > 0:
            # Approximate ATM delta ~0.50
            delta_gain_per_hr = velocity_pts_per_hr * 0.50
            theta_velocity_ratio = delta_gain_per_hr / hourly_theta_decay if hourly_theta_decay > 0 else 10.0
            if theta_velocity_ratio < 1.5:
                is_fast_enough = False
                assessment = f"THETA_BLEED_RISK: Velocity gain (₹{delta_gain_per_hr:.1f}/hr) fails to comfortably exceed theta (₹{hourly_theta_decay:.1f}/hr)"
                rationale.append(assessment)
            else:
                rationale.append(f"Velocity cushion healthy: {theta_velocity_ratio:.1f}x theta decay rate")

        confidence = 75.0
        if "TREND" in r_upper:
            confidence += 8.0
        elif "RANGE" in r_upper and horizon != "SCALP":
            confidence -= 12.0

        rationale.append(f"Horizon {horizon} ({duration_hours:.2f}h) target: ±{expected_move_pts} pts (T1: ±{conservative_pts}, T2: ±{aggressive_pts})")
        rationale.append(f"IV 1-sigma move: {iv_move:.1f} pts ({current_iv*100.0:.1f}% IV), ATR excursion: {atr_move:.1f} pts")

        return ExpectedMoveProjection(
            underlying=u,
            horizon=horizon,
            direction=direction,
            spot_price=spot,
            expected_move_points=expected_move_pts,
            expected_move_pct=expected_move_pct,
            conservative_move_points=conservative_pts,
            aggressive_move_points=aggressive_pts,
            iv_implied_1sigma_move=round(iv_move, 2),
            atr_excursion_points=round(atr_move, 2),
            expected_duration_hours=round(duration_hours, 2),
            expected_velocity_pts_per_hour=velocity_pts_per_hr,
            is_fast_enough_for_option=is_fast_enough,
            velocity_assessment=assessment,
            calibration_confidence=min(95.0, max(40.0, confidence)),
            forecast_rationale=rationale,
        )


# Global singleton
expected_move_engine = ExpectedMoveEngine()
