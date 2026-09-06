import pytest
from app.signals.expected_move import (
    ExpectedMoveEngine,
    expected_move_engine,
    ExpectedMoveProjection,
)
from app.signals.options_intelligence.selector import QuantitativeContractSelector


class TestExpectedMoveEngine:
    def test_iv_implied_move_scaling(self):
        engine = ExpectedMoveEngine()
        spot = 25000.0
        iv = 0.15

        move_1h = engine.calculate_iv_implied_move(spot, iv, duration_hours=1.0)
        move_4h = engine.calculate_iv_implied_move(spot, iv, duration_hours=4.0)

        # sqrt(4) = 2x scaling
        assert abs(move_4h - (move_1h * 2.0)) < 0.5, f"Expected 2x scaling: {move_1h} vs {move_4h}"

    def test_multi_horizon_projections(self):
        engine = ExpectedMoveEngine()
        spot = 24900.0

        scalp = engine.project_move(
            underlying="NIFTY",
            spot=spot,
            direction="BULLISH",
            horizon="SCALP",
            current_iv=0.14,
            atr=18.0,
            regime="TREND_UP",
        )
        assert scalp.horizon == "SCALP"
        assert scalp.expected_duration_hours <= 0.5
        assert scalp.expected_move_points > 20.0
        assert scalp.expected_velocity_pts_per_hour >= 45.0
        assert scalp.is_fast_enough_for_option is True

        intraday = engine.project_move(
            underlying="NIFTY",
            spot=spot,
            direction="BULLISH",
            horizon="INTRADAY",
            current_iv=0.14,
            atr=22.0,
            regime="TREND_UP",
        )
        assert intraday.horizon == "INTRADAY"
        assert intraday.expected_duration_hours == 2.5
        assert intraday.expected_move_points > scalp.expected_move_points

        swing = engine.project_move(
            underlying="NIFTY",
            spot=spot,
            direction="BULLISH",
            horizon="SWING",
            current_iv=0.14,
            atr=140.0,
        )
        assert swing.horizon == "SWING"
        assert swing.expected_duration_hours > intraday.expected_duration_hours
        assert swing.expected_move_points > intraday.expected_move_points

    def test_velocity_vs_theta_decoupling_fast_vs_slow(self):
        engine = ExpectedMoveEngine()
        spot = 24900.0

        # High velocity breakout move:
        fast_proj = engine.project_move(
            underlying="NIFTY",
            spot=spot,
            direction="BULLISH",
            horizon="SCALP",
            current_iv=0.15,
            atr=25.0,
            regime="BREAKOUT",
            hourly_theta_decay=2.5,  # Low theta drag
        )
        assert fast_proj.is_fast_enough_for_option is True
        assert "FAST_EXPANSION" in fast_proj.velocity_assessment or "healthy" in "".join(fast_proj.forecast_rationale)

        # Slow / Low volatility move with crushing theta decay (e.g. expiring today):
        slow_proj = engine.project_move(
            underlying="NIFTY",
            spot=spot,
            direction="BULLISH",
            horizon="INTRADAY",
            current_iv=0.10,  # low volatility
            atr=10.0,
            regime="RANGE",
            hourly_theta_decay=25.0,  # Extreme theta drag
        )
        assert slow_proj.is_fast_enough_for_option is False
        assert "THETA_BLEED_RISK" in slow_proj.velocity_assessment or "TOO_SLOW" in slow_proj.velocity_assessment

    def test_selector_integration_with_expected_move(self):
        selector = QuantitativeContractSelector()
        proj = expected_move_engine.project_move(
            underlying="BANKNIFTY",
            spot=53150.0,
            direction="BULLISH",
            horizon="INTRADAY",
            current_iv=0.165,
            atr=60.0,
            regime="TREND_UP",
        )

        result = selector.select_optimal_contract(
            underlying="BANKNIFTY",
            spot_price=53150.0,
            direction="LONG_CALL",
            stop_loss_points=70.0,
            current_iv=0.165,
            expected_move_projection=proj,
        )
        assert result is not None
        assert result.expected_move_projection is not None
        assert result.selected_strike_type in ("ITM_1", "ATM", "OTM_1")
        assert result.selected_contract.underlying == "BANKNIFTY"
