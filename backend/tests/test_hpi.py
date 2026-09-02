"""HPI service-level tests — §2, §6-§13, §15 behaviors (NIFTY, BANKNIFTY, SENSEX)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.hpi import constants as C
from app.hpi.engine import HPITrendPatternEngine
from app.hpi.models import (
    DeleteRequest, DerivativeSelectionEntry, ImportRequest, RetentionPolicy,
    RetentionPolicyUpdate,
)
from app.hpi.service import HPIService, HPIBudgetBlocked, HPIValidationError


@pytest.fixture
def svc(tmp_path):
    return HPIService(state_path=tmp_path / "hpi_state.json")


def _enable_all(svc: HPIService, symbol: str):
    svc.update_selection([DerivativeSelectionEntry(
        symbol=symbol, enabled=True, data_categories=C.categories_for(symbol),
    )])


def _enable(svc: HPIService, symbol: str, categories: list[str]):
    svc.update_selection([DerivativeSelectionEntry(symbol=symbol, enabled=True, data_categories=categories)])


def _import(svc: HPIService, symbol: str, days: int, sampling: str = "1h", categories=None):
    end = datetime(2026, 8, 30, tzinfo=timezone.utc)
    start = end - timedelta(days=days)
    return svc.run_import(ImportRequest(
        symbol=symbol, categories=categories or ["1m_market_data", "option_chain"],
        start_date=start, end_date=end, sampling_interval=sampling,
    ))


# ---------------------------------------------------------------------------
# §1/§2 — Universe & selection
# ---------------------------------------------------------------------------
def test_universe_is_exactly_three(svc):
    sel = svc.get_selection()
    assert [e.symbol for e in sel.entries] == C.HPI_UNIVERSE
    assert len(C.HPI_UNIVERSE) == 3
    assert set(C.HPI_UNIVERSE) == {"NIFTY", "BANKNIFTY", "SENSEX"}


def test_unknown_derivative_rejected(svc):
    with pytest.raises(HPIValidationError):
        svc.update_selection([DerivativeSelectionEntry(symbol="DOGE", enabled=True)])


def test_invalid_category_rejected(svc):
    with pytest.raises(HPIValidationError):
        svc.update_selection([DerivativeSelectionEntry(
            symbol="NIFTY", enabled=True, data_categories=["invalid_unknown_cat"])])


# ---------------------------------------------------------------------------
# §3/§4/§10/§16 — Import, periods, storage estimation
# ---------------------------------------------------------------------------
def test_import_requires_period(svc):
    _enable_all(svc, "NIFTY")
    with pytest.raises(HPIValidationError, match="start_date"):
        svc.run_import(ImportRequest(symbol="NIFTY", categories=["iv"], sampling_interval="1h"))


def test_import_executes_and_tracks_storage(svc):
    _enable_all(svc, "NIFTY")
    result = _import(svc, "NIFTY", days=30, sampling="1h")
    # 30 days of 1h bars ≈ 721 records per category
    assert result.records_imported == 2 * 721
    report = svc.get_storage_report()
    assert report.status in ("WITHIN_TARGET", "WARNING")
    nifty = next(d for d in report.datasets if d.symbol == "NIFTY")
    assert nifty.records_stored == 2 * 721
    assert nifty.historical_period_months == pytest.approx(1.0, abs=0.1)
    assert nifty.oldest_record is not None and nifty.newest_record is not None


def test_budget_blocks_when_projected_exceeds_hard_ceiling(svc, monkeypatch):
    monkeypatch.setattr(C, "STORAGE_HARD_CEILING_MB", 0.01)
    _enable_all(svc, "NIFTY")
    req = ImportRequest(symbol="NIFTY", retention_days=30, sampling_interval="1h")
    preview = svc.estimate_import(req)
    assert preview.status == "EXCEEDS_HARD"
    assert preview.blocked
    assert preview.alternatives  # §10 alternatives offered
    with pytest.raises(HPIBudgetBlocked):
        svc.run_import(req)


def test_per_category_independent_periods(svc):
    """§4 — each derivative/category gets its own period."""
    _enable_all(svc, "BANKNIFTY")
    end = datetime(2026, 8, 30, tzinfo=timezone.utc)
    svc.run_import(ImportRequest(symbol="BANKNIFTY", categories=["1m_market_data"],
                                 start_date=end - timedelta(days=180), end_date=end, sampling_interval="1h"))
    svc.run_import(ImportRequest(symbol="BANKNIFTY", categories=["iv"],
                                 start_date=end - timedelta(days=30), end_date=end, sampling_interval="1h"))
    cov = svc.get_coverage("BANKNIFTY")
    md = next(d for d in cov.datasets if d.category == "1m_market_data")
    iv = next(d for d in cov.datasets if d.category == "iv")
    assert md.coverage_months == pytest.approx(6.0, abs=0.2)
    assert iv.coverage_months == pytest.approx(1.0, abs=0.1)


# ---------------------------------------------------------------------------
# §6/§7/§8 — Deletion: two-step confirm, scope isolation
# ---------------------------------------------------------------------------
def test_delete_requires_confirmation_token(svc):
    _enable_all(svc, "NIFTY")
    _import(svc, "NIFTY", days=60, sampling="1h")
    with pytest.raises(HPIValidationError, match="token"):
        svc.confirm_delete("bogus-token")


def test_delete_scope_isolation(svc):
    """§8 — deleting option-chain data retains 1m candles and everything else."""
    _enable_all(svc, "NIFTY")
    _import(svc, "NIFTY", days=60, sampling="1h")
    before_md = svc.store.count("NIFTY", "1m_market_data")
    assert before_md > 0 and svc.store.count("NIFTY", "option_chain") > 0

    preview = svc.preview_delete(DeleteRequest(
        symbol="NIFTY", categories=["option_chain"],
        range_type="all_time", reason="test cleanup",
    ))
    assert preview.total_records > 0
    assert "Option-chain confirmation will be unavailable" in preview.analytical_impact[0]
    assert "Not affected" in preview.price_technical_impact

    result = svc.confirm_delete(preview.confirmation_token)
    assert result.records_deleted == preview.total_records
    # 1m candles fully retained; option chain for that window gone
    assert svc.store.count("NIFTY", "1m_market_data") == before_md
    assert svc.store.count("NIFTY", "option_chain") == 0
    # audit recorded (§14)
    audit = svc.list_audit("NIFTY")
    assert len(audit) == 1
    assert audit[0].dataset == "option_chain"
    assert audit[0].reason == "test cleanup"
    assert audit[0].records_deleted == preview.total_records


def test_delete_range_types(svc):
    _enable_all(svc, "SENSEX")
    _import(svc, "SENSEX", days=200, sampling="1h", categories=["iv"])
    total = svc.store.count("SENSEX", "iv")
    # older_than_6_months deletes the first ~20 days
    p1 = svc.preview_delete(DeleteRequest(symbol="SENSEX", categories=["iv"],
                                          range_type="older_than_6_months"))
    r1 = svc.confirm_delete(p1.confirmation_token)
    assert 0 < r1.records_deleted < total
    # all_time deletes the rest
    p2 = svc.preview_delete(DeleteRequest(symbol="SENSEX", categories=["iv"],
                                          range_type="all_time"))
    r2 = svc.confirm_delete(p2.confirmation_token)
    assert svc.store.count("SENSEX", "iv") == 0
    assert r1.records_deleted + r2.records_deleted == total


# ---------------------------------------------------------------------------
# §12/§13 — Auto-delete & protection
# ---------------------------------------------------------------------------
def test_auto_delete_respects_protection_and_optin(svc):
    _enable_all(svc, "NIFTY")
    _import(svc, "NIFTY", days=120, sampling="1h")
    now = datetime(2026, 8, 30, tzinfo=timezone.utc)
    # Auto-delete OFF by default → nothing happens
    assert svc.run_auto_delete(now=now) == []

    # Protected + auto-delete ON → skipped (§13)
    pol = svc.create_policy(RetentionPolicy(
        instrument="NIFTY", derivative_category="INDEX", feature_group="option_chain",
        retention_days=30, auto_delete_enabled=True, protected=True,
    ))
    assert svc.run_auto_delete(now=now) == []

    # Unprotect → auto-delete purges older records and records audit
    svc.update_policy(pol.policy_id, RetentionPolicyUpdate(protected=False))
    entries = svc.run_auto_delete(now=now)
    assert len(entries) == 1
    assert entries[0].records_deleted > 0
    assert "auto_delete" in entries[0].reason
    assert len(svc.list_audit("NIFTY")) == 1


# ---------------------------------------------------------------------------
# §15 — Trend & pattern analysis integration
# ---------------------------------------------------------------------------
def test_engine_reports_coverage_and_confidence(svc):
    _enable_all(svc, "NIFTY")
    _import(svc, "NIFTY", days=180, sampling="1h",
            categories=["1m_market_data", "option_chain", "iv", "pcr", "futures", "open_interest", "greeks"])

    engine = HPITrendPatternEngine(svc)
    res = engine.analyze("NIFTY", timeframe="5m")
    assert res.derivative_coverage in ("FULL", "PARTIAL")
    assert res.confidence > 50.0
    assert len(res.setups) > 0


def test_engine_reduced_confidence_after_deletion(svc):
    """§15 — partial coverage degrades confidence but never crashes analysis."""
    _enable_all(svc, "NIFTY")
    _import(svc, "NIFTY", days=180, sampling="1h",
            categories=C.categories_for("NIFTY"))

    engine = HPITrendPatternEngine(svc)
    res_full = engine.analyze("NIFTY")
    assert res_full.derivative_coverage == "FULL"
    assert res_full.confidence > 0

    # Delete option_chain and IV
    p = svc.preview_delete(DeleteRequest(
        symbol="NIFTY", categories=["option_chain", "iv"], range_type="all_time"))
    svc.confirm_delete(p.confirmation_token)

    res_partial = engine.analyze("NIFTY")
    assert res_partial.derivative_coverage == "PARTIAL"
    assert res_partial.confidence < res_full.confidence


def test_policy_crud_and_validation(svc):
    pol = svc.create_policy(RetentionPolicy(
        instrument="NIFTY", derivative_category="INDEX", feature_group="iv",
        retention_days=60, sampling_interval="5m", auto_delete_enabled=False, protected=True,
    ))
    assert len(pol.policy_id) > 0
    assert len(svc.list_policies("NIFTY")) == 1

    updated = svc.update_policy(pol.policy_id, RetentionPolicyUpdate(retention_days=90))
    assert updated.retention_days == 90

    assert svc.delete_policy(pol.policy_id) is True
    assert len(svc.list_policies("NIFTY")) == 0


def test_state_persists_across_restart(tmp_path):
    p = tmp_path / "hpi_state.json"
    svc1 = HPIService(state_path=p)
    _enable_all(svc1, "NIFTY")
    _import(svc1, "NIFTY", days=30, sampling="1h")
    svc1.create_policy(RetentionPolicy(
        instrument="NIFTY", derivative_category="INDEX", feature_group="pcr",
        retention_days=45, sampling_interval="1h",
    ))
    svc1.save_state()

    svc2 = HPIService(state_path=p)
    assert svc2.is_enabled("NIFTY")
    assert svc2.store.count("NIFTY", "1m_market_data") > 0
    assert len(svc2.list_policies("NIFTY")) == 1


def test_seed_loads_all_derivatives(svc):
    """One-click seed: loads history for NIFTY, BANKNIFTY, SENSEX in one shot."""
    summary = svc.seed_defaults(sampling_interval="1h", retention_days=30)
    assert summary["status"] == "seeded"
    assert summary["records_imported"] > 0
    assert svc.is_seeded()

    rep = svc.get_storage_report()
    assert all(d.enabled for d in rep.datasets)
    assert all(d.records_stored > 0 for d in rep.datasets)
