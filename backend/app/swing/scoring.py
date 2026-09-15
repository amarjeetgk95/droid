"""
Deterministic Setup Scoring Engine (v6.0 Options Overhaul).
Calculates an auditable 0-100 score across 12 objective options dimensions:
  1. Underlying Trend (0-15)
  2. Structure (0-10)
  3. Volume Confirmation (0-5)
  4. Expected Move vs Implied (0-10)
  5. IV Favorability (0-10)
  6. Greeks Quality (0-10)
  7. Theta Efficiency (0-5)
  8. Liquidity & Execution (0-10)
  9. Macro Regime Alignment (0-5)
  10. Risk/Reward (0-10)
  11. Portfolio Fit (0-5)
  12. DTE Adequacy (0-5)
Rule: score != probability.
"""
from __future__ import annotations

from typing import Literal
from app.swing.models import SetupScoreBreakdown, MarketRegime
from app.swing.technical import SwingFeatures


def calculate_setup_score(
    features: SwingFeatures,
    regime: MarketRegime,
    direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL",
    delta: float = 0.55,
    theta_drag_ratio: float = 12.0,
    iv_percentile: float = 40.0,
    iv_edge: float = 1.2,
    spread_pct: float = 1.0,
    open_interest: int = 5000,
    risk_reward_t1: float = 1.5,
    dte: int = 12,
    expected_holding_days: int = 7,
    has_same_underlying_position: bool = False,
) -> SetupScoreBreakdown:
    # 1. Underlying Trend (0-15)
    trend_pts = 0.0
    if direction == "LONG_CALL":
        if features.price_above_ema20:
            trend_pts += 5.0
        if features.price_above_sma50:
            trend_pts += 5.0
        if features.price_above_sma200:
            trend_pts += 3.0
        if features.sma200_slope_positive:
            trend_pts += 2.0
    else:  # LONG_PUT
        if not features.price_above_ema20:
            trend_pts += 5.0
        if not features.price_above_sma50:
            trend_pts += 5.0
        if not features.price_above_sma200:
            trend_pts += 3.0
        if not features.sma200_slope_positive:
            trend_pts += 2.0
    trend_pts = min(15.0, trend_pts)

    # 2. Structure (0-10)
    struct_pts = 0.0
    if features.range_contraction_ratio <= 0.75:
        struct_pts += 5.0
    elif features.range_contraction_ratio <= 0.85:
        struct_pts += 3.0

    if direction == "LONG_CALL":
        if features.dist_from_52w_high_pct >= -12.0:
            struct_pts += 3.0
    else:
        if features.dist_from_52w_high_pct <= -15.0:
            struct_pts += 3.0

    if features.daily_range_pct < features.avg_range_20d_pct:
        struct_pts += 2.0
    struct_pts = min(10.0, struct_pts)

    # 3. Volume Confirmation (0-5)
    vol_pts = 0.0
    if features.volume_dry_up:
        vol_pts += 5.0
    elif features.rvol >= 1.2:
        vol_pts += 4.0
    else:
        vol_pts += 2.0
    vol_pts = min(5.0, vol_pts)

    # 4. Expected Move vs Implied (0-10)
    move_pts = 0.0
    if iv_edge >= 1.5:
        move_pts = 10.0
    elif iv_edge >= 1.2:
        move_pts = 8.0
    elif iv_edge >= 1.0:
        move_pts = 6.0
    elif iv_edge >= 0.8:
        move_pts = 4.0
    else:
        move_pts = 2.0

    # 5. IV Favorability (0-10) (Lower IV percentile rewards long premium)
    iv_pts = 0.0
    if iv_percentile < 25.0:
        iv_pts = 10.0
    elif iv_percentile <= 50.0:
        iv_pts = 8.0
    elif iv_percentile <= 70.0:
        iv_pts = 5.0
    elif iv_percentile <= 85.0:
        iv_pts = 2.0
    else:
        iv_pts = 0.0  # Extreme IV is unfavorable for pure option buyers

    # 6. Greeks Quality (0-10) (Delta sweet spot: 0.50 - 0.70)
    greeks_pts = 0.0
    abs_delta = abs(delta)
    if 0.55 <= abs_delta <= 0.70:
        greeks_pts = 10.0
    elif 0.45 <= abs_delta <= 0.80:
        greeks_pts = 7.0
    elif 0.35 <= abs_delta:
        greeks_pts = 4.0
    else:
        greeks_pts = 1.0

    # 7. Theta Efficiency (0-5)
    theta_pts = 0.0
    if theta_drag_ratio <= 10.0:
        theta_pts = 5.0
    elif theta_drag_ratio <= 20.0:
        theta_pts = 3.0
    else:
        theta_pts = 1.0

    # 8. Liquidity & Execution Quality (0-10)
    liq_pts = 0.0
    if open_interest >= 5000:
        liq_pts += 5.0
    elif open_interest >= 1000:
        liq_pts += 3.0
    else:
        liq_pts += 1.0

    if spread_pct <= 1.0:
        liq_pts += 5.0
    elif spread_pct <= 2.0:
        liq_pts += 3.0
    elif spread_pct <= 2.5:
        liq_pts += 1.0
    liq_pts = min(10.0, liq_pts)

    # 9. Macro Regime Alignment (0-5)
    reg_pts = 2.0
    if direction == "LONG_CALL" and regime.regime == "BULL":
        reg_pts = 5.0
    elif direction == "LONG_PUT" and regime.regime == "BEAR":
        reg_pts = 5.0
    elif regime.regime == "NEUTRAL":
        reg_pts = 3.0

    # 10. Risk / Reward (0-10)
    rr_pts = 2.0
    if risk_reward_t1 >= 2.0:
        rr_pts = 10.0
    elif risk_reward_t1 >= 1.5:
        rr_pts = 8.0
    elif risk_reward_t1 >= 1.2:
        rr_pts = 5.0

    # 11. Portfolio Fit (0-5)
    fit_pts = 2.0 if has_same_underlying_position else 5.0

    # 12. DTE Adequacy (0-5)
    dte_pts = 1.0
    if dte >= expected_holding_days + 5:
        dte_pts = 5.0
    elif dte >= expected_holding_days + 3:
        dte_pts = 3.0

    total = round(
        trend_pts
        + struct_pts
        + vol_pts
        + move_pts
        + iv_pts
        + greeks_pts
        + theta_pts
        + liq_pts
        + reg_pts
        + rr_pts
        + fit_pts
        + dte_pts,
        1,
    )

    return SetupScoreBreakdown(
        trend=round(trend_pts, 1),
        structure=round(struct_pts, 1),
        volume=round(vol_pts, 1),
        expected_move=round(move_pts, 1),
        iv_favorability=round(iv_pts, 1),
        greeks_quality=round(greeks_pts, 1),
        theta_efficiency=round(theta_pts, 1),
        liquidity=round(liq_pts, 1),
        regime=round(reg_pts, 1),
        risk_reward=round(rr_pts, 1),
        portfolio_fit=round(fit_pts, 1),
        dte_adequacy=round(dte_pts, 1),
        total=min(100.0, max(0.0, total)),
        score_is_probability=False,
    )

