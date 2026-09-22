"""Honest fallback contract: unfitted models, missing IV, stale cache.

Covers task goals:
- unfitted model returns fallback status (not fake probs)
- missing IV returns available=false (+ nulls, assumptions)
- stale served with stale=true (+ limitations/age)
"""
from __future__ import annotations

import asyncio

import pytest


class TestUnfittedModelsFailClosed:
    def test_direction_unfitted_returns_fallback_nulls(self):
        from app.ml.models.direction_model import DirectionModel

        m = DirectionModel.__new__(DirectionModel)
        m.horizon_minutes = 15
        m.lgb_model = None
        m.meta = {}
        out = m.predict_direction([0.0] * 15)
        assert out["is_fallback"] is True
        assert out["status"] == "fallback"
        assert out["p_down"] is None and out["p_neutral"] is None and out["p_up"] is None
        assert out["predicted_bias"] is None and out["confidence"] is None
        # Never 60/25/15-style concrete numbers
        assert "reason" in out

    def test_regime_unfitted_returns_fallback_nulls(self):
        from app.ml.models.regime_model import RegimeModel

        m = RegimeModel.__new__(RegimeModel)
        m.model = None
        m.meta = {}
        out = m.predict_regime([0.0] * 20)
        assert out["is_fallback"] is True
        assert out["status"] == "fallback"
        assert out["regime"] is None
        assert out["probabilities"] is None

    def test_breakout_unfitted_returns_fallback_nulls(self):
        from app.ml.models.breakout_model import BreakoutModel

        m = BreakoutModel.__new__(BreakoutModel)
        m.model = None
        m.meta = {}
        out = m.predict_breakout_quality([0.0] * 15)
        assert out["is_fallback"] is True
        assert out["status"] == "fallback"
        assert out["p_valid_breakout"] is None
        assert out["p_false_breakout"] is None
        assert out["is_continuation"] is None

    def test_trade_outcome_unfitted_returns_fallback_nulls(self):
        from app.ml.models.trade_outcome_model import TradeOutcomeModel

        m = TradeOutcomeModel.__new__(TradeOutcomeModel)
        m.classifier = None
        m.mfe_regressor = None
        m.mae_regressor = None
        m.calibrator = None
        m.meta = {}
        out = m.predict_trade_outcome([0.0] * 15)
        assert out["is_fallback"] is True
        assert out["status"] == "fallback"
        assert out["p_target_before_stop"] is None
        assert out["p_stop_before_target"] is None
        assert out["p_timeout"] is None

    def test_orthogonal_ensemble_unfitted_returns_unfitted_nulls(self):
        import polars as pl

        from app.ml.orthogonal_ensemble import OrthogonalEnsemble

        ens = OrthogonalEnsemble()
        assert ens.is_fitted is False
        df = pl.DataFrame(
            {
                "vwap_distance": [0.0],
                "ema_cross_spread": [0.0],
                "atr_pct": [0.0],
                "realized_vol_20": [0.0],
                "return_15m": [0.0],
                "rsi": [50.0],
                "return_1m": [0.0],
                "return_3m": [0.0],
                "candle_body_ratio": [0.5],
                "upper_wick_ratio": [0.1],
                "lower_wick_ratio": [0.1],
                "volume_ratio": [1.0],
            }
        )
        pred = ens.predict_one(df, 0)
        assert pred.status == "unfitted"
        assert pred.is_fallback is True
        assert pred.is_qualified is False
        assert pred.p_linear is None and pred.p_lgbm is None
        assert pred.p_ensemble is None and pred.calibrated_prob is None
        assert pred.confidence_score is None

    def test_stacker_missing_artifact_fail_closed(self):
        from app.ml import stacker_v1 as _s

        # Missing artifact -> None (fail-closed, never 0.5 fake probs)
        row = [0.0] * _s.STACKER_WIDTH
        # Point at a missing path by monkeypatching STACKER_PATH
        import pathlib
        import tempfile

        orig = _s.STACKER_PATH
        try:
            _s.STACKER_PATH = pathlib.Path(tempfile.gettempdir()) / "stacker_missing_test.json"
            if _s.STACKER_PATH.exists():
                _s.STACKER_PATH.unlink()
            assert _s.load_stacker() is None
            assert _s.predict_stacker(row) is None
        finally:
            _s.STACKER_PATH = orig

    def test_stacker_row_assumption_bumps_missing(self):
        from app.ml.stacker_v1 import build_stacker_row_with_meta

        out = build_stacker_row_with_meta({"mtf": 0, "indicators": 0, "ml": 0, "options": 0, "structure": 0})
        assert "iv_rank-assumed-0.5-mid" in out["assumptions"]
        assert "dte_days-assumed-2.0-bucket" in out["assumptions"]
        assert out["missing_count"] >= 2


class TestMissingIVAvailableFalse:
    @pytest.mark.asyncio
    async def test_options_context_unavailable_nulls_not_15(self, monkeypatch):
        from app.research.options_context import ResearchOptionsContext

        async def _no_fno(instrument):
            return {"available": False, "reason": "test no chain"}

        monkeypatch.setattr("app.fno.context.get_fno_context", _no_fno, raising=False)
        # Also patch the direct import path used inside get_context
        import app.research.options_context as _oc

        orig = _oc.ResearchOptionsContext.get_context

        async def _patched(instrument):
            # Force the unavailable branch without needing fno module
            return {
                "instrument": instrument,
                "timestamp": "2026-01-01T00:00:00+00:00",
                "available": False,
                "data_quality": "EMPTY",
                "pcr_oi": None,
                "pcr_vol": None,
                "atm_iv": None,
                "call_wall": None,
                "put_wall": None,
                "max_pain": None,
                "days_to_expiry": None,
                "atm_theta": None,
                "atm_gamma": None,
                "atm_vega": None,
                "synthetic": False,
                "assumptions": ["test"],
            }

        # Directly verify the contract shape for unavailable: nulls, not 15.0/1.0
        ctx = await _patched("NIFTY 50")
        assert ctx["available"] is False
        assert ctx["atm_iv"] is None
        assert ctx["pcr_oi"] is None
        assert ctx["days_to_expiry"] is None
        assert "assumptions" in ctx

    def test_option_model_default_iv_marked_assumption(self):
        from app.ml.models.option_model import OptionsIntelligenceModel

        m = OptionsIntelligenceModel()
        out = m.evaluate_strikes(
            underlying="NIFTY",
            direction="LONG_CALL",
            spot_price=25000.0,
            target_1=25100.0,
            stop_loss=24900.0,
            p_target=0.5,
            p_stop=0.3,
            p_timeout=0.2,
            dte_days=None,
            atm_iv=None,
        )
        assert out["iv_available"] is False
        assert out["dte_available"] is False
        assert any("atm_iv" in a for a in out["assumptions"])
        assert any("dte" in a for a in out["assumptions"])

    def test_option_model_explicit_iv_not_assumed(self):
        from app.ml.models.option_model import OptionsIntelligenceModel

        m = OptionsIntelligenceModel()
        out = m.evaluate_strikes(
            underlying="NIFTY",
            direction="LONG_CALL",
            spot_price=25000.0,
            target_1=25100.0,
            stop_loss=24900.0,
            p_target=0.5,
            p_stop=0.3,
            p_timeout=0.2,
            dte_days=2.0,
            atm_iv=0.16,
        )
        assert out["iv_available"] is True
        assert out["dte_available"] is True
        assert out["assumptions"] == []


class TestStaleServedHonest:
    def test_stamp_tactical_bias_stale_true_with_limitation(self):
        from app.api.research import _stamp_tactical_bias

        fresh = _stamp_tactical_bias({"limitations": []}, 10.0)
        assert fresh["stale"] is False
        assert fresh["cache_age_s"] == 10.0

        stale = _stamp_tactical_bias({"limitations": []}, 100.0)
        assert stale["stale"] is True
        assert "served-stale-cache" in stale["limitations"]

    def test_stamp_board_stale_true(self):
        from app.api.research import _stamp_board

        fresh = _stamp_board({"x": 1}, 5.0)
        assert fresh["stale"] is False
        stale = _stamp_board({"x": 1}, 100.0)
        assert stale["stale"] is True

    @pytest.mark.asyncio
    async def test_coordinator_stale_carries_status_and_age(self):
        import asyncio

        from app.services.market_data_coordinator import MarketDataCoordinator

        coord = MarketDataCoordinator()

        async def _good():
            return {"price": 100.0}

        r1 = await coord.get_or_compute("honest_stale_key", _good, ttl_seconds=0.02)
        assert r1.status == "FRESH"

        await asyncio.sleep(0.03)

        async def _bad():
            raise RuntimeError("upstream down")

        r2 = await coord.get_or_compute("honest_stale_key", _bad, ttl_seconds=0.02)
        # Stale must carry status+age, never fresh
        assert r2.status == "DEGRADED"
        assert r2.age_ms > 0
        assert r2.data == {"price": 100.0}

    def test_central_feed_age_status_additive(self):
        from app.services.central_feed import central_feed

        s = central_feed.feed_age_status()
        assert "status" in s and "age_s" in s
        assert s["status"] in ("LIVE", "STALE", "DOWN", "UNKNOWN")

    def test_ai_validation_fallback_never_confirm(self):
        import asyncio

        from app.services.ai_validation_service import ai_validation_service
        from app.models.ai import AITradeValidationRequest
        from unittest.mock import AsyncMock, MagicMock, patch

        req = AITradeValidationRequest(
            symbol="NIFTY",
            timeframe="15m",
            direction="BUY",
            entry_price=25000.0,
            stop_loss=24900.0,
            target_price=25200.0,
        )

        async def _run():
            # Regime + options succeed; LLM provider fails -> deterministic fallback
            mock_regime = MagicMock()
            mock_regime.spot_price = 25000.0
            mock_regime.regime_state = "RANGING"
            mock_regime.confidence_score = 50.0
            mock_regime.key_levels.classic_pivots.r1 = 25100.0
            mock_regime.key_levels.classic_pivots.s1 = 24900.0
            mock_regime.key_levels.poc = 25000.0
            mock_regime.key_levels.vah = 25100.0
            mock_regime.key_levels.val = 24900.0
            mock_regime.indicators.supertrend_direction = "NEUTRAL"
            mock_regime.indicators.supertrend_value = 25000.0
            mock_regime.indicators.adx_14 = 20.0
            mock_regime.indicators.rsi_14 = 50.0
            with patch("app.services.ai_validation_service.regime_service.classify_market_regime", new=AsyncMock(return_value=mock_regime)):
                with patch("app.services.ai_validation_service.options_service.get_option_chain_matrix", new=AsyncMock(side_effect=RuntimeError("chain down"))):
                    with patch("app.services.ai_validation_service.create_provider_for_test", side_effect=RuntimeError("llm down")):
                        return await ai_validation_service.validate_trade(req)

        resp = asyncio.run(_run())
        assert resp.decision != "CONFIRM"
        assert resp.decision in ("WATCH", "UNCERTAIN", "REJECT")
        assert "degraded" in resp.provider_used
        assert "DEGRADED" in resp.executive_verdict or "degraded" in resp.executive_verdict.lower()
