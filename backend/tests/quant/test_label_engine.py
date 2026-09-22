"""Unit tests for TripleBarrierLabelEngine (Tier 0)."""

import pytest
import polars as pl
from datetime import datetime, timezone, timedelta

from app.quant.labels.label_engine import TripleBarrierLabelEngine


class TestTripleBarrierLabelEngine:

    def test_adverse_ohlc_path_resolution(self):
        """When both TP and SL are crossed within the same bar, assume STOP FIRST."""
        engine = TripleBarrierLabelEngine(t_max_bars=5, k_tp=1.0, k_sl=1.0, fixed_cost_pct=0.001)

        t0 = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        # Bar 0: Trigger at 80000, ATR = 100
        # Bar 1 (entry): Open at 80000 -> TP = 80100, SL = 79900
        # Bar 2: Wild candle! High = 80150 (TP hit), Low = 79850 (SL hit)
        df = pl.DataFrame({
            "timestamp": [t0, t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)],
            "open": [79990.0, 80000.0, 80000.0],
            "high": [80005.0, 80010.0, 80150.0],  # Bar 2 crosses TP
            "low": [79980.0, 79990.0, 79850.0],   # Bar 2 crosses SL
            "close": [80000.0, 80005.0, 80050.0],
            "atr": [100.0, 100.0, 100.0],
        })

        outcomes = engine.label_candidates(df, candidate_indices=[0], directions=[1])
        assert len(outcomes) == 1
        res = outcomes[0]

        # Must resolve adversely as STOP_HIT, NOT TARGET_HIT
        assert res.exit_reason == "STOP_HIT"
        assert res.exit_price == 79900.0
        assert res.y_raw == -1
        assert res.y_net == -1

    def test_clean_target_hit(self):
        """When only TP is crossed, resolve as TARGET_HIT."""
        engine = TripleBarrierLabelEngine(t_max_bars=5, k_tp=1.0, k_sl=1.0, fixed_cost_pct=0.001)

        t0 = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        df = pl.DataFrame({
            "timestamp": [t0, t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)],
            "open": [79990.0, 80000.0, 80020.0],
            "high": [80005.0, 80010.0, 80150.0],  # Bar 2 crosses TP (80100)
            "low": [79980.0, 79990.0, 79950.0],   # Bar 2 low is well above SL (79900)
            "close": [80000.0, 80005.0, 80120.0],
            "atr": [100.0, 100.0, 100.0],
        })

        outcomes = engine.label_candidates(df, candidate_indices=[0], directions=[1])
        assert len(outcomes) == 1
        res = outcomes[0]

        assert res.exit_reason == "TARGET_HIT"
        assert res.exit_price == 80100.0
        assert res.gross_return > 0
        assert res.net_return == pytest.approx(res.gross_return - 0.001, rel=1e-5)
        assert res.y_raw == 1

    def test_time_expiration(self):
        """When neither barrier is crossed within t_max_bars, exit at close with TIME_EXPIRED."""
        engine = TripleBarrierLabelEngine(t_max_bars=2, k_tp=2.0, k_sl=2.0, fixed_cost_pct=0.001)

        t0 = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        # Entry at Bar 1 (Open 80000). Barriers: TP=80200, SL=79800.
        # Max horizon = 2 bars (Bar 1, Bar 2). Closes at 80010.
        df = pl.DataFrame({
            "timestamp": [t0, t0 + timedelta(minutes=1), t0 + timedelta(minutes=2)],
            "open": [80000.0, 80000.0, 80005.0],
            "high": [80005.0, 80010.0, 80015.0],
            "low": [79995.0, 79990.0, 79995.0],
            "close": [80000.0, 80005.0, 80010.0],
            "atr": [100.0, 100.0, 100.0],
        })

        outcomes = engine.label_candidates(df, candidate_indices=[0], directions=[1])
        assert len(outcomes) == 1
        res = outcomes[0]

        assert res.exit_reason == "TIME_EXPIRED"
        assert res.exit_price == 80010.0
        assert res.bars_held == 2
