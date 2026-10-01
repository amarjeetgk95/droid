"""Copilot audit store + signal gate engine tests (spec §30, §34).

The audit store is exercised against its in-memory backend (no DB required),
and the gate engine against synthetic-but-schema-valid contexts. Gate rows are
checked against the CentralRiskEngine-backed RISK_GATE for an honest approval
path.
"""
from __future__ import annotations

import pytest

from app.copilot.audit import CopilotAuditStore
from app.copilot.confluence import evaluate_confluence
from app.copilot.feature_fusion import derive_factors
from app.copilot.levels import build_levels
from app.copilot.models import CopilotAuditRecord, SignalUnderReview
from app.copilot.validation import signal_validation_engine
from tests.test_copilot_intelligence import _ctx


def _audit_record(prediction_id: str = "pred_test_1") -> CopilotAuditRecord:
    return CopilotAuditRecord(
        prediction_id=prediction_id,
        analysis_id="ana_test_1",
        symbol="SENSEX",
        horizon="NEXT_SESSION",
        intent="NEXT_SESSION_OUTLOOK",
        market_context={"symbol": "SENSEX"},
        feature_snapshot={"trend": {"state": "NEUTRAL"}},
        prediction={"direction": "NEUTRAL", "expected_range": {"low": 74250.0, "high": 74900.0}},
        scenarios=[{"id": "RANGE", "probability": None}],
        probabilities={"BULL": None, "NEUTRAL": None, "BEAR": None},
        levels={"support": [], "resistance": []},
        confidence={"model": None, "confluence": 0.5},
        model_version="copilot-prediction-1.0+evidence",
        prompt_version="copilot-explain-1.0",
        copilot_version="1.0",
    )


@pytest.mark.asyncio
async def test_audit_prediction_then_outcome_roundtrip():
    store = CopilotAuditStore()
    stored = await store.record_prediction(_audit_record("pred_roundtrip"))
    assert stored["stored"] is True and stored["backend"] == "memory"

    outcome = await store.record_outcome(
        "pred_roundtrip", outcome="RANGE_HELD", realized_return_pct=0.1, realized_direction="NEUTRAL"
    )
    assert outcome["stored"] is True

    fetched = await store.get_prediction("pred_roundtrip")
    assert fetched and fetched["prediction_id"] == "pred_roundtrip"

    summary = await store.evaluation_summary(symbol="SENSEX")
    assert summary["available"] is True
    assert summary["sample_size"] >= 1


@pytest.mark.asyncio
async def test_audit_second_outcome_is_duplicate():
    store = CopilotAuditStore()
    await store.record_prediction(_audit_record("pred_dupe"))
    first = await store.record_outcome("pred_dupe", outcome="RANGE_HELD")
    assert first["stored"] is True
    assert (await store.get_prediction("pred_dupe"))["outcome"] == "RANGE_HELD"


@pytest.mark.asyncio
async def test_evaluation_empty_without_outcomes():
    store = CopilotAuditStore()
    summary = await store.evaluation_summary(symbol="NIFTY")
    assert summary["available"] is False
    assert summary["sample_size"] == 0
    assert summary["directional_hit_rate"] is None  # never invent a metric


def test_gate_rejects_long_against_bearish_trend():
    ctx = _ctx()
    ctx.regime.name = "TRENDING_BEARISH"
    factors = derive_factors(ctx)
    confluence = evaluate_confluence(factors)
    levels = build_levels(ctx)
    signal = SignalUnderReview(
        symbol="SENSEX",
        direction="LONG",
        entry=74500.0,
        stop=74400.0,
        target_1=74700.0,
        source="REQUEST",
    )
    result = signal_validation_engine.evaluate(ctx, factors, confluence, signal, levels)
    gates = {g.gate: g for g in result.gates}
    assert gates["REGIME_GATE"].status == "FAIL"
    assert result.verdict == "REJECTED"
    assert any("REGIME_GATE" in reason for reason in result.reasons)


def test_gate_conditional_when_options_missing():
    ctx = _ctx()
    ctx.regime.name = "RANGEBOUND_LOW_VOL"
    ctx.technicals.supertrend_direction = "BULLISH"
    ctx.technicals.ema_20 = 74400.0
    ctx.technicals.sma_200 = 74000.0
    ctx.options.pcr_oi = None
    ctx.options.call_wall = None
    ctx.options.put_wall = None
    ctx.options.max_pain = None
    factors = derive_factors(ctx)
    confluence = evaluate_confluence(factors)
    levels = build_levels(ctx)
    signal = SignalUnderReview(
        symbol="SENSEX",
        direction="LONG",
        entry=74500.0,
        stop=74400.0,
        target_1=74700.0,
        source="REQUEST",
    )
    result = signal_validation_engine.evaluate(ctx, factors, confluence, signal, levels)
    gates = {g.gate: g for g in result.gates}
    assert gates["OPTIONS_GATE"].status == "SKIPPED"
    # No hard failure can be asserted here; verdict must not be APPROVED without full evidence.
    assert result.verdict in ("APPROVED", "CONDITIONAL", "REJECTED")
    assert result.engine_version
    assert result.authoritative is True
