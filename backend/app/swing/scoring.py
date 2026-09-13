"""
Deterministic Setup Scoring Engine (v5.0 §11).
Calculates an auditable 0-100 score across 8 objective dimensions:
  1. Trend (0-20)
  2. Structure (0-15)
  3. Volume (0-15)
  4. Relative Strength (0-10)
  5. Sector Momentum (0-10)
  6. Market Regime (0-15)
  7. Risk/Reward (0-10)
  8. Liquidity (0-5)
Rule: score != probability.
"""
from __future__ import annotations

from app.swing.models import SetupScoreBreakdown, MarketRegime, SectorClassification
from app.swing.technical import SwingFeatures


def calculate_setup_score(
    features: SwingFeatures,
    regime: MarketRegime,
    sector_status: SectorClassification,
    risk_reward_t1: float,
    turnover_cr: float = 50.0,
) -> SetupScoreBreakdown:
    # 1. Trend (0-20)
    # Price > 20 EMA, 50 SMA, 200 SMA + positive 200 slope
    trend_pts = 0.0
    if features.price_above_ema20:
        trend_pts += 6.0
    if features.price_above_sma50:
        trend_pts += 6.0
    if features.price_above_sma200:
        trend_pts += 5.0
    if features.sma200_slope_positive:
        trend_pts += 3.0
    trend_pts = min(20.0, trend_pts)

    # 2. Structure (0-15)
    # Range contraction, proximity to 52w high, clean pivot
    struct_pts = 0.0
    if features.range_contraction_ratio <= 0.70:
        struct_pts += 7.0
    elif features.range_contraction_ratio <= 0.85:
        struct_pts += 4.0

    if features.dist_from_52w_high_pct >= -15.0:  # Within 15% of 52w high
        struct_pts += 5.0
    elif features.dist_from_52w_high_pct >= -25.0:
        struct_pts += 3.0

    if features.daily_range_pct < features.avg_range_20d_pct:
        struct_pts += 3.0
    struct_pts = min(15.0, struct_pts)

    # 3. Volume (0-15)
    vol_pts = 0.0
    if features.volume_dry_up:
        # Pre-breakout volume dry up is a huge plus
        vol_pts += 10.0
    elif features.rvol >= 1.5:
        # Breakout volume surge
        vol_pts += 15.0
    elif features.rvol >= 1.1:
        vol_pts += 10.0
    else:
        vol_pts += 5.0
    vol_pts = min(15.0, vol_pts)

    # 4. Relative Strength vs Nifty (0-10)
    rs_pts = 5.0
    if features.dist_from_52w_high_pct > -10.0:
        rs_pts += 5.0
    elif features.dist_from_52w_high_pct > -20.0:
        rs_pts += 3.0
    rs_pts = min(10.0, rs_pts)

    # 5. Sector Momentum (0-10)
    sec_pts = 5.0
    if sector_status.trend == "LEADING":
        sec_pts = 10.0
    elif sector_status.trend == "IMPROVING":
        sec_pts = 8.0
    elif sector_status.trend == "NEUTRAL":
        sec_pts = 5.0
    elif sector_status.trend == "WEAKENING":
        sec_pts = 2.0
    elif sector_status.trend == "LAGGING":
        sec_pts = 0.0

    # 6. Market Regime (0-15)
    reg_pts = 5.0
    if regime.regime == "BULL":
        reg_pts = 15.0
    elif regime.regime == "NEUTRAL":
        reg_pts = 10.0
    elif regime.regime == "DISTRIBUTION":
        reg_pts = 5.0
    elif regime.regime in ("BEAR", "HIGH_VOLATILITY", "DATA_UNCERTAIN"):
        reg_pts = 0.0

    # 7. Risk / Reward (0-10)
    rr_pts = 0.0
    if risk_reward_t1 >= 2.0:
        rr_pts = 10.0
    elif risk_reward_t1 >= 1.5:
        rr_pts = 8.0
    elif risk_reward_t1 >= 1.2:
        rr_pts = 5.0
    else:
        rr_pts = 2.0

    # 8. Liquidity (0-5)
    liq_pts = 5.0 if turnover_cr >= 25.0 else 3.0

    total = round(trend_pts + struct_pts + vol_pts + rs_pts + sec_pts + reg_pts + rr_pts + liq_pts, 1)

    return SetupScoreBreakdown(
        trend=round(trend_pts, 1),
        structure=round(struct_pts, 1),
        volume=round(vol_pts, 1),
        relative_strength=round(rs_pts, 1),
        sector=round(sec_pts, 1),
        regime=round(reg_pts, 1),
        risk_reward=round(rr_pts, 1),
        liquidity=round(liq_pts, 1),
        total=min(100.0, max(0.0, total)),
        score_is_probability=False,
    )
