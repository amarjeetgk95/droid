"""Institutional flow PIT + overlay regression tests (audit remediation)."""
from datetime import datetime, timezone, timedelta


def test_flow_as_of_is_pit_safe():
    from app.institutional.flow_store import flow_store

    # Before any available_time -> None, never leak (history starts 2026-01-14,
    # seed-only fallback starts 2026-08-27; use 2025 to cover both).
    early = datetime(2025, 1, 5, 12, 0, tzinfo=timezone.utc)
    # Fresh store so history-file presence does not leak between tests.
    from app.institutional.flow_store import InstitutionalFlowStore

    fresh = InstitutionalFlowStore()
    assert fresh.as_of(early) is None
    # After window -> latest row only, pit_ok, futures UNAVAILABLE.
    # Fail-closed on staleness: history (2026-09-11) is fresh for 2026-09-13;
    # a seed-only store (2026-08-29) is >5 days stale and must return None.
    late = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    snap = fresh.as_of(late)
    from pathlib import Path as _P
    _hist = _P(__file__).resolve().parents[1] / "data" / "fii_dii_history.json"
    if _hist.exists():
        assert snap is not None and snap.pit_ok is True
        # With history file: 2026-09-11; seed-only fallback: 2026-08-29.
        assert snap.event_date in ("2026-09-11", "2026-08-29")
        assert snap.futures_status == "UNAVAILABLE"
        assert snap.live_available is False
    else:
        assert snap is None


def test_flow_history_loaded_when_present():
    from pathlib import Path
    from app.institutional.flow_store import InstitutionalFlowStore

    p = Path(__file__).resolve().parents[1] / "data" / "fii_dii_history.json"
    if not p.exists():
        return
    fresh = InstitutionalFlowStore()
    rows = fresh.to_training_rows()
    assert len(rows) >= 100  # 152-row proxy history
    with_fo = sum(1 for r in rows if r.get("fii_fut_net") is not None)
    assert with_fo >= 50  # F&O present on older rows, missing (None) on recent


def test_flow_training_rows_pass_leakage_gate():
    from app.institutional.flow_store import flow_store
    from app.ml.leakage_gate import leakage_gate

    rows = flow_store.to_training_rows()
    assert len(rows) >= 3
    ok, violations = leakage_gate.validate_features_matrix(rows)
    assert ok, violations


def test_overlay_regime_conditioning():
    from app.signals.institutional_overlay import compute_institutional_adjustment

    class _F:
        event_date = "2026-08-29"
        fii_cash_5d_z = -2.0
        dii_cash_5d_z = -1.0
        fii_fut_net = -16270
        fii_lsr = 0.85
        pit_ok = True

    d_trend, i_trend = compute_institutional_adjustment("LONG_PUT", "TREND_DOWN", _F(), {"distance_to_expiry_days": 3}, {})
    d_range, i_range = compute_institutional_adjustment("LONG_PUT", "RANGE", _F(), {"distance_to_expiry_days": 3}, {})
    assert i_trend["applied"] and i_range["applied"]
    assert abs(d_trend) > abs(d_range)  # same print, muted in sideways
    assert abs(d_trend) <= 5.0 and abs(d_range) <= 5.0


def test_overlay_divergence_forces_validated():
    from app.signals.institutional_overlay import compute_institutional_adjustment

    class _F:
        event_date = "2026-08-29"
        fii_cash_5d_z = -2.5
        dii_cash_5d_z = 0.0
        fii_fut_net = -10000
        fii_lsr = 0.80
        pit_ok = True

    part = {"label": "SHORT_COVERING", "support_hold": True, "put_writing": True}
    _, info = compute_institutional_adjustment("LONG_PUT", "TREND_DOWN", _F(), {"distance_to_expiry_days": 3}, part)
    assert info["downgrade_to_validated"] is True


def test_overlay_unverifiable_flow_ignored():
    from app.signals.institutional_overlay import compute_institutional_adjustment

    d, info = compute_institutional_adjustment("LONG_CALL", "TREND_UP", None, {}, {})
    assert d == 0.0 and info["applied"] is False


def test_confluence_overlay_capped():
    from app.signals.confluence import confluence_engine
    from app.signals.strategies.base import SignalCandidate

    cand = SignalCandidate(
        candidate_id="t",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25100.0,
        entry_min=25095.0,
        entry_max=25105.0,
        trigger=25110.0,
        stop_loss=25080.0,
        target_1=25140.0,
        target_2=25170.0,
        risk_points=30.0,
        risk_reward_t1=1.5,
        risk_reward_t2=2.0,
        technical_score=70.0,
        mtf_score=70.0,
        fno_score=70.0,
        regime_score=70.0,
    )
    base = confluence_engine.fuse(cand, ai_result=None, ml_prediction=None, institutional=None)
    boosted = confluence_engine.fuse(cand, ai_result=None, ml_prediction=None,
                                     institutional={"applied": True, "delta": 50.0})
    assert boosted - base <= 5.0 + 1e-9


def test_fno_context_has_pit_timestamps():
    import asyncio
    from app.fno.context import get_fno_context

    # Offline env returns available=False BUT must still carry PIT timestamps.
    data = asyncio.run(get_fno_context("NIFTY"))
    assert "available_time" in data and "timestamp_ms" in data
