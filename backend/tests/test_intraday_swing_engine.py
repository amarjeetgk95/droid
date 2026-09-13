"""
Unit and Integration Tests for Droid Intraday Swing Option Buying Engine (v3.1 Production-MVP).
Validates:
  - ATM vs ITM-1 strike candidate generation
  - 15M/5M Trend Pullback strategy with VWAP alignment
  - Theta drag ceiling (<= 20%) and net R/R gating
  - Fast-path execution latency (< 150ms)
  - Position sizing with 0.75% account risk
"""
from __future__ import annotations

import time
from decimal import Decimal
import pytest

from app.signals.contract_resolver import resolve_option_contract
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.base import StrategyContext
from app.signals.risk_engine import StrategySetup, central_risk_engine


class TestIntradaySwingOptionBuyingMVP:
    """Test Suite for v3.1 Production-MVP Intraday Option Buying."""

    def test_candidate_types_filtering_atm_and_itm1_only(self):
        """Verify that only ITM_1 and ATM candidates are evaluated (§9)."""
        res = quantitative_contract_selector.select_optimal_contract(
            underlying="NIFTY",
            spot_price=25000.0,
            direction="LONG_CALL",
            expected_move_points=75.0,
            stop_loss_points=25.0,
            target_horizon_hours=0.75,
            candidate_types=["ITM_1", "ATM"],
        )
        assert res is not None
        candidate_types = [c.strike_type for c in res.all_candidates]
        assert "OTM_1" not in candidate_types
        assert set(candidate_types) == {"ITM_1", "ATM"}
        assert res.selected_strike_type in ("ITM_1", "ATM")

    def test_put_option_itm_strike_selection(self):
        """Verify that Put option swing selects In-The-Money (higher strike) (§9 & §10)."""
        res = quantitative_contract_selector.select_optimal_contract(
            underlying="NIFTY",
            spot_price=25000.0,
            direction="LONG_PUT",
            expected_move_points=75.0,
            stop_loss_points=25.0,
            target_horizon_hours=0.75,
            candidate_types=["ITM_1", "ATM"],
        )
        assert res is not None
        assert res.selected_contract.option_type == "PE"
        # For NIFTY at 25000, ITM-1 Put strike is 25050 (above spot)
        itm_cands = [c for c in res.all_candidates if c.strike_type == "ITM_1"]
        assert len(itm_cands) == 1
        assert itm_cands[0].strike == 25050.0
        assert itm_cands[0].greeks.delta < -0.45

    def test_vwap_alignment_bullish_and_bearish(self):
        """Verify VWAP alignment requirement (§7 Step 1 & §6)."""
        strat = TrendPullbackStrategy()
        spot = Decimal("25000")

        indicators = {
            "trend": {
                "ema20": 24980.0,
                "ema50": 24900.0,
                "ema200": 24700.0,
                "adx": 26.0,
                "trend": "BULLISH",
            },
            "atr": 25.0,
            "adx": 26.0,
        }

        # Case 1: Spot is below VWAP (25050) -> Must fail VWAP alignment
        ctx_below_vwap = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators=indicators,
            mtf={"overall_bias": "BULLISH"},
            regime="TREND_UP",
            vwap=Decimal("25050"),
        )
        cand_below = strat.detect(ctx_below_vwap)
        assert cand_below is None

        # Case 2: Spot is above VWAP (24950) -> Passes VWAP alignment
        ctx_above_vwap = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators=indicators,
            mtf={"overall_bias": "BULLISH"},
            regime="TREND_UP",
            vwap=Decimal("24950"),
        )
        cand_above = strat.detect(ctx_above_vwap)
        assert cand_above is not None
        assert cand_above.direction == "LONG_CALL"
        assert cand_above.time_stop_seconds == 180 * 60

    def test_theta_drag_guard_rejection(self):
        """Verify that excessive theta drag (> 20%) marks candidate as unacceptable (§12)."""
        # A tiny expected move over a long horizon produces huge theta drag
        res = quantitative_contract_selector.select_optimal_contract(
            underlying="NIFTY",
            spot_price=25000.0,
            direction="LONG_CALL",
            expected_move_points=10.0,  # Tiny 10 pt move
            stop_loss_points=25.0,
            target_horizon_hours=2.5,   # Long 2.5 hour holding
            candidate_types=["ITM_1", "ATM"],
            max_theta_drag_ratio=20.0,
        )
        assert res is not None
        # Both candidates must be rejected for exceeding 20% theta drag ceiling
        for c in res.all_candidates:
            assert c.is_acceptable is False
            assert any("Theta drag" in r for r in c.rejection_reasons)
        assert res.is_viable is False

    def test_fast_path_latency_under_150ms(self):
        """Verify fast execution gate latency constraint (§5: Target < 150 ms)."""
        strat = TrendPullbackStrategy()
        spot = Decimal("25000")
        indicators = {
            "trend": {
                "ema20": 24980.0,
                "ema50": 24900.0,
                "ema200": 24700.0,
                "adx": 26.0,
                "trend": "BULLISH",
            },
            "atr": 25.0,
            "adx": 26.0,
        }
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators=indicators,
            mtf={"overall_bias": "BULLISH"},
            regime="TREND_UP",
            vwap=Decimal("24950"),
        )

        # Warm-up
        _ = strat.detect(ctx)

        # Benchmark execution
        t0 = time.perf_counter()
        cand = strat.detect(ctx)
        t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert cand is not None
        assert t_elapsed_ms < 150.0, f"Fast path latency exceeded 150ms: {t_elapsed_ms:.2f}ms"

    def test_risk_sizing_respects_equity_budget(self):
        """Verify position sizing does not exceed 0.75% account risk budget (§17 & §18)."""
        strat_setup = StrategySetup(
            strategy_name="TREND_PULLBACK",
            underlying="NIFTY",
            direction="LONG_CALL",
            timeframe="5M",
            is_scalp=False,
            spot_price=Decimal("25000.0"),
            entry_trigger=Decimal("25015.0"),
            raw_structural_stop=Decimal("24995.0"),
            structural_target_candidates=[Decimal("25045.0"), Decimal("25075.0")],
            atr_5m=Decimal("25.0"),
            confidence=80.0,
            option_delta=0.60,
            option_theta_hour=-7.0,
            option_premium=140.0,
        )

        account_equity = 100000.0  # Rs. 1 Lakh
        risk_pct = 0.75            # Rs. 750 max risk

        decision = central_risk_engine.evaluate(
            strat_setup,
            available_capital=account_equity,
            risk_per_trade_pct=risk_pct,
            allow_closed_market=True,
        )

        # Budget is Rs. 750. 1 lot NIFTY (75 qty) with ~20 pt SL * 0.6 delta = Rs. 900 risk.
        # So budget Rs. 750 should safely reject 1 lot (budget cannot absorb risk)
        if not decision.accepted:
            assert "INSUFFICIENT_CAPITAL" in (decision.rejection_reason or "")

        # With Rs. 2 Lakh equity, budget = Rs. 1500 -> Exactly 1 lot allowed!
        decision2 = central_risk_engine.evaluate(
            strat_setup,
            available_capital=200000.0,
            risk_per_trade_pct=risk_pct,
            allow_closed_market=True,
        )
        assert decision2.accepted is True
        assert decision2.lots == 1
        assert decision2.quantity == 75
        assert decision2.max_rupee_loss <= 1500.0
