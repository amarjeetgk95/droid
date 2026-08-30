"""HPI API — user-controlled derivative & historical data endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.hpi import constants as C
from app.hpi.engine import HPITrendPatternEngine
from app.hpi.models import (
    DeleteConfirmRequest, DeleteRequest, DerivativeSelectionState,
    ImportRequest, RetentionPolicy, RetentionPolicyUpdate,
)
from app.hpi.service import HPIBudgetBlocked, HPIValidationError, hpi_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/hpi", tags=["hpi"])
engine = HPITrendPatternEngine(hpi_service)


def _meta() -> ApiMeta:
    return ApiMeta(provider="hpi_engine", timestamp=datetime.now(timezone.utc), status=DataStatus.DEMO)


def _ok(data) -> dict:
    return {"data": data, "error": None, "meta": _meta().model_dump(mode="json")}


def _err(e: Exception):
    if isinstance(e, HPIValidationError):
        raise HTTPException(status_code=400, detail=str(e))
    if isinstance(e, HPIBudgetBlocked):
        raise HTTPException(status_code=409, detail={
            "message": str(e),
            "estimate": e.estimate.model_dump(mode="json"),
            "alternatives": C.STORAGE_ALTERNATIVES,
        })
    raise HTTPException(status_code=500, detail=str(e))


@router.get("/universe")
async def get_universe():
    """§1 — the fixed seven-derivative universe (nothing else is ever added)."""
    return _ok({
        "derivatives": [
            {"symbol": sym, **meta, "data_categories": C.categories_for(sym)}
            for sym, meta in C.HPI_DERIVATIVES.items()
        ],
        "sampling_intervals": list(C.SAMPLING_INTERVALS.keys()),
        "storage_budget": {
            "target_mb": C.STORAGE_TARGET_MB,
            "warning_mb": C.STORAGE_WARNING_MB,
            "hard_ceiling_mb": C.STORAGE_HARD_CEILING_MB,
        },
        "delete_range_types": ["last_30_days", "last_3_months", "older_than_6_months", "custom", "all_time"],
        "note": "HPI is permanently restricted to these seven derivatives.",
    })


@router.get("/selection")
async def get_selection():
    return _ok(hpi_service.get_selection().model_dump(mode="json"))


@router.put("/selection")
async def update_selection(state: DerivativeSelectionState):
    """§2 — enable/disable derivatives and their data categories."""
    try:
        return _ok(hpi_service.update_selection(state.entries).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.get("/policies")
async def list_policies(symbol: str | None = Query(default=None)):
    return _ok([p.model_dump(mode="json") for p in hpi_service.list_policies(symbol)])


@router.post("/policies")
async def create_policy(policy: RetentionPolicy):
    try:
        return _ok(hpi_service.create_policy(policy).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.patch("/policies/{policy_id}")
async def update_policy(policy_id: str, update: RetentionPolicyUpdate):
    try:
        return _ok(hpi_service.update_policy(policy_id, update).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.delete("/policies/{policy_id}")
async def delete_policy(policy_id: str):
    try:
        if not hpi_service.delete_policy(policy_id):
            raise HPIValidationError(f"Policy '{policy_id}' not found")
        return _ok({"policy_id": policy_id, "status": "removed"})
    except Exception as e:
        _err(e)


@router.post("/seed")
async def seed_defaults(
    force: bool = Query(default=False),
    sampling_interval: str = Query(default="1h"),
    retention_days: int = Query(default=180, ge=1, le=3650),
):
    """One-click bootstrap — enable all derivatives and load their history."""
    try:
        return _ok(hpi_service.seed_defaults(
            force=force, sampling_interval=sampling_interval, retention_days=retention_days))
    except Exception as e:
        _err(e)


@router.get("/storage/report")
async def storage_report():
    """§5 — per-derivative data-management cards + storage budget status."""
    return _ok(hpi_service.get_storage_report().model_dump(mode="json"))


@router.post("/import")
async def import_history(req: ImportRequest):
    """§16 — estimate (estimate_only=true) or execute the historical import."""
    try:
        return _ok(hpi_service.run_import(req).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.post("/delete/preview")
async def delete_preview(req: DeleteRequest):
    """§6/§7 — preview the deletion; returns a confirmation token."""
    try:
        return _ok(hpi_service.preview_delete(req).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.post("/delete/confirm")
async def delete_confirm(req: DeleteConfirmRequest):
    """§7 — execute the confirmed deletion (two-step; no accidental clicks)."""
    try:
        return _ok(hpi_service.confirm_delete(req.confirmation_token, reason=req.reason).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.get("/audit/deletions")
async def deletion_audit(symbol: str | None = Query(default=None)):
    """§14 — deletion audit log (survives the underlying record removal)."""
    return _ok([a.model_dump(mode="json") for a in hpi_service.list_audit(symbol)])


@router.post("/maintenance/auto-delete")
async def run_auto_delete():
    """§12 — run the optional auto-delete sweep now (protected data skipped)."""
    entries = hpi_service.run_auto_delete()
    return _ok({
        "executed": True,
        "datasets_affected": len(entries),
        "records_deleted": sum(e.records_deleted for e in entries),
        "audit": [e.model_dump(mode="json") for e in entries],
    })


@router.get("/coverage/{symbol}")
async def coverage(symbol: str):
    """§9 — what historical derivative data is available / missing / deleted."""
    try:
        if symbol.upper() not in C.HPI_UNIVERSE:
            raise HPIValidationError(f"Unsupported derivative '{symbol}'")
        return _ok(hpi_service.get_coverage(symbol).model_dump(mode="json"))
    except Exception as e:
        _err(e)


@router.get("/analysis/{symbol}")
async def analysis(symbol: str, timeframe: str = Query(default="5m")):
    """§15 — coverage-aware historical pattern analysis."""
    try:
        if symbol.upper() not in C.HPI_UNIVERSE:
            raise HPIValidationError(f"Unsupported derivative '{symbol}'")
        return _ok(engine.analyze(symbol, timeframe).model_dump(mode="json"))
    except Exception as e:
        _err(e)
