import pytest
import time
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.strategies.base import SignalCandidate, StrategyContext
from app.signals.strategies import SCALP_STRATEGIES, INTRADAY_STRATEGIES, STRATEGY_REGISTRY
from app.signals.scalp_confirmation import scalp_confirmation_engine, ScalpConfirmationEngine
from app.signals.fill_reconciler import option_fill_reconciler, OptionFillReconciler
from app.signals.outcome_tracker import outcome_tracker


@pytest.fixture
def client():
    return TestClient(app)


class TestScalpingConfirmationEngine:

    def setup_method(self):
        scalp_confirmation_engine.reset()

    def test_anti_chase_gate(self):
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="MICRO_MOMENTUM",
            direction="LONG_CALL",
            timeframe="1M",
            spot_price=Decimal("24900.0"),
            signal_type="SCALP",
            is_scalp=True,
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24910.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24880.0"),  # Risk = 20 pts
            target_1=Decimal("24930.0"),
            target_2=Decimal("24960.0"),
            risk_points=Decimal("20.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            max_chase_fraction=0.50,  # Max allowed chase = 10 pts
        )

        # 1. Inside allowed chase: 5 pts chase (0.25R)
        res_ok = scalp_confirmation_engine.validate(
            candidate=cand,
            current_spot=Decimal("24905.0"),
            regime="TRENDING_BULLISH",
        )
        assert res_ok.passed is True
        assert res_ok.reason_code is None

        # 2. Exceeded chase: 12 pts chase (0.60R > 0.50R ceiling)
        res_chase = scalp_confirmation_engine.validate(
            candidate=cand,
            current_spot=Decimal("24912.0"),
            regime="TRENDING_BULLISH",
        )
        assert res_chase.passed is False
        assert res_chase.reason_code == "REJECTED_CHASE"

    def test_regime_compatibility_matrix(self):
        cand_vwap = SignalCandidate(
            underlying="NIFTY",
            strategy="VWAP_SCALP",
            direction="LONG_CALL",
            timeframe="1M",
            spot_price=Decimal("24900.0"),
            signal_type="SCALP",
            is_scalp=True,
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24905.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24885.0"),
            target_1=Decimal("24922.5"),
            target_2=Decimal("24937.5"),
            risk_points=Decimal("15.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=2.5,
        )

        # VWAP_SCALP in COMPRESSION -> allowed
        res_comp = scalp_confirmation_engine.validate(cand_vwap, Decimal("24900.0"), regime="COMPRESSION_SQUEEZE")
        assert res_comp.passed is True

        # VWAP_SCALP in VOLATILE_EXPANSION -> rejected
        res_exp = scalp_confirmation_engine.validate(cand_vwap, Decimal("24900.0"), regime="VOLATILE_EXPANSION")
        assert res_exp.passed is False
        assert res_exp.reason_code == "REJECTED_REGIME"

        # EMA_RIBBON in RANGE -> rejected (requires trend)
        cand_ema = cand_vwap.model_copy(update={"strategy": "EMA_RIBBON"})
        res_ema_range = scalp_confirmation_engine.validate(cand_ema, Decimal("24900.0"), regime="RANGEBOUND_LOW_VOL")
        assert res_ema_range.passed is False
        assert res_ema_range.reason_code == "REJECTED_REGIME"

        # EMA_RIBBON in TRENDING_BULLISH -> allowed for LONG_CALL
        res_ema_bull = scalp_confirmation_engine.validate(cand_ema, Decimal("24900.0"), regime="TRENDING_BULLISH")
        assert res_ema_bull.passed is True

    def test_deduplication_and_cooldown(self):
        cand = SignalCandidate(
            underlying="NIFTY",
            strategy="VWAP_SCALP",
            direction="LONG_CALL",
            timeframe="1M",
            spot_price=Decimal("24900.0"),
            signal_type="SCALP",
            is_scalp=True,
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24905.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24885.0"),
            target_1=Decimal("24922.5"),
            target_2=Decimal("24937.5"),
            risk_points=Decimal("15.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=2.5,
        )
        c_ts = 1700000000000

        # First time: passes
        res1 = scalp_confirmation_engine.validate(cand, Decimal("24900.0"), "COMPRESSION_SQUEEZE", candle_timestamp_ms=c_ts, now_ms=c_ts + 1000)
        assert res1.passed is True
        scalp_confirmation_engine.record_confirmed(cand, candle_timestamp_ms=c_ts, now_ms=c_ts + 1000)

        # Duplicate same candle: rejected
        res_dup = scalp_confirmation_engine.validate(cand, Decimal("24900.0"), "COMPRESSION_SQUEEZE", candle_timestamp_ms=c_ts, now_ms=c_ts + 2000)
        assert res_dup.passed is False
        assert res_dup.reason_code == "REJECTED_DEDUPLICATION"

        # Next candle 30 seconds later: rejected by cooldown (default 60s)
        res_cd = scalp_confirmation_engine.validate(cand, Decimal("24900.0"), "COMPRESSION_SQUEEZE", candle_timestamp_ms=c_ts + 30000, now_ms=c_ts + 31000)
        assert res_cd.passed is False
        assert res_cd.reason_code == "REJECTED_COOLDOWN"


class TestTwoClockFSMAndLifecycle:

    def test_breakeven_ratchet_and_two_clock_transitions(self):
        now_ms = int(time.time() * 1000)
        sig = SignalInstance(
            underlying="NIFTY",
            strategy="VWAP_SCALP",
            direction="LONG_CALL",
            timeframe="1M",
            spot_price=Decimal("24900.0"),
            signal_type="SCALP",
            is_scalp=True,
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24905.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24880.0"),  # Risk R = 20 pts
            target_1=Decimal("24930.0"),   # +1.5R (30 pts)
            target_2=Decimal("24950.0"),   # +2.5R (50 pts)
            risk_points=Decimal("20.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=2.5,
            confidence=85.0,
            fsm_state="CONFIRMED",
            ttl_seconds=120,
            runner_ttl_seconds=300,
            time_stop_at_utc=now_ms + 120_000,
        )
        signal_fsm.register(sig)

        # Pre-computed breakeven trigger (+0.8R = 24900 + 16 = 24916.0)
        assert sig.breakeven_trigger_price == Decimal("24916.0")
        assert sig.breakeven_activated is False

        # 1. Tick reaches 24910 (less than 24916): evaluate_tick returns None
        act = signal_fsm.evaluate_tick(sig, Decimal("24910.0"), now_ms)
        assert act is None

        # 2. Tick reaches 24917 (+0.8R breach): evaluate_tick returns BE_ACTIVATED
        act_be = signal_fsm.evaluate_tick(sig, Decimal("24917.0"), now_ms)
        assert act_be == "BE_ACTIVATED"

        # Apply ratchet
        ratcheted = signal_fsm.ratchet_breakeven(sig.signal_id, Decimal("24917.0"))
        assert ratcheted is True
        assert sig.breakeven_activated is True
        # Current stop loss moved to Cost + exchange buffer
        assert sig.current_stop_loss >= Decimal("24900.0")

        # 3. Tick reaches Target 1 (24930.0) -> Transitions to TARGET_1_HIT
        act_t1 = signal_fsm.evaluate_tick(sig, Decimal("24930.0"), now_ms)
        assert act_t1 == "TARGET_1_HIT"

        ok, err = signal_fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("24930.0"))
        assert ok is True
        assert sig.fsm_state == "TARGET_1_HIT"
        assert sig.t1_hit is True
        # Original TTL is killed; runner clock is active
        assert sig.runner_time_stop_at_utc is not None
        assert sig.runner_time_stop_at_utc > now_ms

        # 4. In Runner State, test that it exits at TARGET_2_HIT or RUNNER_TIME_STOP_HIT, NEVER original TIME_STOP_HIT
        # Past original TTL time:
        past_original_ttl = now_ms + 150_000
        act_runner = signal_fsm.evaluate_tick(sig, Decimal("24935.0"), past_original_ttl)
        assert act_runner is None  # Still active inside runner window!

        # Past runner TTL:
        past_runner_ttl = sig.runner_time_stop_at_utc + 1000
        act_runner_timeout = signal_fsm.evaluate_tick(sig, Decimal("24935.0"), past_runner_ttl)
        assert act_runner_timeout == "RUNNER_TIME_STOP_HIT"


class TestOptionFillReconciliation:

    def test_staged_exit_and_pnl(self):
        reconciler = OptionFillReconciler()
        sig = SignalInstance(
            underlying="NIFTY",
            strategy="MICRO_MOMENTUM",
            direction="LONG_CALL",
            timeframe="1M",
            spot_price=Decimal("24900.0"),
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24910.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24880.0"),
            target_1=Decimal("24930.0"),
            target_2=Decimal("24960.0"),
            risk_points=Decimal("20.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            confidence=85.0,
            fsm_state="CONFIRMED",
        )

        # 1. Entry fill: 2 lots (150 qty) @ ₹120.00
        rec = reconciler.reconcile_entry(sig, fill_price=120.0, quantity=150, lot_size=75)
        assert rec.intended_qty == 150
        assert rec.remaining_qty == 150
        assert rec.t1_qty == 75  # 50% staged exit (1 lot)

        # 2. T1 staged exit: 75 qty closed @ ₹160.00
        rec_t1 = reconciler.reconcile_t1_exit(sig, exit_fill_price=160.0)
        assert rec_t1.remaining_qty == 75
        # Gross profit on 75 qty: (160 - 120) * 75 = ₹3,000.00
        # Net profit after Indian statutory taxes/charges:
        assert rec_t1.t1_realized_pnl > 2800.0
        assert rec_t1.total_statutory_costs > 0.0

        # 3. Final exit at Target 2: remaining 75 qty closed @ ₹200.00
        rec_final = reconciler.reconcile_final_exit(sig, exit_fill_price=200.0, exit_reason="TARGET_2_HIT")
        assert rec_final.remaining_qty == 0
        assert rec_final.is_fully_closed is True
        assert rec_final.net_realized_pnl_inr > 8000.0
        assert rec_final.realized_rr > 0.0


class TestDeskAPIEndpoints:

    def test_active_signals_desk_filter(self, client, mock_market_open):
        # Register one intraday and one scalp
        s_intra = SignalInstance(
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("24900.0"),
            signal_type="INTRADAY",
            is_scalp=False,
            entry_min=Decimal("24900.0"),
            entry_max=Decimal("24910.0"),
            trigger=Decimal("24900.0"),
            stop_loss=Decimal("24850.0"),
            target_1=Decimal("24975.0"),
            target_2=Decimal("25050.0"),
            risk_points=Decimal("50.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            confidence=85.0,
            fsm_state="ARMED",
        )
        s_scalp = SignalInstance(
            underlying="BANKNIFTY",
            strategy="VWAP_SCALP",
            direction="LONG_CALL",
            timeframe="1M",
            signal_type="SCALP",
            is_scalp=True,
            spot_price=Decimal("52000.0"),
            entry_min=Decimal("52000.0"),
            entry_max=Decimal("52020.0"),
            trigger=Decimal("52000.0"),
            stop_loss=Decimal("51940.0"),
            target_1=Decimal("52090.0"),
            target_2=Decimal("52150.0"),
            risk_points=Decimal("60.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=2.5,
            confidence=85.0,
            fsm_state="ARMED",
        )
        signal_fsm.register(s_intra)
        signal_fsm.register(s_scalp)

        # 1. Filter desk=SCALP
        res_scalp = client.get("/api/v1/signals/active?desk=SCALP")
        assert res_scalp.status_code == 200
        scalp_data = res_scalp.json()
        assert any(s["strategy"] == "VWAP_SCALP" for s in scalp_data["signals"])
        assert not any(s["strategy"] == "BREAKOUT" for s in scalp_data["signals"])

        # 2. Filter desk=INTRADAY
        res_intra = client.get("/api/v1/signals/active?desk=INTRADAY")
        assert res_intra.status_code == 200
        intra_data = res_intra.json()
        assert any(s["strategy"] == "BREAKOUT" for s in intra_data["signals"])
        assert not any(s["strategy"] == "VWAP_SCALP" for s in intra_data["signals"])
