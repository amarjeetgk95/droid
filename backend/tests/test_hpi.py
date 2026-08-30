"""HPI service-level tests — §2, §6-§13, §15 behaviors."""
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
def test_universe_is_exactly_seven(svc):
    sel = svc.get_selection()
    assert [e.symbol for e in sel.entries] == C.HPI_UNIVERSE
    assert len(C.HPI_UNIVERSE) == 7


def test_unknown_derivative_rejected(svc):
    with pytest.raises(HPIValidationError):
        svc.update_selection([DerivativeSelectionEntry(symbol="DOGE", enabled=True)])


def test_invalid_category_rejected(svc):
    with pytest.raises(HPIValidationError):
        svc.update_selection([DerivativeSelectionEntry(
            symbol="BTC", enabled=True, data_categories=["option_chain"])])  # index-only category


def test_disabled_derivative_blocks_import(svc):
    svc.update_selection([DerivativeSelectionEntry(symbol="SOL", enabled=False)])
    req = ImportRequest(symbol="SOL", retention_days=7, sampling_interval="1h")
    with pytest.raises(HPIValidationError, match="not enabled"):
        svc.run_import(req)


def test_disabled_derivative_rejects_live_capture(svc):
    svc.update_selection([DerivativeSelectionEntry(symbol="ETH", enabled=False)])
    assert svc.capture_live_record("ETH", "funding", (1.0, 2.0)) is False
    _enable_all(svc, "ETH")
    assert svc.capture_live_record("ETH", "funding", (1.0, 2.0)) is True


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


def test_import_cap_warning_on_oversized_dataset(svc):
    _enable_all(svc, "BTC")
    preview = svc.estimate_import(ImportRequest(
        symbol="BTC", retention_days=365 * 2, sampling_interval="1m"))  # ~1M records
    assert preview.warnings
    with pytest.raises(HPIValidationError, match="cap"):
        svc.run_import(ImportRequest(
            symbol="BTC", retention_days=365 * 2, sampling_interval="1m"))


def test_per_category_independent_periods(svc):
    """§4 — each derivative/category gets its own period."""
    _enable_all(svc, "BTC")
    end = datetime(2026, 8, 30, tzinfo=timezone.utc)
    svc.run_import(ImportRequest(symbol="BTC", categories=["1m_market_data"],
                                 start_date=end - timedelta(days=180), end_date=end, sampling_interval="1h"))
    svc.run_import(ImportRequest(symbol="BTC", categories=["funding"],
                                 start_date=end - timedelta(days=30), end_date=end, sampling_interval="1h"))
    cov = svc.get_coverage("BTC")
    md = next(d for d in cov.datasets if d.category == "1m_market_data")
    fund = next(d for d in cov.datasets if d.category == "funding")
    assert md.coverage_months == pytest.approx(6.0, abs=0.2)
    assert fund.coverage_months == pytest.approx(1.0, abs=0.1)


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
    _enable_all(svc, "BTC")
    _import(svc, "BTC", days=200, sampling="1h", categories=["liquidations"])
    total = svc.store.count("BTC", "liquidations")
    # older_than_6_months deletes the first ~20 days
    p1 = svc.preview_delete(DeleteRequest(symbol="BTC", categories=["liquidations"],
                                          range_type="older_than_6_months"))
    r1 = svc.confirm_delete(p1.confirmation_token)
    assert 0 < r1.records_deleted < total
    # all_time deletes the rest
    p2 = svc.preview_delete(DeleteRequest(symbol="BTC", categories=["liquidations"],
                                          range_type="all_time"))
    r2 = svc.confirm_delete(p2.confirmation_token)
    assert svc.store.count("BTC", "liquidations") == 0
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
    assert svc.store.count("NIFTY", "option_chain") > 0

    # Protected + explicit user deletion requires allow_protected (§13)
    p = svc.preview_delete(DeleteRequest(symbol="NIFTY", categories=["option_chain"],
                                         range_type="all_time"))
    r = svc.confirm_delete(p.confirmation_token)
    assert r.records_deleted == 0  # skipped — protected
    p = svc.preview_delete(DeleteRequest(symbol="NIFTY", categories=["option_chain"],
                                         range_type="all_time", allow_protected=True))
    r = svc.confirm_delete(p.confirmation_token)
    assert r.records_deleted > 0

    # Unprotected + auto-delete ON → old records removed (§12)
    svc.update_policy(pol.policy_id, RetentionPolicyUpdate(
        protected=False, auto_delete_enabled=True))
    svc.run_import(ImportRequest(
        symbol="NIFTY", categories=["option_chain"],
        start_date=now - timedelta(days=120), end_date=now, sampling_interval="1h"))
    entries = svc.run_auto_delete(now=now)
    assert len(entries) == 1
    assert entries[0].reason == "auto_delete"
    remaining = svc.store.records("NIFTY", "option_chain")
    cutoff = (now - timedelta(days=30)).timestamp()
    assert all(r[0] > cutoff for r in remaining)


# ---------------------------------------------------------------------------
# §9/§15 — Coverage & engine after deletion
# ---------------------------------------------------------------------------
def test_engine_reports_coverage_and_confidence(svc):
    _enable(svc, "NIFTY", ["1m_market_data", "option_chain"])
    _import(svc, "NIFTY", days=180, sampling="1h")
    engine = HPITrendPatternEngine(svc)
    analysis = engine.analyze("NIFTY", "5m")
    assert analysis.historical_coverage_months == pytest.approx(6.0, abs=0.2)
    assert "6 months" in analysis.historical_coverage_label
    assert analysis.similar_setups > 0
    assert analysis.confidence > 0
    assert analysis.derivative_coverage == "FULL"
    assert analysis.warnings == []


def test_engine_reduced_confidence_after_deletion(svc):
    _enable(svc, "NIFTY", ["1m_market_data"])
    _import(svc, "NIFTY", days=180, sampling="1h", categories=["1m_market_data"])
    engine = HPITrendPatternEngine(svc)
    before = engine.analyze("NIFTY", "5m")

    # Delete the most recent 30 days of 1m data (§9 — deletion must be visible)
    p = svc.preview_delete(DeleteRequest(symbol="NIFTY", categories=["1m_market_data"],
                                         range_type="last_30_days"))
    svc.confirm_delete(p.confirmation_token)

    analysis = engine.analyze("NIFTY", "5m")
    assert analysis.derivative_coverage == "PARTIAL"
    assert analysis.missing_dataset is not None
    assert any("Partial" in w for w in analysis.warnings)
    # coverage shrinks and confidence is reduced vs the full-history run
    assert analysis.historical_coverage_months < before.historical_coverage_months
    assert analysis.confidence < before.confidence
    # deleted data is never reconstructed — newer records are gone
    recs = svc.store.records("NIFTY", "1m_market_data")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
    assert all(r[0] <= cutoff for r in recs)


def test_engine_no_data_for_disabled_derivative(svc):
    engine = HPITrendPatternEngine(svc)
    analysis = engine.analyze("SENSEX", "5m")
    assert analysis.derivative_coverage == "DISABLED"
    assert analysis.confidence == 0.0
    assert analysis.similar_setups == 0


# ---------------------------------------------------------------------------
# §11 — Policy CRUD
# ---------------------------------------------------------------------------
def test_policy_crud_and_validation(svc):
    pol = svc.create_policy(RetentionPolicy(
        instrument="SOL", derivative_category="CRYPTO", feature_group="funding",
        retention_days=30, sampling_interval="1h", auto_delete_enabled=True,
    ))
    assert pol.policy_id in {p.policy_id for p in svc.list_policies("SOL")}
    updated = svc.update_policy(pol.policy_id, RetentionPolicyUpdate(retention_days=45, protected=True))
    assert updated.retention_days == 45 and updated.protected
    assert svc.delete_policy(pol.policy_id)
    assert svc.list_policies("SOL") == []
    with pytest.raises(HPIValidationError):
        svc.create_policy(RetentionPolicy(
            instrument="SOL", derivative_category="CRYPTO", feature_group="option_chain"))


def test_state_persists_across_restart(tmp_path):
    svc1 = HPIService(state_path=tmp_path / "hpi_state.json")
    _enable_all(svc1, "SOL")
    svc1.run_import(ImportRequest(symbol="SOL", categories=["funding"],
                                  retention_days=10, sampling_interval="1h"))
    svc1.create_policy(RetentionPolicy(
        instrument="SOL", derivative_category="CRYPTO", feature_group="funding",
        retention_days=30))
    svc1.save_state()

    svc2 = HPIService(state_path=tmp_path / "hpi_state.json")
    assert svc2.is_enabled("SOL")
    assert svc2.store.count("SOL", "funding") > 0
    assert len(svc2.list_policies("SOL")) == 1
    assert svc2.list_audit() == []  # nothing deleted — log empty but functional
