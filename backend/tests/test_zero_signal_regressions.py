"""
Regression tests for the zero-signal root causes found 2026-10-01.

Each test here pins a defect that made the live funnel report
"798 evaluations -> 50 detector hits -> 0 confirmed" regardless of market
conditions. They are deliberately behavioural (what the pipeline must be able
to do) rather than value-pinning, so a future refactor cannot silently
reintroduce a 0% hit rate.
"""
from decimal import Decimal

import pytest

from app.signals.pipeline.enrichment import _pit_max_age_ms
from app.signals.risk.friction_gate import friction_gate
from app.signals.strategies.base import SignalCandidate
from app.signals.validation.pit_validator import pit_validator


def _cand(**kw) -> SignalCandidate:
    base = dict(
        underlying="NIFTY",
        strategy="TREND_PULLBACK",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("22500.0"),
        entry_min=Decimal("22500.0"),
        entry_max=Decimal("22510.0"),
        trigger=Decimal("22510.0"),
        stop_loss=Decimal("22487.5"),
        target_1=Decimal("22544.0"),
        target_2=Decimal("22611.0"),
        risk_points=Decimal("22.5"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        greeks={"delta": 0.51, "theta_hour": -6.16, "iv": 0.15},
    )
    base.update(kw)
    return SignalCandidate(**base)


class TestHoldingClockIsNotFatal:
    """time_stop_seconds is the ONLY holding clock friction_gate can reach from
    strategy_runner (it calls friction_gate.evaluate(cand) with no args).

    A strategy that leaves it None is UNTRADEABLE BY CONSTRUCTION: the gate
    hard-rejects with REJECT_NO_HOLDING_CLOCK on 100% of evaluations. ORB and
    MEAN_REVERSION both shipped that way, so they could never emit a signal.
    """

    @pytest.mark.parametrize("strategy", ["ORB", "MEAN_REVERSION"])
    def test_enabled_intraday_strategies_declare_a_holding_clock(self, strategy: str):
        from app.signals.strategies import INTRADAY_STRATEGIES, STRATEGY_ENABLED

        assert STRATEGY_ENABLED.get(strategy) is True, "strategy must be auto-scanned for this to matter"
        src = open(
            f"app/signals/strategies/{'orb' if strategy == 'ORB' else 'mean_reversion'}.py",
            encoding="utf-8",
        ).read()
        assert "time_stop_seconds=" in src, f"{strategy} never sets a holding clock"

    def test_candidate_without_holding_clock_is_rejected(self):
        """Documents WHY the field is mandatory — pins the failure mode."""
        res = friction_gate.evaluate(
            _cand(time_stop_seconds=None),
            live_premium=110.0, live_spread_pts=2.0, live_iv=0.15,
        )
        assert res.passed is False
        assert "REJECT_NO_HOLDING_CLOCK" in (res.rejection_reason or "")

    def test_every_enabled_strategy_declares_a_holding_clock(self):
        """Sweep guard.

        The whole enabled portfolio must be structurally tradeable. A single
        enabled strategy missing time_stop_seconds is a strategy that can
        never emit a signal, silently, forever.
        """
        import inspect
        from app.signals.strategies import STRATEGY_ENABLED, STRATEGY_REGISTRY

        missing: list[str] = []
        for name, enabled in STRATEGY_ENABLED.items():
            if not enabled:
                continue
            strat = STRATEGY_REGISTRY.get(name)
            if strat is None:
                continue
            cls = type(strat)
            src = inspect.getsource(cls)
            if "time_stop_seconds=" not in src:
                missing.append(f"{name} ({cls.__module__})")
        assert not missing, "enabled strategies with no holding clock: " + ", ".join(missing)


class TestIntradayHoldingClockIsPricable:
    """The real economics: theta is priced over the declared holding clock.

    At the old 3-hour clock the ATM-leg theta drag (~18.5 pts) exceeded the
    entire 1.5R option target (~17.3 pts), so EVERY TREND_PULLBACK candidate
    was rejected with REJECT_FRICTION. At a 15-minute clock the same setup is
    comfortably viable.
    """

    def test_three_hour_clock_was_uneconomic(self):
        res = friction_gate.evaluate(
            _cand(time_stop_seconds=10800),
            live_premium=110.0, live_spread_pts=2.0, live_iv=0.15,
        )
        assert res.passed is False
        assert res.rejection_reason and res.rejection_reason.startswith(
            ("REJECT_FRICTION", "REJECT_NET_EDGE", "REJECT_POOR_NET_RR")
        )

    def test_fifteen_minute_clock_is_viable(self):
        res = friction_gate.evaluate(
            _cand(time_stop_seconds=900),
            live_premium=110.0, live_spread_pts=2.0, live_iv=0.15,
        )
        assert res.passed is True, res.rejection_reason
        assert res.net_reward_risk_ratio >= 0.70
        assert res.cost_to_target_ratio_pct <= 45.0

    def test_trend_pullback_ships_a_pricable_clock(self):
        from app.signals.strategies.trend_pullback import TrendPullbackStrategy
        import inspect

        src = inspect.getsource(TrendPullbackStrategy)
        assert "time_stop_seconds=900" in src
        assert "time_stop_seconds=180 * 60" not in src, "3h clock must not come back"


class TestPITStalenessIsTimeframeAware:
    """Providers stamp candles at the bar OPEN, so while a bar is still forming
    its timestamp is legitimately up to one bar-duration old. A fixed 120s
    floor hard-rejected the 5M desk for the back half of every 5-minute bar
    (~60% of wall-clock time) with a STALE_DATA violation on a CURRENT bar.
    """

    def test_1m_floor_unchanged(self):
        cand = _cand(timeframe="1M")
        assert _pit_max_age_ms(cand) == 120_000

    def test_5m_floor_covers_a_full_forming_bar(self):
        cand = _cand(timeframe="5M")
        assert _pit_max_age_ms(cand) >= 300_000

    def test_forming_5m_bar_is_not_reported_stale(self):
        now_ms = 1_700_000_000_000
        bar_open_ms = now_ms - 240_000  # 240s into a 300s bar
        candles = [
            {"timestamp": bar_open_ms, "close": 22500.0},
            {"timestamp": bar_open_ms - 300_000, "close": 22490.0},
        ]
        strict = pit_validator.validate_timeline(
            decision_timestamp_ms=now_ms, candles=candles, max_age_ms=120_000
        )
        assert strict.passed is False  # the old, wrong behaviour
        assert any("STALE_DATA" in v for v in strict.violations)

        cand = _cand(timeframe="5M")
        fixed = pit_validator.validate_timeline(
            decision_timestamp_ms=now_ms,
            candles=candles,
            max_age_ms=_pit_max_age_ms(cand),
        )
        assert fixed.passed is True, fixed.violations

    def test_lookahead_is_still_blocked(self):
        """Widening the staleness floor must NOT weaken the anti-lookahead guard."""
        now_ms = 1_700_000_000_000
        candles = [{"timestamp": now_ms + 10_000, "close": 22500.0}]
        res = pit_validator.validate_timeline(
            decision_timestamp_ms=now_ms,
            candles=candles,
            max_age_ms=_pit_max_age_ms(_cand(timeframe="5M")),
        )
        assert res.passed is False
        assert any("LOOKAHEAD_VIOLATION" in v for v in res.violations)


class TestScanCacheCannotSwallowDueScans:
    """scan_cache_ttl_s == the worker's scalp interval meant every other due
    tick returned the cache and never scanned. Effective cadence was 2x the
    configured one, and each skip was completely silent.
    """

    def test_ttl_is_strictly_below_every_scan_interval(self):
        from app.signals.scanner import SignalScanner
        from app.signals.worker import AutomatedSignalWorker

        ttl = SignalScanner()._scan_cache_ttl_s
        worker = AutomatedSignalWorker()
        assert ttl < worker._scalp_interval, "scalp due-ticks would be swallowed"
        assert ttl < worker._intraday_interval, "intraday due-ticks would be swallowed"


class TestNoStrategyHasAnImpossibleVolumeGate:
    """MICRO_MOMENTUM rebuilt its own volume ratio from the raw candle pool:

        vol_ratio = candles[-1].volume / ctx.volume_ma_20

    candles[-1] is the FORMING bar (partial print) and volume_ma_20 is the mean
    of the last 20 bars INCLUDING that same forming bar. Measured on the live
    feed the ratio is a sawtooth topping out near 1.0 at the last second of the
    minute, so a `>= VOLUME_MICRO_MIN` (1.1) gate could never be cleared — the
    strategy was mathematically incapable of emitting a candidate, and the
    blanket NO_SETUP_NO_EDGE diagnostic hid it behind 288 identical lines.
    """

    def test_micro_momentum_does_not_rebuild_ratio_from_raw_pool(self):
        import inspect
        from app.signals.strategies.micro_momentum import MicroMomentumStrategy

        src = inspect.getsource(MicroMomentumStrategy)
        # It must consume the PIT-reconciled ratio, like every sibling.
        assert "extract_volume_ratio(ctx.indicators)" in src
        # The raw forming-bar ratio is the bug and must not come back.
        assert "vol_ratio = cur_vol / vol_ma" not in src
        assert "cur_vol / vol_ma" not in src

    def test_forming_bar_ration_cannot_clear_the_gate(self):
        """Demonstrates the arithmetic: even a bar at 100% of its eventual
        volume only reaches ~1.0 against an MA that contains itself."""
        from app.signals.strategies.base import VOLUME_MICRO_MIN

        prior = [100.0] * 20          # 20 prior closed bars
        for fill in (0.0, 0.25, 0.5, 0.75, 1.0):
            forming = 100.0 * fill
            raw_ma = (sum(prior) + forming) / 20.0
            raw_ratio = (forming / raw_ma) if raw_ma else 0.0
            assert raw_ratio < VOLUME_MICRO_MIN, (
                f"fill={fill}: raw ratio {raw_ratio:.3f} unexpectedly cleared "
                f"{VOLUME_MICRO_MIN} — the sawtooth assumption no longer holds"
            )
        # The honest (closed-bar) ratio for the same bar is 1.0 and clears the
        # 0.8 scalp gate comfortably, which is why the PIT value is used.
        assert 1.0 >= 0.8

    def test_every_volume_gated_strategy_uses_the_reconciled_ratio(self):
        """Sweep: no volume-gated strategy may build its own raw ratio."""
        import inspect
        from app.signals.strategies import STRATEGY_ENABLED, STRATEGY_REGISTRY

        offenders: list[str] = []
        for name, enabled in STRATEGY_ENABLED.items():
            if not enabled:
                continue
            strat = STRATEGY_REGISTRY.get(name)
            if strat is None:
                continue
            src = inspect.getsource(type(strat))
            if "VOLUME" not in src and "vol_ratio" not in src:
                continue  # not volume-gated
            if "extract_volume_ratio" in src:
                continue
            offenders.append(f"{name} ({type(strat).__module__})")
        assert not offenders, (
            "volume-gated strategies bypassing extract_volume_ratio: "
            + ", ".join(offenders)
        )


class TestExplainCoversEveryEnabledStrategy:
    """A detect() that returns None must name its real blocker. The fallback
    NO_SETUP_NO_EDGE is a diagnostic black hole that made two scalp strategies
    unobservable for a full session."""

    def test_enabled_strategies_have_explain_branches(self):
        import inspect
        from app.signals.pipeline.strategy_runner import _explain_detect_none
        from app.signals.strategies import STRATEGY_ENABLED, STRATEGY_REGISTRY

        src = inspect.getsource(_explain_detect_none)
        missing = [
            n for n, e in STRATEGY_ENABLED.items()
            if e and n in STRATEGY_REGISTRY and f'"{n}"' not in src and f'"{n[:-1]}"' not in src
        ]
        assert not missing, "no explain branch for: " + ", ".join(missing)


class TestThrottleCounterIsWired:
    """throttled_signals_count was declared and read but never written, so
    /signals/performance reported throttled_signals_total: 0 forever.
    """

    def test_suppression_codes_are_classified(self):
        from app.signals.scanner import SignalScanner

        s = SignalScanner()
        for code in (
            "VWAP_SCALP:REJECTED_DEDUPLICATION",
            "ORB:REJECTED_COOLDOWN",
            "NIFTY:STACKING_BLOCKED_EXISTING_ORB_LONG_CALL",
            "X:PORTFOLIO_CONCURRENCY_LIMIT_REACHED",
        ):
            assert s._is_throttle_code(code) is True, code

        for code in (
            "VWAP_SCALP:NO_SETUP_LOW_VOLUME_0.71_LT_0.8",
            "TREND_PULLBACK:REJECT_FRICTION: Friction consumes 45.5% of target",
            "NIFTY:MARKET_DATA_OFFLINE_OFFLINE",
        ):
            assert s._is_throttle_code(code) is False, code

    def test_note_throttle_accumulates(self):
        from app.signals.scanner import SignalScanner

        s = SignalScanner()
        s._note_throttle("NIFTY:1M", ["ORB:REJECTED_COOLDOWN", "ORB:NO_SETUP_NO_EDGE"])
        s._note_throttle("NIFTY:1M", ["ORB:REJECTED_DEDUPLICATION"])
        assert s._throttle_counts["NIFTY:1M"] == 2
