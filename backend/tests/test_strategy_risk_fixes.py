from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch
import pytest

from app.signals.strategies.base import StrategyContext
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy
from app.signals.trigger_gate import check_trigger_integrity
from app.signals.risk_engine import central_risk_engine, StrategySetup, resolve_realistic_atr
from app.signals.contract_resolver import resolve_nearest_expiry, IST


class TestTrendPullbackGeometry:
    def test_bullish_pullback_trigger_gap_and_risk(self):
        strat = TrendPullbackStrategy()
        spot = Decimal("25000.00")
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "trend": {
                    "ema20": spot * Decimal("0.999"),  # Near EMA20
                    "ema50": spot * Decimal("0.995"),
                    "ema200": spot * Decimal("0.990"),
                    "trend": "BULLISH",
                    "adx": 28.0,
                },
                "atr": 20.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_CALL"
        
        # Flawed trigger was spot + 0.05 pts (25000.05)
        # Valid trigger must be at least min_gap above spot
        atr = Decimal("20.0")
        min_gap = max(atr * Decimal("0.30"), spot * Decimal("0.0006"))  # 15.0 pts
        assert cand.trigger >= spot + min_gap
        assert cand.trigger > spot

        # Trigger gate integrity verification
        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code} - {gate.message}"

        # Risk engine envelope verification
        setup = StrategySetup(
            strategy_name=cand.strategy,
            underlying=cand.underlying,
            direction=cand.direction,
            timeframe=cand.timeframe,
            spot_price=cand.spot_price,
            entry_trigger=cand.trigger,
            raw_structural_stop=cand.stop_loss,
            structural_target_candidates=[cand.target_1, cand.target_2],
            atr_5m=Decimal(str(round(float(cand.risk_points or 20.0), 2))),
            confidence=cand.overall_confidence,
        )
        decision = central_risk_engine.evaluate(setup)
        assert decision.accepted is True, f"Risk engine rejected: {decision.rejection_reason}"

    def test_bearish_pullback_trigger_gap_and_risk(self):
        strat = TrendPullbackStrategy()
        spot = Decimal("25000.00")
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "trend": {
                    "ema20": spot * Decimal("1.001"),
                    "ema50": spot * Decimal("1.005"),
                    "ema200": spot * Decimal("1.010"),
                    "trend": "BEARISH",
                    "adx": 28.0,
                },
                "atr": 20.0,
            },
            mtf={"overall_bias": "BEARISH", "alignment_score": 80.0},
            regime="TREND_DOWN",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_PUT"
        
        atr = Decimal("20.0")
        min_gap = max(atr * Decimal("0.30"), spot * Decimal("0.0006"))
        assert cand.trigger <= spot - min_gap
        assert cand.trigger < spot

        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code} - {gate.message}"


class TestBreakoutGeometry:
    def test_pre_breakout_bullish(self):
        strat = BreakoutStrategy()
        spot = Decimal("25000.00")
        key_res = Decimal("25010.00")  # spot < key_res
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "support_resistance": {"resistance": [key_res], "support": [Decimal("24800.00")]},
                "breakout_pressure": 75.0,
                "volume_ratio": 1.5,
                "atr": 20.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_CALL"
        assert cand.trigger > spot
        assert cand.trigger >= key_res

        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code}"

    def test_breakout_continuation_bullish(self):
        strat = BreakoutStrategy()
        key_res = Decimal("25000.00")
        spot = Decimal("25008.00")  # spot >= key_res, within 0.5 * atr (atr=20 -> max chase=10)
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "support_resistance": {"resistance": [key_res], "support": [Decimal("24800.00")]},
                "breakout_pressure": 75.0,
                "volume_ratio": 1.5,
                "atr": 20.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_CALL"
        # Trigger must be ahead of spot, never behind spot (which caused TRIGGER_WRONG_SIDE)
        assert cand.trigger > spot

        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code}"

    def test_breakout_chase_exceeded(self):
        strat = BreakoutStrategy()
        key_res = Decimal("25000.00")
        spot = Decimal("25015.00")  # spot - key_res = 15 > 0.5 * atr (10)
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "support_resistance": {"resistance": [key_res], "support": [Decimal("24800.00")]},
                "breakout_pressure": 75.0,
                "volume_ratio": 1.5,
                "atr": 20.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="TREND_UP",
        )

        cand = strat.detect(ctx)
        assert cand is None, "Expected None when chase exceeds 0.5 * atr"

    def test_breakdown_continuation_bearish(self):
        strat = BreakoutStrategy()
        key_sup = Decimal("25000.00")
        spot = Decimal("24993.00")  # spot <= key_sup, within 0.5 * atr (7 pts < 10 pts)
        ctx = StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            indicators={
                "support_resistance": {"resistance": [Decimal("25200.00")], "support": [key_sup]},
                "breakout_pressure": 75.0,
                "volume_ratio": 1.5,
                "atr": 20.0,
            },
            mtf={"overall_bias": "BEARISH", "alignment_score": 80.0},
            regime="TREND_DOWN",
        )

        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_PUT"
        # Trigger must be below spot (never above spot)
        assert cand.trigger < spot

        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code}"


class TestORBStrategy:
    def _create_orb_context(self, spot: Decimal, ts_ms: int, orb_high: Decimal, orb_low: Decimal) -> StrategyContext:
        return StrategyContext(
            underlying="NIFTY",
            spot_price=spot,
            timeframe="5M",
            timestamp_ms=ts_ms,
            indicators={
                "orb": {"high": orb_high, "low": orb_low},
                "volume_ratio": 1.5,
                "atr": 20.0,
            },
            mtf={"overall_bias": "BULLISH", "alignment_score": 80.0},
            regime="TREND_UP",
        )

    def test_orb_session_window_enforcement(self):
        strat = OpeningRangeBreakoutStrategy()
        orb_high = Decimal("25000.00")
        orb_low = Decimal("24900.00")
        spot = Decimal("25005.00")

        # 09:15 IST -> 555 min -> before window (570 min)
        # Epoch ms for 03:45 UTC (09:15 IST):
        # (3*3600 + 45*60) * 1000 = 13500000 ms
        ctx_early = self._create_orb_context(spot, 13500000, orb_high, orb_low)
        assert strat.detect(ctx_early) is None

        # 12:00 IST -> 720 min -> after window (690 min)
        # 06:30 UTC -> (6*3600 + 30*60) * 1000 = 23400000 ms
        ctx_late = self._create_orb_context(spot, 23400000, orb_high, orb_low)
        assert strat.detect(ctx_late) is None

        # 10:00 IST -> 600 min -> inside window (570 - 690 min)
        # 04:30 UTC -> (4*3600 + 30*60) * 1000 = 16200000 ms
        ctx_valid = self._create_orb_context(spot, 16200000, orb_high, orb_low)
        cand = strat.detect(ctx_valid)
        assert cand is not None

    def test_orb_trigger_geometry_and_chase(self):
        strat = OpeningRangeBreakoutStrategy()
        orb_high = Decimal("25000.00")
        orb_low = Decimal("24900.00")
        
        # 10:00 IST timestamp (inside window)
        ts_valid = 16200000

        # Spot breached orb_high by 5 pts (within 0.5 * atr = 10 pts)
        spot = Decimal("25005.00")
        ctx = self._create_orb_context(spot, ts_valid, orb_high, orb_low)
        cand = strat.detect(ctx)
        assert cand is not None
        assert cand.direction == "LONG_CALL"
        # Trigger must be ahead of spot, NOT at orb_high
        assert cand.trigger > spot
        assert cand.trigger > orb_high

        gate = check_trigger_integrity(
            underlying=cand.underlying,
            strategy=cand.strategy,
            direction=cand.direction,
            spot_price=cand.spot_price,
            entry_min=cand.entry_min,
            entry_max=cand.entry_max,
            trigger=cand.trigger,
            stop_loss=cand.stop_loss,
            target_1=cand.target_1,
            target_2=cand.target_2,
            risk_points=cand.risk_points,
            risk_reward_t1=cand.risk_reward_t1,
            risk_reward_t2=cand.risk_reward_t2,
        )
        assert gate.passed is True, f"Trigger gate failed: {gate.reason_code}"

        # Spot breached orb_high by 15 pts (exceeds 0.5 * atr = 10 pts) -> chase rejection
        spot_chase = Decimal("25015.00")
        ctx_chase = self._create_orb_context(spot_chase, ts_valid, orb_high, orb_low)
        assert strat.detect(ctx_chase) is None


class TestSensex1mScalpEnvelope:
    def test_sensex_1m_scalp_envelope_present(self):
        rules = central_risk_engine._config.get("envelopes", {}).get("SENSEX", {}).get("1m_scalp")
        assert rules is not None
        assert rules["min_risk_pts"] == 35.0
        assert rules["max_risk_pts"] == 70.0
        assert rules["t1_ceiling_pts"] == 100.0
        assert rules["t2_ceiling_pts"] == 160.0
        assert rules["atr_multiplier"] == 1.1
        assert rules["min_rr"] == 1.25
        assert rules["trigger_ttl_seconds"] == 180
        assert rules["active_time_stop_seconds"] == 900

    def test_sensex_1m_scalp_evaluation(self):
        # Simulate a 1M scalp candidate on SENSEX
        setup = StrategySetup(
            strategy_name="EMA_RIBBON",
            underlying="SENSEX",
            direction="LONG_CALL",
            timeframe="1M",
            is_scalp=True,
            spot_price=Decimal("82000.00"),
            entry_trigger=Decimal("82050.00"),
            raw_structural_stop=Decimal("82000.00"),  # 50 pts risk (within 35 - 70 envelope)
            structural_target_candidates=[Decimal("82120.00"), Decimal("82180.00")],
            atr_5m=Decimal("40.0"),
            confidence=80.0,
        )
        decision = central_risk_engine.evaluate(setup)
        assert decision.accepted is True
        assert decision.trigger_ttl_seconds == 180
        assert decision.active_time_stop_seconds == 900


class TestContractResolverPostMarketExpiry:
    def test_expiry_day_intraday_vs_postmarket(self):
        # Test Thursday (weekday 3)
        thursday = date(2026, 9, 3)
        assert thursday.weekday() == 3

        # Case 1: During market hours on Thursday at 14:00 IST
        market_time = datetime(2026, 9, 3, 14, 0, tzinfo=IST)
        with patch("app.signals.contract_resolver.datetime") as mock_dt:
            mock_dt.now.return_value = market_time
            mock_dt.strptime = datetime.strptime
            expiry, exp_type = resolve_nearest_expiry("NIFTY", ref_date=None)
            assert expiry == thursday
            assert exp_type == "EXPIRING_TODAY"

        # Case 2: Post-market on Thursday at 15:35 IST (contract for today expired, advance to next)
        post_market_time = datetime(2026, 9, 3, 15, 35, tzinfo=IST)
        with patch("app.signals.contract_resolver.datetime") as mock_dt:
            mock_dt.now.return_value = post_market_time
            mock_dt.strptime = datetime.strptime
            expiry, exp_type = resolve_nearest_expiry("NIFTY", ref_date=None)
            assert expiry == thursday + timedelta(days=7)
            assert exp_type != "EXPIRING_TODAY"
