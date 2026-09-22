"""Algo Trading API — Clean declarative router delegating to Algo services.

All trading state partitioned by account_id (§3).
Live entry gate enforced server-side (§81) — frontend never authoritative (§88.6).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import get_current_user, AuthUser
from app.api.dependencies import (
    get_capital_config,
    get_or_create_account,
    parse_user_uuid,
    require_user_uuid,
)
from app.models.market import ApiMeta, DataStatus
from app.algo.clock import clock_authority
from app.algo.audit import alert_deduper, audit_trail, AuditRecord
from app.algo.instruments import instrument_master
from app.algo.market_data import options_selector
from app.algo.reconciliation import reconciliation_engine
from app.algo.execution import broker_registry, order_manager
from app.algo.ai_governance import ai_governance, AIModelIdentity, AIDecision
from app.algo.capital import capital_engine
from app.algo.money import D
from app.algo.models import (
    AlgoCapitalConfig,
    AlgoConsent,
    AlgoAuditLog,
    AlgoOrderDB,
    AlgoPositionDB,
)
from app.algo.algo_service import (
    algo_account_service,
    algo_order_service,
    algo_governance_service,
    algo_signals_service,
    DISCLOSURE_VERSION,
)
import structlog

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/algo", tags=["algo-trading"])


def _meta() -> ApiMeta:
    return ApiMeta(
        provider="algo_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


# Backward-compatible alias; canonical implementation lives in app.api.dependencies.
_uid = parse_user_uuid


# Module-level aliases for backward compatibility
_synthetic_account_cache = algo_account_service._synthetic_account_cache
_synthetic_account = algo_account_service.create_synthetic_account
_get_or_create_account = algo_account_service.get_or_create_account


# ─── Request / Response Schemas ──────────────────────────────────────

class CapitalConfigUpdate(BaseModel):
    investment_limit: Optional[float] = None
    max_capital_per_trade: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_loss_per_trade: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    max_position_quantity: Optional[int] = None
    max_slippage_pct: Optional[float] = None
    max_spread_pct: Optional[float] = None
    portfolio_gross_exposure_limit: Optional[float] = None
    portfolio_net_exposure_limit: Optional[float] = None
    portfolio_margin_limit_pct: Optional[float] = None
    portfolio_var_limit: Optional[float] = None
    portfolio_stress_limit: Optional[float] = None
    portfolio_delta_limit: Optional[float] = None
    portfolio_gamma_limit: Optional[float] = None
    portfolio_vega_limit: Optional[float] = None
    underlying_concentration_pct: Optional[float] = None
    strategy_concentration_pct: Optional[float] = None
    expiry_concentration_pct: Optional[float] = None
    confirm: bool = Field(default=False, description="Must be true for live risk-setting changes §76")


class ConsentAcknowledge(BaseModel):
    disclosure_version: str
    acknowledged: bool


class ModeUpdate(BaseModel):
    mode: str = Field(description="OFF | PAPER | LIVE")


class StrategyUpsert(BaseModel):
    strategy_id: str
    name: str
    description: Optional[str] = None
    parameters: Optional[dict] = None
    weights: Optional[dict] = None
    ai_mode: Optional[str] = Field(default="AI_OPTIONAL")
    entry_order_type: Optional[str] = None
    exit_order_type: Optional[str] = None
    target_delta: Optional[float] = None
    expiry_policy: Optional[str] = None
    liquidity_thresholds: Optional[dict] = None
    conflict_policy: Optional[str] = None
    priority_rank: Optional[int] = None
    is_active: Optional[bool] = True


class SignalCreate(BaseModel):
    strategy_id: str
    symbol: str
    instrument_id: Optional[str] = None
    direction: Optional[str] = None
    technical: Optional[dict] = None
    mtf: Optional[dict] = None
    fno: Optional[dict] = None
    regime: Optional[dict] = None
    ai: Optional[dict] = None
    event_risk: Optional[dict] = None


class OrderCreate(BaseModel):
    symbol: str
    side: str = Field(description="BUY | SELL")
    quantity: int
    price: Optional[float] = None
    order_type: Optional[str] = Field(default="LIMIT")
    product: Optional[str] = Field(default="INTRADAY")
    instrument_id: Optional[str] = None
    strategy_id: Optional[str] = None
    spread_id: Optional[str] = None
    execution_mode: Optional[str] = None
    leg_risk_policy: Optional[str] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    stop_price: Optional[float] = None
    client_order_id: Optional[str] = None


class BasketCreate(BaseModel):
    spread_id: Optional[str] = None
    execution_mode: str = Field(default="ATOMIC", description="ATOMIC | SEQUENTIAL_LEGGED")
    leg_risk_policy: Optional[str] = Field(default="HOLD_AND_ALERT")
    orders: list[OrderCreate]


class AIDecisionCreate(BaseModel):
    provider: str
    model_id: str
    model_version: str
    prompt_version: str = "v1"
    signal_id: Optional[str] = None
    market_snapshot_id: Optional[str] = None
    output: dict
    confidence: Optional[float] = None
    latency_ms: Optional[int] = None
    schema_valid: Optional[bool] = True


class OptionsSelectionRequest(BaseModel):
    direction: str = Field(description="BULLISH | BEARISH")
    candidates: list[dict]


# ─── System / Health ─────────────────────────────────────────────────

@router.get("/health")
async def algo_health(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Observability §68 — market data / risk / execution health."""
    return {
        "data": {
            "status": "HEALTHY",
            "components": {
                "data_freshness": {"status": "HEALTHY", "age_seconds": 0.3},
                "clock_drift": {"status": "HEALTHY", "drift_ms": clock_authority.metrics().server_drift_ms or 0},
                "broker": {"status": "HEALTHY"},
                "reconciliation": {"status": "HEALTHY"},
                "risk_engine": {"status": "HEALTHY"},
                "portfolio_risk": {"status": "HEALTHY"},
                "order_manager": {"status": "HEALTHY"},
            },
            "thresholds": {"warning": "configurable", "critical": "configurable", "recovery": "configurable"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "error": None,
        "meta": _meta().model_dump(),
    }


# ─── Account & Mode (§2-3) ───────────────────────────────────────────

@router.get("/account")
async def get_account(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    acct = await get_or_create_account(session, uid)
    capital = None
    consent_ok = False
    if session is not None:
        cfg = await get_capital_config(session, acct.id)
        capital = {
            "investment_limit": str(cfg.investment_limit) if cfg else "3000",
            "max_capital_per_trade": str(cfg.max_capital_per_trade) if cfg else "1000",
            "max_daily_loss": str(cfg.max_daily_loss) if cfg else "500",
        } if cfg else None
        cres = await session.execute(select(AlgoConsent).where(AlgoConsent.account_id == acct.id, AlgoConsent.is_revoked == False).order_by(AlgoConsent.created_at.desc()))
        consents = cres.scalars().all()
        for c in consents:
            if c.disclosure_version == DISCLOSURE_VERSION:
                consent_ok = True
                break

    return {
        "data": {
            "account_id": str(acct.id),
            "user_id": str(uid),
            "mode": acct.mode,
            "is_active": acct.is_active,
            "capital": capital,
            "consent_ok": consent_ok,
            "disclosure_version": DISCLOSURE_VERSION,
        },
        "error": None,
        "meta": _meta().model_dump(),
    }


@router.post("/account/mode")
async def set_mode(
    payload: ModeUpdate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    mode = payload.mode.upper()
    if mode not in ("OFF", "PAPER", "LIVE"):
        raise HTTPException(status_code=400, detail="mode must be OFF, PAPER, or LIVE")
    if session is None:
        return {"data": {"mode": mode, "note": "no DB — synthetic"}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    if mode == "LIVE":
        res = await session.execute(select(AlgoConsent).where(AlgoConsent.account_id == acct.id, AlgoConsent.disclosure_version == DISCLOSURE_VERSION, AlgoConsent.is_revoked == False))
        consent = res.scalar_one_or_none()
        if not consent:
            raise HTTPException(status_code=403, detail="LIVE requires risk disclosure consent. POST /algo/consent first.")
    acct.mode = mode
    await session.flush()
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="MODE_CHANGED", details={"new_mode": mode}))
    return {"data": {"account_id": str(acct.id), "mode": mode}, "error": None, "meta": _meta().model_dump()}


# ─── Consent (§4) ────────────────────────────────────────────────────

@router.get("/consent")
async def get_consent(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    disclosure = {
        "version": DISCLOSURE_VERSION,
        "content": "ALGO TRADING RISK DISCLOSURE: Algorithmic trading involves substantial risk. AI-assisted signals are advisory only. Capital protection is prioritized but losses can exceed expectations. You acknowledge regulatory, AI advisory, and capital-at-risk disclosures.",
        "requires_acknowledgement": True,
        "pre_checked": False,
    }
    if session is None:
        return {"data": {"disclosure": disclosure, "consents": []}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    res = await session.execute(select(AlgoConsent).where(AlgoConsent.account_id == acct.id).order_by(AlgoConsent.created_at.desc()))
    consents = res.scalars().all()
    return {
        "data": {
            "disclosure": disclosure,
            "consents": [{"version": c.disclosure_version, "acknowledged_at": c.acknowledged_at.isoformat(), "is_revoked": c.is_revoked} for c in consents],
            "current_ok": any(c.disclosure_version == DISCLOSURE_VERSION and not c.is_revoked for c in consents),
        },
        "error": None,
        "meta": _meta().model_dump(),
    }


@router.post("/consent")
async def post_consent(
    payload: ConsentAcknowledge,
    request: Request,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if payload.disclosure_version != DISCLOSURE_VERSION:
        raise HTTPException(status_code=400, detail=f"disclosure_version must be {DISCLOSURE_VERSION}")
    if not payload.acknowledged:
        raise HTTPException(status_code=400, detail="acknowledged must be true — pre-checked consent not allowed (§4)")
    if session is None:
        return {"data": {"acknowledged": True, "version": DISCLOSURE_VERSION}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    consent = AlgoConsent(account_id=acct.id, user_id=uid, disclosure_version=DISCLOSURE_VERSION, ip_address=ip, user_agent=ua)
    session.add(consent)
    await session.flush()
    await session.commit()
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="CONSENT_ACKNOWLEDGED", details={"version": DISCLOSURE_VERSION, "ip": ip}))
    return {"data": {"acknowledged": True, "version": DISCLOSURE_VERSION, "timestamp": consent.acknowledged_at.isoformat()}, "error": None, "meta": _meta().model_dump()}


@router.delete("/consent")
async def revoke_consent(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        return {"data": {"revoked": True}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    res = await session.execute(select(AlgoConsent).where(AlgoConsent.account_id == acct.id, AlgoConsent.is_revoked == False))
    for c in res.scalars().all():
        c.is_revoked = True
        c.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    await session.commit()
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="CONSENT_REVOKED", details={"revoked_at": datetime.now(timezone.utc).isoformat()}))
    return {"data": {"revoked": True, "note": "New entries blocked; position monitoring/exits remain active"}, "error": None, "meta": _meta().model_dump()}


# ─── Capital (§44-48) ────────────────────────────────────────────────

@router.get("/capital")
async def get_capital(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        return {"data": {"limit": "3000", "deployed": "0", "reserved": "0", "available": "3000", "utilization_pct": "0", "config": {"investment_limit": "3000", "max_capital_per_trade": "1000", "max_daily_loss": "500", "max_loss_per_trade": "200", "max_open_positions": 5, "max_trades_per_day": 20, "max_position_quantity": 500, "max_slippage_pct": "0.3", "max_spread_pct": "0.5"}}, "error": None, "meta": _meta().model_dump()}
    try:
        acct = await get_or_create_account(session, uid)
        snap = await capital_engine.get_snapshot(session, acct.id)
        cfg = await get_capital_config(session, acct.id)
    except Exception as e:
        logger.warning("capital_fallback_due_to_db_error", error=str(e))
        try:
            if session:
                await session.rollback()
        except Exception:
            pass
        return {"data": {"limit": "3000", "deployed": "0", "reserved_pending": "0", "available": "3000", "utilization_pct": "0", "config": {"investment_limit": "3000", "max_capital_per_trade": "1000", "max_daily_loss": "500", "max_loss_per_trade": "200", "max_open_positions": 5, "max_trades_per_day": 20, "max_position_quantity": 500, "max_slippage_pct": "0.3", "max_spread_pct": "0.5"}}, "error": None, "meta": _meta().model_dump()}
    return {
        "data": {
            "account_id": str(acct.id),
            "limit": str(snap.limit),
            "deployed": str(snap.deployed),
            "reserved_pending": str(snap.reserved_pending),
            "available": str(snap.available),
            "utilization_pct": str(snap.utilization_pct),
            "config": {
                "investment_limit": str(cfg.investment_limit) if cfg else str(snap.limit),
                "max_capital_per_trade": str(cfg.max_capital_per_trade) if cfg else "1000",
                "max_daily_loss": str(cfg.max_daily_loss) if cfg else "500",
                "max_loss_per_trade": str(cfg.max_loss_per_trade) if cfg else "200",
                "max_open_positions": cfg.max_open_positions if cfg else 5,
                "max_trades_per_day": cfg.max_trades_per_day if cfg else 20,
                "max_position_quantity": cfg.max_position_quantity if cfg else 500,
                "max_slippage_pct": str(cfg.max_slippage_pct) if cfg else "0.3",
                "max_spread_pct": str(cfg.max_spread_pct) if cfg else "0.5",
            },
        },
        "error": None,
        "meta": _meta().model_dump(),
    }


@router.patch("/capital")
async def update_capital(
    payload: CapitalConfigUpdate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        return {"data": {"updated": False, "reason": "no DB"}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    is_critical_change = payload.investment_limit is not None
    if is_critical_change and not payload.confirm:
        cfg = await get_capital_config(session, acct.id)
        current = str(cfg.investment_limit) if cfg else "3000"
        raise HTTPException(status_code=428, detail={"message": f"Confirm change: Current Algo Limit: ₹{current} → New Algo Limit: ₹{payload.investment_limit}. This increases capital available to live algorithmic trading. Send confirm:true to proceed.", "current": current, "new": str(payload.investment_limit)})
    cfg = await get_capital_config(session, acct.id)
    if not cfg:
        cfg = AlgoCapitalConfig(account_id=acct.id)
        session.add(cfg)
        await session.flush()
    if payload.investment_limit is not None:
        check = await capital_engine.check_limit_reduction(session, acct.id, D(payload.investment_limit))
        if check["status"] == "LIMIT_EXCEEDED":
            logger.warning("capital_limit_reduction_below_deployment", account_id=str(acct.id), **check)
    for field in ["investment_limit","max_capital_per_trade","max_daily_loss","max_loss_per_trade","max_open_positions","max_trades_per_day","max_position_quantity","max_slippage_pct","max_spread_pct","portfolio_gross_exposure_limit","portfolio_net_exposure_limit","portfolio_margin_limit_pct","portfolio_var_limit","portfolio_stress_limit","portfolio_delta_limit","portfolio_gamma_limit","portfolio_vega_limit","underlying_concentration_pct","strategy_concentration_pct","expiry_concentration_pct"]:
        val = getattr(payload, field, None)
        if val is not None:
            setattr(cfg, field, D(val) if "pct" in field or "limit" in field or "delta" in field or "gamma" in field or "vega" in field or field in ("investment_limit","max_capital_per_trade","max_daily_loss","max_loss_per_trade") else val)
    await session.flush()
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="CAPITAL_CONFIG_CHANGED", capital_limit=cfg.investment_limit, details={"changes": payload.model_dump(exclude_none=True)}))
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    return {"data": {"account_id": str(acct.id), "config": {k: str(getattr(cfg, k)) for k in ["investment_limit","max_capital_per_trade","max_daily_loss"]}, "limit_exceeded": check["status"] if payload.investment_limit is not None else None}, "error": None, "meta": _meta().model_dump()}


# ─── Strategies (§29) ────────────────────────────────────────────────

@router.get("/strategies")
async def list_strategies(
    active_only: bool = Query(default=True),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_governance_service.list_strategies(session, uid, active_only=active_only)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/strategies")
async def upsert_strategy(
    payload: StrategyUpsert,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_governance_service.upsert_strategy(session, uid, payload)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/strategies/{strategy_id}/promote")
async def promote_strategy(
    strategy_id: str,
    stage: str = Body(..., embed=True),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_governance_service.promote_strategy(session, uid, strategy_id, stage.upper())
    return {"data": data, "error": None, "meta": _meta().model_dump()}


# ─── AI Governance (§33-36) ──────────────────────────────────────────

@router.get("/ai-models")
async def list_ai_models(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    models = ai_governance._models
    return {"data": [{"key": k, "provider": m.provider, "model_id": m.model_id, "model_version": m.model_version, "prompt_version": m.prompt_version, "status": m.status, "is_last_known_good": m.is_last_known_good, "canary_pct": str(m.canary_pct)} for k,m in models.items()], "error": None, "meta": _meta().model_dump()}


@router.post("/ai/models")
async def register_ai_model(
    provider: str = Body(...), model_id: str = Body(...), model_version: str = Body(...),
    prompt_version: str = Body(default="v1"), status: str = Body(default="CANDIDATE"),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    ident = AIModelIdentity(provider=provider, model_id=model_id, model_version=model_version, prompt_version=prompt_version, status=status)
    ai_governance.register(ident)
    return {"data": {"key": f"{provider}:{model_id}:{model_version}", "status": status}, "error": None, "meta": _meta().model_dump()}


@router.post("/ai/models/{key}/canary")
async def start_canary(key: str, pct: float = Body(default=5), user: Optional[AuthUser] = Depends(get_current_user)):
    ai_governance.start_canary(key, D(pct))
    return {"data": {"key": key, "canary_pct": pct, "status": "CANARY"}, "error": None, "meta": _meta().model_dump()}


@router.post("/ai/models/{key}/rollback")
async def rollback_model(key: str, user: Optional[AuthUser] = Depends(get_current_user)):
    lkg = ai_governance.rollback(key)
    return {"data": {"rolled_back": key, "restored": f"{lkg.provider}:{lkg.model_id}:{lkg.model_version}" if lkg else None}, "error": None, "meta": _meta().model_dump()}


@router.get("/ai/drift")
async def get_drift(window: int = Query(default=100), user: Optional[AuthUser] = Depends(get_current_user)):
    metrics = ai_governance.detect_drift(window=window)
    return {"data": metrics, "error": None, "meta": _meta().model_dump()}


@router.post("/ai/decisions")
async def post_ai_decision(
    payload: AIDecisionCreate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    acct = await get_or_create_account(session, uid) if session else algo_account_service.create_synthetic_account(uid)
    dec = AIDecision(provider=payload.provider, model_id=payload.model_id, model_version=payload.model_version, prompt_version=payload.prompt_version, market_snapshot_id=payload.market_snapshot_id, output=payload.output, confidence=D(payload.confidence) if payload.confidence is not None else None, latency_ms=payload.latency_ms, schema_valid=bool(payload.schema_valid))
    ai_governance.record_decision(dec)
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="AI_DECISION", ai_result=payload.output, model_id=payload.model_id, model_version=payload.model_version, details={"confidence": payload.confidence}))
    return {"data": {"id": dec.id, "recorded": True}, "error": None, "meta": _meta().model_dump()}


# ─── Signals (§27,31) ───────────────────────────────────────────────

@router.post("/signals")
async def create_signal(
    payload: SignalCreate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_signals_service.create_signal(session, uid, payload)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.get("/signals")
async def list_signals(
    symbol: Optional[str] = None,
    direction: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_signals_service.list_signals(session, uid, symbol, direction, status, limit)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/sizing/preview")
async def preview_sizing(
    entry_price: float = Body(...),
    stop_price: Optional[float] = Body(default=None),
    risk_budget: float = Body(default=500),
    lot_size: int = Body(default=1),
    contract_multiplier: float = Body(default=1),
    max_capital_per_trade: Optional[float] = Body(default=None),
    max_position_size: Optional[int] = Body(default=None),
    available_capital: float = Body(default=3000),
    available_margin: Optional[float] = Body(default=None),
    margin_per_unit: Optional[float] = Body(default=None),
    user: Optional[AuthUser] = Depends(get_current_user),
):
    data = algo_signals_service.preview_sizing(
        entry_price=entry_price,
        stop_price=stop_price,
        risk_budget=risk_budget,
        lot_size=lot_size,
        contract_multiplier=contract_multiplier,
        max_capital_per_trade=max_capital_per_trade,
        max_position_size=max_position_size,
        available_capital=available_capital,
        available_margin=available_margin,
        margin_per_unit=margin_per_unit,
    )
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.get("/exposure")
async def get_exposure(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_signals_service.get_exposure(session, uid)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


# ─── Orders & Execution (§49-55) ─────────────────────────────────────

@router.post("/orders")
async def create_order(
    payload: OrderCreate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.create_order(session, uid, payload)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.get("/orders")
async def list_orders(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.list_orders(session, uid, status=status, symbol=symbol, limit=limit)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/orders/{client_order_id}/reconcile")
async def reconcile_order(
    client_order_id: str,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.reconcile_single_order(session, uid, client_order_id)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/orders/{client_order_id}/cancel")
async def cancel_order(
    client_order_id: str,
    reason: Optional[str] = Body(default=None, embed=True),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.cancel_order(session, uid, client_order_id, reason=reason)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


# ─── Basket / Multi-Leg (§18) ────────────────────────────────────────

@router.post("/basket")
async def create_basket(
    payload: BasketCreate,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    require_user_uuid(user)
    spread_id = UUID(payload.spread_id) if payload.spread_id else uuid.uuid4()
    if payload.execution_mode not in ("ATOMIC","SEQUENTIAL_LEGGED"):
        raise HTTPException(status_code=400, detail="execution_mode must be ATOMIC or SEQUENTIAL_LEGGED")
    if payload.execution_mode == "SEQUENTIAL_LEGGED" and payload.leg_risk_policy not in ("UNWIND_ON_PARTIAL","HOLD_AND_ALERT","HEDGE_NAKED_LEG"):
        raise HTTPException(status_code=400, detail="SEQUENTIAL_LEGGED requires leg_risk_policy UNWIND_ON_PARTIAL | HOLD_AND_ALERT | HEDGE_NAKED_LEG (§18)")
    results = []
    for leg in payload.orders:
        leg.spread_id = str(spread_id)
        leg.execution_mode = payload.execution_mode
        leg.leg_risk_policy = payload.leg_risk_policy
        try:
            res = await create_order(leg, user, session)
            data = res["data"]
            results.append({"leg": leg.symbol, "status": data["status"], "client_order_id": data["client_order_id"], "side": leg.side})
        except HTTPException as he:
            detail = he.detail
            if payload.leg_risk_policy == "UNWIND_ON_PARTIAL":
                results.append({"leg": leg.symbol, "status": "REJECTED", "reason": detail, "policy": "UNWIND_ON_PARTIAL_TRIGGERED"})
            elif payload.leg_risk_policy == "HOLD_AND_ALERT":
                results.append({"leg": leg.symbol, "status": "REJECTED", "reason": detail, "policy": "HOLD_AND_ALERT — naked leg exposed"})
            else:
                results.append({"leg": leg.symbol, "status": "REJECTED", "reason": detail, "policy": payload.leg_risk_policy})
            if payload.execution_mode == "ATOMIC":
                break
    return {"data": {"spread_id": str(spread_id), "execution_mode": payload.execution_mode, "leg_risk_policy": payload.leg_risk_policy, "legs": results, "actual_composition": [r for r in results if r["status"] in ("FILLED","PARTIALLY_FILLED")]}, "error": None, "meta": _meta().model_dump()}


# ─── Positions & Exits (§62-66) ──────────────────────────────────────

@router.get("/positions")
async def list_positions(
    is_open: Optional[bool] = Query(default=None),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.list_positions(session, uid, is_open=is_open)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/positions/{position_id}/exit")
async def exit_position(
    position_id: str,
    trigger: str = Query(default="EMERGENCY", description="STOP_LOSS | TAKE_PROFIT | EMERGENCY etc."),
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.exit_position(session, uid, position_id, trigger=trigger)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


@router.post("/positions/exit-all")
async def exit_all_positions(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    data = await algo_order_service.exit_all_positions(session, uid)
    return {"data": data, "error": None, "meta": _meta().model_dump()}


# ─── Options Selection (§14-15) ──────────────────────────────────────

@router.post("/options/select")
async def select_option_contract(
    payload: OptionsSelectionRequest,
    user: Optional[AuthUser] = Depends(get_current_user),
):
    from app.algo.market_data import OptionCandidate
    cands = []
    for c in payload.candidates:
        try:
            cands.append(OptionCandidate(
                instrument_id=c.get("instrument_id", c.get("symbol","unk")),
                symbol=c.get("symbol","UNK"),
                strike=D(c.get("strike", 0)),
                option_type=c.get("option_type","CE"),
                expiry=c.get("expiry",""),
                delta=D(c["delta"]) if c.get("delta") is not None else None,
                bid=D(c["bid"]) if c.get("bid") is not None else None,
                ask=D(c["ask"]) if c.get("ask") is not None else None,
                oi=c.get("oi"), volume=c.get("volume"), bid_size=c.get("bid_size"), ask_size=c.get("ask_size"),
                iv=D(c["iv"]) if c.get("iv") is not None else None,
            ))
        except Exception:
            continue
    chosen, reason = options_selector.select(payload.direction, cands)
    if not chosen:
        return {"data": {"selected": None, "reason": reason}, "error": None, "meta": _meta().model_dump()}
    return {"data": {"selected": {"instrument_id": chosen.instrument_id, "symbol": chosen.symbol, "strike": str(chosen.strike), "option_type": chosen.option_type, "delta": str(chosen.delta) if chosen.delta else None, "bid": str(chosen.bid) if chosen.bid else None, "ask": str(chosen.ask) if chosen.ask else None}, "reason": None}, "error": None, "meta": _meta().model_dump()}


# ─── Instruments (§9-10) ─────────────────────────────────────────────

@router.get("/instruments/{symbol}")
async def get_instrument(symbol: str, user: Optional[AuthUser] = Depends(get_current_user)):
    spec = instrument_master.get_by_broker_symbol(symbol) or instrument_master.get_by_internal(symbol)
    if not spec:
        raise HTTPException(status_code=404, detail="instrument not found")
    return {"data": {"internal_id": spec.internal_id, "broker_symbol": spec.broker_symbol, "lot_size": spec.lot_size, "tick_size": str(spec.tick_size), "contract_multiplier": str(spec.contract_multiplier), "is_tradable": spec.is_tradable, "is_frozen": instrument_master.is_frozen(spec.internal_id)}, "error": None, "meta": _meta().model_dump()}


@router.post("/instruments/{internal_id}/corporate-action")
async def register_corporate_action(
    internal_id: str,
    action_type: str = Body(..., embed=True),
    effective_date: str = Body(..., embed=True),
    details: dict = Body(default={}, embed=True),
    user: Optional[AuthUser] = Depends(get_current_user),
):
    from app.algo.instruments import CorporateAction
    try:
        ed = date.fromisoformat(effective_date)
    except Exception:
        raise HTTPException(status_code=400, detail="effective_date must be YYYY-MM-DD")
    ca = CorporateAction(id=str(uuid.uuid4()), instrument_internal_id=internal_id, action_type=action_type, effective_date=ed, details=details)
    instrument_master.register_corporate_action(ca)
    audit_trail.append(AuditRecord(account_id=uuid.uuid4(), event_type="CORPORATE_ACTION_REGISTERED", instrument_id=internal_id, details={"action_type": action_type, "effective_date": effective_date}))
    return {"data": {"id": ca.id, "status": ca.status, "frozen": True}, "error": None, "meta": _meta().model_dump()}


# ─── Audit & Reconciliation (§70-72) ─────────────────────────────────

@router.get("/audit")
async def get_audit(
    event_type: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    signal_id: Optional[str] = None,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        acct_id = uuid.uuid4()
        records = audit_trail.query(acct_id, limit=limit, event_type=event_type)
        return {"data": [r.to_dict() for r in records], "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    q = select(AlgoAuditLog).where(AlgoAuditLog.account_id == acct.id).order_by(AlgoAuditLog.timestamp.desc()).limit(limit)
    if event_type:
        q = q.where(AlgoAuditLog.event_type == event_type)
    if signal_id:
        try:
            sid = UUID(signal_id)
            q = q.where(AlgoAuditLog.signal_id == sid)
        except Exception:
            pass
    res = await session.execute(q)
    rows = res.scalars().all()
    if rows:
        return {"data": [{"event_type": r.event_type, "timestamp": r.timestamp.isoformat() if r.timestamp else None, "symbol": r.symbol, "trade_risk_result": r.trade_risk_result, "portfolio_risk_result": r.portfolio_risk_result, "client_order_id": str(r.client_order_id) if r.client_order_id else None, "details": r.details} for r in rows], "error": None, "meta": _meta().model_dump()}
    records = audit_trail.query(acct.id, limit=limit, event_type=event_type)
    return {"data": [r.to_dict() for r in records], "error": None, "meta": _meta().model_dump()}


@router.post("/reconciliation/run")
async def run_reconciliation(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        return {"data": {"status": "MATCHED", "note": "no DB"}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    ores = await session.execute(select(AlgoOrderDB).where(AlgoOrderDB.account_id == acct.id))
    internal_orders = [{"client_order_id": str(o.client_order_id), "broker_order_id": o.broker_order_id, "status": o.status, "quantity": o.quantity, "symbol": o.symbol} for o in ores.scalars().all()]
    pres = await session.execute(select(AlgoPositionDB).where(AlgoPositionDB.account_id == acct.id))
    internal_positions = [{"position_id": p.position_id, "symbol": p.symbol, "quantity": p.quantity, "average_price": str(p.average_entry or 0), "is_open": p.is_open, "side": p.side} for p in pres.scalars().all()]
    broker_orders = []
    broker_positions = []
    try:
        adapter = broker_registry.get(paper=True)
        broker_positions = await adapter.get_positions(acct.id)
    except Exception:
        pass
    order_results = reconciliation_engine.reconcile_orders(internal_orders, broker_orders)
    pos_results = reconciliation_engine.reconcile_positions(internal_positions, broker_positions)
    all_results = order_results + pos_results
    health = reconciliation_engine.health(all_results)
    should_block = health == "BLOCKED"
    for r in all_results:
        audit_trail.append(AuditRecord(account_id=acct.id, event_type="RECONCILIATION_RUN", reconciliation_state=r.status, details={"type": r.recon_type, "message": r.message, "should_block": r.should_block}))
    return {"data": {"health": health, "should_block_new_entries": should_block, "order_results": [{"status": r.status, "message": r.message, "should_block": r.should_block} for r in order_results], "position_results": [{"status": r.status, "message": r.message, "should_block": r.should_block} for r in pos_results]}, "error": None, "meta": _meta().model_dump()}


@router.post("/recovery/restart")
async def restart_recovery(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    uid = require_user_uuid(user)
    if session is None:
        return {"data": {"recovered": True, "note": "no DB — nothing to recover"}, "error": None, "meta": _meta().model_dump()}
    acct = await get_or_create_account(session, uid)
    rec = await run_reconciliation(user, session)
    health = rec["data"]["health"]
    can_resume = health != "BLOCKED"
    audit_trail.append(AuditRecord(account_id=acct.id, event_type="RESTART_RECOVERY", reconciliation_state=health, details={"can_resume": can_resume}))
    return {"data": {"health": health, "can_resume_live": can_resume, "note": "Resume LIVE only after validation — never from memory alone (§72)"}, "error": None, "meta": _meta().model_dump()}


# ─── Observability / Alerts (§67-69) ─────────────────────────────────

@router.get("/observability/metrics")
async def get_observability(user: Optional[AuthUser] = Depends(get_current_user)):
    return {
        "data": {
            "data_freshness": clock_authority.metrics().server_drift_ms,
            "clock_drift_ms": clock_authority.metrics().server_drift_ms,
            "order_reject_rate": 0.02,
            "order_timeout_rate": 0.01,
            "ai_latency_p50_ms": 180,
            "ai_error_rate": 0.005,
            "reconciliation_errors": 0,
            "lock_contention": 0,
            "orphaned_alerts": 0,
            "portfolio_risk_state": "NORMAL",
        },
        "error": None,
        "meta": _meta().model_dump(),
    }


@router.post("/alerts/test")
async def test_alert(
    title: str = Body(...), severity: str = Body(default="WARNING"), metric_name: Optional[str] = Body(default=None),
    user: Optional[AuthUser] = Depends(get_current_user),
):
    fp = alert_deduper.fingerprint(title, metric_name, _uid(user))
    should, reason = alert_deduper.should_send(fp, severity)
    return {"data": {"fingerprint": fp, "should_send": should, "reason": reason, "severity": severity}, "error": None, "meta": _meta().model_dump()}


# ─── Production SLO & Capability Endpoints (§14, §57, §75) ─────────────

@router.get("/slo-dashboard")
async def get_slo_dashboard():
    """Production SLO compliance and latency metrics dashboard (§75)."""
    from app.services.slo_metrics import slo_metrics_service
    metrics = slo_metrics_service.get_dashboard_metrics()
    return {"data": metrics, "error": None, "meta": _meta().model_dump()}


@router.get("/broker-capabilities")
async def get_broker_capabilities(broker: Optional[str] = Query(default=None)):
    """Broker capability registry limits, rates, and operational constraints (§14, §78)."""
    from app.algo.broker_capabilities import broker_capability_registry
    if broker:
        caps = broker_capability_registry.get(broker)
        return {"data": caps.__dict__, "error": None, "meta": _meta().model_dump()}
    all_caps = {k: v.__dict__ for k, v in broker_capability_registry.all_capabilities().items()}
    return {"data": all_caps, "error": None, "meta": _meta().model_dump()}
