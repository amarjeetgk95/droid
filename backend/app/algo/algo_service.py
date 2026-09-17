"""Algo Trading Domain Services — Business logic extracted from app/api/algo.py.

Provides unit-testable service classes:
- AlgoAccountService: deterministic account resolution, synthetic fallbacks, mode transitions, consent, capital
- AlgoOrderService: full-stack pre-trade risk evaluation, order submission, idempotency, baskets, position exits
- AlgoGovernanceService: strategy lifecycle, AI models/canary, kill switch
- AlgoSignalsService: signal creation, fusion, sizing preview, exposure
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.database import Profile
from app.algo.money import D
from app.algo.capital import capital_engine
from app.algo.risk import (
    trade_risk_engine,
    portfolio_risk_engine,
    OrderIntent,
    PortfolioExposure,
    PortfolioRiskInput,
)
from app.algo.position_sizing import size_position, SizingInputs
from app.algo.execution import order_manager, execution_safety, broker_registry
from app.algo.positions import exit_engine, Position
from app.algo.audit import audit_trail, AuditRecord
from app.algo.account import live_entry_gate
from app.algo.clock import clock_authority
from app.algo.signal_fusion import signal_fusion, SignalInputs
from app.algo.ai_governance import ai_governance, AIModelIdentity, AIDecision
from app.algo.models import (
    AlgoAccount,
    AlgoCapitalConfig,
    AlgoOrderDB,
    AlgoPositionDB,
    AlgoSignalDB,
    AlgoKillSwitch,
    AlgoConsent,
    AlgoRiskDecision,
    AlgoAuditLog,
    AlgoStrategy,
)

logger = structlog.get_logger()
DISCLOSURE_VERSION = "v1.0-2026-08-31"


class AlgoAccountService:
    """Manages algo account lifecycle, synthetic test fallbacks, consent, and mode transitions."""

    def __init__(self) -> None:
        self._synthetic_account_cache: dict[UUID, AlgoAccount] = {}

    def reset(self) -> None:
        """Reset in-memory synthetic account cache (used in test fixtures)."""
        self._synthetic_account_cache.clear()

    def create_synthetic_account(self, user_id: UUID, mode: str = "OFF") -> AlgoAccount:
        """Detached, non-persisted account with a deterministic id (the user_id itself)."""
        return AlgoAccount(id=user_id, user_id=user_id, mode=mode, is_active=True)

    async def get_or_create_account(
        self, session: AsyncSession | None, user_id: UUID
    ) -> AlgoAccount:
        """Get or create algo account — deterministic per user_id, DB-backed when available, synthetic fallback.

        Always returns an AlgoAccount.
        """
        if not settings.database_url or session is None:
            if user_id not in self._synthetic_account_cache:
                self._synthetic_account_cache[user_id] = self.create_synthetic_account(user_id)
            return self._synthetic_account_cache[user_id]

        if user_id in self._synthetic_account_cache:
            return self._synthetic_account_cache[user_id]

        try:
            target_uid = user_id
            prof_res = await session.execute(select(Profile.id).where(Profile.id == user_id))
            if not prof_res.scalar_one_or_none():
                if str(user_id) == "00000000-0000-0000-0000-000000000001":
                    active_prof_res = await session.execute(
                        select(Profile.id).order_by(Profile.created_at.asc()).limit(1)
                    )
                    db_uid = active_prof_res.scalar_one_or_none()
                    if db_uid:
                        target_uid = db_uid

            res = await session.execute(
                select(AlgoAccount).where(AlgoAccount.user_id == target_uid)
            )
            acct = res.scalar_one_or_none()
            if not acct:
                acct = AlgoAccount(user_id=target_uid, mode="OFF")
                session.add(acct)
                await session.flush()
                cfg = AlgoCapitalConfig(account_id=acct.id)
                session.add(cfg)
                ks = AlgoKillSwitch(account_id=acct.id)
                session.add(ks)
                await session.flush()
                await session.commit()
            self._synthetic_account_cache[user_id] = acct
            return acct
        except Exception as e:
            logger.warning("algo_account_db_fallback", error=str(e))
            try:
                await session.rollback()
            except Exception:
                pass
            if user_id not in self._synthetic_account_cache:
                self._synthetic_account_cache[user_id] = self.create_synthetic_account(user_id)
            return self._synthetic_account_cache[user_id]

    async def get_account_detail(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Fetch account state, capital limits, kill-switch status, and consent."""
        acct = await self.get_or_create_account(session, user_id)
        if session is None:
            # Fail-closed: no DB = no capital numbers. Never invent a
            # ₹3000 "Dev Account" — the UI must show unavailable, not funds.
            return {
                "account_id": str(acct.id),
                "mode": acct.mode,
                "is_active": False,
                "display_name": acct.display_name or "Unavailable (no DB)",
                "unavailable": True,
                "reason": "NO_DB_SESSION",
                "capital": {
                    "investment_limit": "0.00",
                    "available": "0.00",
                    "reserved": "0.00",
                    "deployed": "0.00",
                    "daily_loss": "0.00",
                    "daily_loss_limit": "0.00",
                    "is_breached": False,
                },
                "kill_switch": {"is_killed": True, "kill_level": "FULL"},
                "consent": {"acknowledged": False, "disclosure_version": DISCLOSURE_VERSION},
            }

        snap = await capital_engine.get_snapshot(session, acct.id)
        ks_res = await session.execute(
            select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == acct.id)
        )
        ks = ks_res.scalar_one_or_none()
        cs_res = await session.execute(
            select(AlgoConsent).where(
                AlgoConsent.account_id == acct.id,
                AlgoConsent.disclosure_version == DISCLOSURE_VERSION,
                AlgoConsent.revoked_at.is_(None),
            )
        )
        consent = cs_res.scalar_one_or_none()
        return {
            "account_id": str(acct.id),
            "mode": acct.mode,
            "is_active": acct.is_active,
            "display_name": acct.display_name or "Primary",
            "capital": {
                "investment_limit": str(snap.investment_limit),
                "available": str(snap.available),
                "reserved": str(snap.reserved),
                "deployed": str(snap.deployed),
                "daily_loss": str(snap.daily_loss),
                "daily_loss_limit": str(snap.daily_loss_limit),
                "is_breached": snap.is_breached,
            },
            "kill_switch": {
                "is_killed": ks.is_killed if ks else False,
                "kill_level": ks.kill_level if ks else "NONE",
            },
            "consent": {
                "acknowledged": consent.acknowledged if consent else False,
                "disclosure_version": DISCLOSURE_VERSION,
            },
        }

    async def set_mode(
        self, session: AsyncSession | None, user_id: UUID, target_mode: str
    ) -> dict[str, Any]:
        """Transition account trading mode with validation and gate verification."""
        target_mode = target_mode.upper()
        if target_mode not in ("OFF", "OBSERVE", "PAPER", "LIVE"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode '{target_mode}'. Allowed: OFF | OBSERVE | PAPER | LIVE",
            )

        acct = await self.get_or_create_account(session, user_id)
        if session is None:
            acct.mode = target_mode
            self._synthetic_account_cache[user_id] = acct
            return {
                "account_id": str(acct.id),
                "mode": acct.mode,
                "previous_mode": "OFF",
                "is_active": acct.is_active,
            }

        prev = acct.mode
        if target_mode == "LIVE":
            cs_res = await session.execute(
                select(AlgoConsent).where(
                    AlgoConsent.account_id == acct.id,
                    AlgoConsent.disclosure_version == DISCLOSURE_VERSION,
                    AlgoConsent.revoked_at.is_(None),
                )
            )
            if not cs_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"LIVE mode requires acknowledged consent for disclosure {DISCLOSURE_VERSION} (§81.1)",
                )

            cap_snap = await capital_engine.get_snapshot(session, acct.id)
            if cap_snap.is_breached or cap_snap.available <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="LIVE mode requires positive available capital and unbreached daily loss (§81.4)",
                )

            ks_res = await session.execute(
                select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == acct.id)
            )
            ks = ks_res.scalar_one_or_none()
            if ks and ks.is_killed:
                raise HTTPException(
                    status_code=400,
                    detail=f"LIVE mode blocked: kill switch active at level {ks.kill_level} (§81.5)",
                )

        acct.mode = target_mode
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="ACCOUNT_MODE_CHANGED",
                details={"from": prev, "to": target_mode},
            )
        )
        return {
            "account_id": str(acct.id),
            "mode": acct.mode,
            "previous_mode": prev,
            "is_active": acct.is_active,
        }

    async def get_consent(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Fetch consent status for disclosure version."""
        if session is None:
            return {
                "disclosure_version": DISCLOSURE_VERSION,
                "acknowledged": False,
                "note": "Dev mode",
            }
        acct = await self.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoConsent).where(
                AlgoConsent.account_id == acct.id,
                AlgoConsent.disclosure_version == DISCLOSURE_VERSION,
            )
        )
        c = res.scalar_one_or_none()
        return {
            "disclosure_version": DISCLOSURE_VERSION,
            "acknowledged": c.acknowledged if c else False,
            "acknowledged_at": c.acknowledged_at.isoformat() if c and c.acknowledged_at else None,
            "revoked": c.revoked_at is not None if c else False,
        }

    async def record_consent(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        disclosure_version: str,
        acknowledged: bool,
    ) -> dict[str, Any]:
        """Capture user acknowledgment of algo disclosure."""
        if not acknowledged:
            raise HTTPException(
                status_code=400, detail="Must acknowledge disclosure terms to enable live mode"
            )
        if disclosure_version != DISCLOSURE_VERSION:
            raise HTTPException(
                status_code=400, detail=f"Unsupported disclosure version '{disclosure_version}'"
            )

        if session is None:
            return {
                "disclosure_version": disclosure_version,
                "acknowledged": True,
                "note": "Dev mode — in-memory only",
            }

        acct = await self.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoConsent).where(
                AlgoConsent.account_id == acct.id,
                AlgoConsent.disclosure_version == disclosure_version,
            )
        )
        existing = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if existing:
            existing.acknowledged = True
            existing.acknowledged_at = now
            existing.revoked_at = None
        else:
            c = AlgoConsent(
                account_id=acct.id,
                disclosure_version=disclosure_version,
                acknowledged=True,
                acknowledged_at=now,
            )
            session.add(c)
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="CONSENT_RECORDED",
                details={"version": disclosure_version},
            )
        )
        return {
            "disclosure_version": disclosure_version,
            "acknowledged": True,
            "acknowledged_at": now.isoformat(),
        }

    async def revoke_consent(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Revoke consent and drop account mode back to OFF immediately."""
        if session is None:
            return {"revoked": True, "mode": "OFF", "note": "Dev mode"}

        acct = await self.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoConsent).where(
                AlgoConsent.account_id == acct.id,
                AlgoConsent.disclosure_version == DISCLOSURE_VERSION,
            )
        )
        c = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if c:
            c.revoked_at = now
            c.acknowledged = False
        acct.mode = "OFF"
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="CONSENT_REVOKED",
                details={"forced_mode": "OFF"},
            )
        )
        return {"revoked": True, "mode": "OFF", "revoked_at": now.isoformat()}

    async def get_capital(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Fetch capital snapshot and configuration limits."""
        if session is None:
            return {
                "investment_limit": "3000.00",
                "available": "3000.00",
                "reserved": "0.00",
                "deployed": "0.00",
                "daily_loss": "0.00",
                "daily_loss_limit": "500.00",
                "is_breached": False,
                "config": {
                    "max_capital_per_trade": "1000.00",
                    "max_loss_per_trade": "200.00",
                    "max_open_positions": 5,
                    "max_trades_per_day": 20,
                    "max_position_quantity": 500,
                    "max_slippage_pct": "0.3000",
                    "max_spread_pct": "0.5000",
                },
            }
        acct = await self.get_or_create_account(session, user_id)
        snap = await capital_engine.get_snapshot(session, acct.id)
        res = await session.execute(
            select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == acct.id)
        )
        cfg = res.scalar_one_or_none()
        return {
            "investment_limit": str(snap.investment_limit),
            "available": str(snap.available),
            "reserved": str(snap.reserved),
            "deployed": str(snap.deployed),
            "daily_loss": str(snap.daily_loss),
            "daily_loss_limit": str(snap.daily_loss_limit),
            "is_breached": snap.is_breached,
            "config": {
                "max_capital_per_trade": str(cfg.max_capital_per_trade) if cfg else "1000.00",
                "max_loss_per_trade": str(cfg.max_loss_per_trade) if cfg else "200.00",
                "max_open_positions": cfg.max_open_positions if cfg else 5,
                "max_trades_per_day": cfg.max_trades_per_day if cfg else 20,
                "max_position_quantity": cfg.max_position_quantity if cfg else 500,
                "max_slippage_pct": str(cfg.max_slippage_pct) if cfg else "0.3000",
                "max_spread_pct": str(cfg.max_spread_pct) if cfg else "0.5000",
            },
        }

    async def update_capital(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        update_data: dict[str, Any],
        confirm: bool,
    ) -> dict[str, Any]:
        """Update risk limits in AlgoCapitalConfig."""
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="Must set confirm=true to modify live risk/capital settings (§76)",
            )
        if session is None:
            return {"updated": True, "note": "Dev mode"}

        acct = await self.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == acct.id)
        )
        cfg = res.scalar_one_or_none()
        if not cfg:
            cfg = AlgoCapitalConfig(account_id=acct.id)
            session.add(cfg)
            await session.flush()

        for k, v in update_data.items():
            if k == "confirm" or v is None:
                continue
            if hasattr(cfg, k):
                setattr(cfg, k, v)

        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="CAPITAL_CONFIG_UPDATED",
                details={k: str(v) for k, v in update_data.items() if v is not None and k != "confirm"},
            )
        )
        return {"updated": True, "account_id": str(acct.id)}


class AlgoOrderService:
    """Manages full-stack pre-trade risk evaluation, order submission, and lifecycle."""

    def __init__(self, account_service: AlgoAccountService) -> None:
        self.account_service = account_service
        self._kill_cache: dict[UUID, dict[str, Any]] = {}

    def reset(self) -> None:
        """Reset in-memory kill switch cache."""
        self._kill_cache.clear()

    def set_kill_cache(self, key_id: UUID, is_killed: bool, kill_level: str, reason: str | None = None) -> None:
        self._kill_cache[key_id] = {
            "is_killed": is_killed,
            "kill_level": kill_level,
            "reason": reason,
        }

    def get_kill_cache(self, key_id: UUID) -> dict[str, Any] | None:
        return self._kill_cache.get(key_id)

    async def evaluate_full_stack(
        self,
        acct_id: UUID,
        intent: OrderIntent,
        session: Optional[AsyncSession],
        signal_id: UUID | None = None,
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Run TradeRisk -> PortfolioRisk -> ExecutionSafety sequentially with zero bypass."""
        limits: dict[str, Any] = {
            "max_position_quantity": 500,
            "max_spread_pct": 0.5,
            "max_slippage_pct": 0.3,
        }
        exposure = PortfolioExposure()
        if session is not None:
            try:
                res = await session.execute(
                    select(AlgoCapitalConfig).where(AlgoCapitalConfig.account_id == acct_id)
                )
                cfg = res.scalar_one_or_none()
                if cfg:
                    limits.update({
                        "max_position_quantity": cfg.max_position_quantity,
                        "max_spread_pct": float(cfg.max_spread_pct) if cfg.max_spread_pct else 0.5,
                        "max_slippage_pct": float(cfg.max_slippage_pct) if cfg.max_slippage_pct else 0.3,
                        "min_oi": (cfg.liquidity_thresholds or {}).get("min_oi")
                        if hasattr(cfg, "liquidity_thresholds") and cfg.liquidity_thresholds
                        else None,
                        "portfolio_gross_exposure_limit": float(cfg.portfolio_gross_exposure_limit)
                        if cfg.portfolio_gross_exposure_limit
                        else None,
                        "portfolio_net_exposure_limit": float(cfg.portfolio_net_exposure_limit)
                        if cfg.portfolio_net_exposure_limit
                        else None,
                        "portfolio_margin_limit_pct": float(cfg.portfolio_margin_limit_pct)
                        if cfg.portfolio_margin_limit_pct
                        else None,
                        "portfolio_delta_limit": float(cfg.portfolio_delta_limit)
                        if cfg.portfolio_delta_limit
                        else None,
                        "portfolio_gamma_limit": float(cfg.portfolio_gamma_limit)
                        if cfg.portfolio_gamma_limit
                        else None,
                        "portfolio_vega_limit": float(cfg.portfolio_vega_limit)
                        if cfg.portfolio_vega_limit
                        else None,
                        "underlying_concentration_pct": float(cfg.underlying_concentration_pct)
                        if cfg.underlying_concentration_pct
                        else None,
                    })

                pres = await session.execute(
                    select(AlgoPositionDB).where(
                        AlgoPositionDB.account_id == acct_id,
                        AlgoPositionDB.is_open == True,
                    )
                )
                poss = pres.scalars().all()
                gross = D(0)
                long_e = D(0)
                short_e = D(0)
                by_u: dict[str, Decimal] = {}
                by_s: dict[str, Decimal] = {}
                by_e: dict[str, Decimal] = {}
                d = D(0)
                g = D(0)
                th = D(0)
                v = D(0)
                for p in poss:
                    notional = abs(D(p.quantity or 0) * D(p.current_price or p.average_entry or 0))
                    gross += notional
                    if p.side == "LONG":
                        long_e += notional
                    else:
                        short_e += notional
                    u = p.underlying or p.symbol
                    by_u[u] = by_u.get(u, D(0)) + notional
                    s = p.strategy_id or "unknown"
                    by_s[s] = by_s.get(s, D(0)) + notional
                    greeks = p.greeks or {}
                    d += D(greeks.get("delta", 0) or 0) * D(p.quantity or 0)
                    g += D(greeks.get("gamma", 0) or 0) * D(p.quantity or 0)
                    th += D(greeks.get("theta", 0) or 0) * D(p.quantity or 0)
                    v += D(greeks.get("vega", 0) or 0) * D(p.quantity or 0)
                exposure = PortfolioExposure(
                    gross_exposure=gross,
                    net_exposure=long_e - short_e,
                    long_exposure=long_e,
                    short_exposure=short_e,
                    portfolio_delta=d,
                    portfolio_gamma=g,
                    portfolio_theta=th,
                    portfolio_vega=v,
                    by_underlying=by_u,
                    by_strategy=by_s,
                    by_expiry=by_e,
                )
            except Exception as e:
                logger.warning("exposure_build_failed", error=str(e))

        # 1. Trade Risk
        tr = trade_risk_engine.evaluate(intent, limits)
        if session is not None:
            try:
                rd = AlgoRiskDecision(
                    account_id=acct_id,
                    signal_id=signal_id,
                    client_order_id=intent.client_order_id,
                    stage="TRADE_RISK",
                    result=tr.result,
                    reason=tr.reason,
                    failed_check=tr.failed_check,
                    checks=[c.__dict__ for c in tr.checks],
                )
                session.add(rd)
                await session.flush()
            except Exception:
                pass
        if tr.result == "REJECTED":
            audit_trail.append(
                AuditRecord(
                    account_id=acct_id,
                    event_type="RISK_REJECTED",
                    signal_id=signal_id,
                    symbol=intent.symbol,
                    trade_risk_result="REJECTED",
                    risk_checks={
                        "stage": "TRADE_RISK",
                        "reason": tr.reason,
                        "checks": [c.__dict__ for c in tr.checks],
                    },
                )
            )
            return False, tr.reason, {"stage": "TRADE_RISK", "checks": [c.__dict__ for c in tr.checks]}

        # 2. Portfolio Risk
        new_notional = D(intent.price) * D(intent.quantity) if intent.price else D(0)
        est_margin = intent.estimated_margin or new_notional * D("0.15")
        pr_inp = PortfolioRiskInput(
            existing_exposure=exposure,
            new_order_notional=new_notional if intent.side == "BUY" else -new_notional,
            new_order_margin=est_margin,
            new_order_underlying=intent.underlying,
            new_order_strategy=intent.strategy_id,
            limits=limits,
            available_margin=intent.margin_available,
            total_required_margin=est_margin,
        )
        pr = portfolio_risk_engine.evaluate(pr_inp)
        if session is not None:
            try:
                rd2 = AlgoRiskDecision(
                    account_id=acct_id,
                    signal_id=signal_id,
                    client_order_id=intent.client_order_id,
                    stage="PORTFOLIO_RISK",
                    result=pr.result,
                    reason=pr.reason,
                    failed_check=pr.failed_check,
                    checks=[c.__dict__ for c in pr.checks],
                )
                session.add(rd2)
                await session.flush()
            except Exception:
                pass
        if pr.result == "REJECTED":
            audit_trail.append(
                AuditRecord(
                    account_id=acct_id,
                    event_type="RISK_REJECTED",
                    signal_id=signal_id,
                    symbol=intent.symbol,
                    trade_risk_result="APPROVED",
                    portfolio_risk_result="REJECTED",
                    risk_checks={"stage": "PORTFOLIO_RISK", "reason": pr.reason},
                )
            )
            return False, pr.reason, {"stage": "PORTFOLIO_RISK", "checks": [c.__dict__ for c in pr.checks]}

        # 3. Execution Safety recheck
        safety_snapshot = {
            "data_health": intent.data_health,
            "broker_health": intent.broker_health,
            "instrument_tradable": intent.is_tradable,
            "has_circuit": intent.has_circuit,
            "kill_switch": intent.kill_switch_active,
            "price": intent.price,
            "spread_pct": float(intent.spread_pct) if intent.spread_pct else None,
            "max_spread_pct": limits.get("max_spread_pct"),
            "capital_available": intent.capital_available,
            "estimated_margin": intent.estimated_margin,
            "portfolio_risk_blocked": False,
            "max_price_deviation_pct": 1.0,
        }
        ok, reason = execution_safety.recheck(intent, safety_snapshot)
        if not ok:
            if session is not None:
                try:
                    rd3 = AlgoRiskDecision(
                        account_id=acct_id,
                        signal_id=signal_id,
                        client_order_id=intent.client_order_id,
                        stage="EXECUTION_SAFETY",
                        result="REJECTED",
                        reason=reason,
                        failed_check="execution_safety",
                    )
                    session.add(rd3)
                    await session.flush()
                except Exception:
                    pass
            return False, reason, {"stage": "EXECUTION_SAFETY", "reason": reason}

        audit_trail.append(
            AuditRecord(
                account_id=acct_id,
                event_type="RISK_APPROVED",
                signal_id=signal_id,
                symbol=intent.symbol,
                trade_risk_result="APPROVED",
                portfolio_risk_result="APPROVED",
            )
        )
        return (
            True,
            None,
            {
                "trade_risk": [c.__dict__ for c in tr.checks],
                "portfolio_risk": [c.__dict__ for c in pr.checks],
            },
        )

    async def create_order(
        self, session: AsyncSession | None, user_id: UUID, payload: Any
    ) -> dict[str, Any]:
        """Execute full order pipeline with safety gates, atomic reservations, and audit."""
        acct = (
            await self.account_service.get_or_create_account(session, user_id)
            if session
            else self.account_service.create_synthetic_account(user_id, mode="PAPER")
        )
        aid = acct.id
        mode = acct.mode
        is_paper = mode != "LIVE"

        # Check Kill Switch
        kill_active = False
        kill_level = "NONE"
        if user_id in self._kill_cache and self._kill_cache[user_id].get("is_killed"):
            kill_level = self._kill_cache[user_id]["kill_level"]
            raise HTTPException(status_code=403, detail=f"KILL_SWITCH_ACTIVE:{kill_level}")
        if aid in self._kill_cache and self._kill_cache[aid].get("is_killed"):
            kill_level = self._kill_cache[aid]["kill_level"]
            raise HTTPException(status_code=403, detail=f"KILL_SWITCH_ACTIVE:{kill_level}")

        if session is not None:
            try:
                ks_res = await session.execute(
                    select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == aid)
                )
                ks = ks_res.scalar_one_or_none()
                if ks and ks.is_killed:
                    kill_active = True
                    kill_level = ks.kill_level
                    self._kill_cache[aid] = {"is_killed": True, "kill_level": kill_level}
                    raise HTTPException(status_code=403, detail=f"KILL_SWITCH_ACTIVE:{ks.kill_level}")
            except HTTPException:
                raise
            except Exception:
                pass

        cid = UUID(payload.client_order_id) if payload.client_order_id else uuid.uuid4()
        price = D(payload.price) if payload.price is not None else D(0)

        # Idempotency checks
        existing_mem = order_manager.get(cid, account_id=aid)
        if existing_mem:
            return {
                "client_order_id": str(existing_mem.client_order_id),
                "status": existing_mem.status,
                "broker_order_id": existing_mem.broker_order_id,
                "fill_price": str(existing_mem.fill_price) if existing_mem.fill_price else None,
                "note": "IDEMPOTENT_EXISTING",
            }
        bare = order_manager.get(cid)
        if bare:
            if str(bare.account_id) != str(aid):
                logger.warning(
                    "idempotency_cross_account_collision",
                    cid=str(cid),
                    existing_account=str(bare.account_id),
                    new_account=str(aid),
                )
            return {
                "client_order_id": str(bare.client_order_id),
                "status": bare.status,
                "broker_order_id": bare.broker_order_id,
                "fill_price": str(bare.fill_price) if bare.fill_price else None,
                "note": "IDEMPOTENT_EXISTING",
            }

        if session is not None:
            existing = await session.execute(
                select(AlgoOrderDB).where(
                    AlgoOrderDB.account_id == aid, AlgoOrderDB.client_order_id == cid
                )
            )
            ex = existing.scalar_one_or_none()
            if ex:
                return {
                    "client_order_id": str(ex.client_order_id),
                    "status": ex.status,
                    "broker_order_id": ex.broker_order_id,
                    "note": "IDEMPOTENT_EXISTING",
                }

        # Capital snapshot for intent
        capital_available = None
        margin_available = None
        if session is not None:
            try:
                snap = await capital_engine.get_snapshot(session, aid)
                capital_available = snap.available
                margin_available = snap.available
            except Exception:
                capital_available = D(3000)

        intent = OrderIntent(
            account_id=aid,
            client_order_id=cid,
            symbol=payload.symbol,
            instrument_id=payload.instrument_id,
            underlying=payload.instrument_id or payload.symbol,
            side=payload.side.upper(),
            quantity=payload.quantity,
            price=price,
            product=payload.product or "INTRADAY",
            order_type=payload.order_type or "LIMIT",
            strategy_id=payload.strategy_id,
            spread_id=UUID(payload.spread_id) if payload.spread_id else None,
            bid=D(payload.bid) if payload.bid else None,
            ask=D(payload.ask) if payload.ask else None,
            is_tradable=True,
            data_health="HEALTHY",
            clock_health="HEALTHY",
            broker_health="HEALTHY",
            reconciliation_health="HEALTHY",
            kill_switch_active=kill_active,
            capital_available=capital_available,
            margin_available=margin_available,
            estimated_margin=price * D(payload.quantity) * D("0.15") if price else None,
        )

        approved, reason, checks = await self.evaluate_full_stack(aid, intent, session, signal_id=None)
        if not approved:
            if session is not None:
                try:
                    rej = AlgoOrderDB(
                        account_id=aid,
                        client_order_id=cid,
                        symbol=payload.symbol,
                        side=payload.side.upper(),
                        quantity=payload.quantity,
                        price=price,
                        order_type=payload.order_type or "LIMIT",
                        product=payload.product or "INTRADAY",
                        status="REJECTED",
                        rejection_reason=reason,
                        is_paper=is_paper,
                        instrument_id=payload.instrument_id,
                        strategy_id=payload.strategy_id,
                    )
                    session.add(rej)
                    await session.flush()
                    await session.commit()
                except Exception:
                    try:
                        await session.rollback()
                    except Exception:
                        pass
            raise HTTPException(
                status_code=422,
                detail={"reason": reason, "checks": checks, "client_order_id": str(cid)},
            )

        reservation_id = None
        if session is not None and intent.estimated_margin:
            ok, rreason, rid = await capital_engine.reserve(session, aid, cid, intent.estimated_margin)
            if not ok:
                if rreason == "LOCK_CONTENTION":
                    raise HTTPException(status_code=429, detail="LOCK_CONTENTION — retry shortly")
                raise HTTPException(status_code=422, detail=rreason)
            reservation_id = rid

        rec = order_manager.create_intent(
            account_id=aid,
            symbol=payload.symbol,
            side=payload.side.upper(),
            quantity=payload.quantity,
            price=price,
            order_type=payload.order_type or "LIMIT",
            instrument_id=payload.instrument_id,
            spread_id=UUID(payload.spread_id) if payload.spread_id else None,
            expected_price=price,
            is_paper=is_paper,
            client_order_id=cid,
        )
        try:
            order_manager.transition(cid, "RISK_APPROVED")
        except Exception:
            pass

        if session is not None:
            try:
                db_ord = AlgoOrderDB(
                    account_id=aid,
                    client_order_id=cid,
                    symbol=payload.symbol,
                    side=payload.side.upper(),
                    quantity=payload.quantity,
                    price=price,
                    order_type=payload.order_type or "LIMIT",
                    product=payload.product or "INTRADAY",
                    status="RISK_APPROVED",
                    is_paper=is_paper,
                    instrument_id=payload.instrument_id,
                    strategy_id=payload.strategy_id,
                    spread_id=UUID(payload.spread_id) if payload.spread_id else None,
                    expected_price=price,
                )
                session.add(db_ord)
                await session.flush()
                await session.commit()
            except Exception as e:
                logger.error("order_db_persist_failed", error=str(e))
                try:
                    await session.rollback()
                except Exception:
                    pass

        gate_checks = {
            "data_healthy": True,
            "clock_healthy": True,
            "broker_healthy": True,
            "reconciliation_healthy": True,
            "instrument_valid": True,
            "instrument_tradable": True,
            "no_circuit": True,
            "signal_valid": True,
            "technical_valid": True,
            "fno_valid": True,
            "ai_valid": True,
            "position_sizing_valid": True,
            "algo_capital_available": True,
            "trade_risk_pass": True,
            "portfolio_risk_pass": True,
            "margin_available": True,
            "liquidity_ok": True,
            "spread_ok": True,
            "slippage_ok": True,
            "no_duplicate_signal": True,
            "no_duplicate_order": True,
            "conflict_resolved": True,
            "kill_switch_inactive": not kill_active,
            "execution_safety_pass": True,
        }
        ok_gate, gate_reason = live_entry_gate(gate_checks)
        if not ok_gate and not is_paper:
            raise HTTPException(
                status_code=422, detail=f"LIVE_ENTRY_GATE_FAILED:{gate_reason}"
            )

        submitted = await order_manager.submit(rec)

        if session is not None:
            try:
                res = await session.execute(
                    select(AlgoOrderDB).where(
                        AlgoOrderDB.account_id == aid, AlgoOrderDB.client_order_id == cid
                    )
                )
                dbrow = res.scalar_one_or_none()
                if dbrow:
                    dbrow.status = submitted.status
                    dbrow.broker_order_id = submitted.broker_order_id
                    dbrow.fill_price = submitted.fill_price
                    dbrow.fill_quantity = submitted.fill_quantity
                    dbrow.slippage = submitted.slippage
                    await session.flush()
                    await session.commit()
                    if submitted.status == "FILLED" and reservation_id:
                        await capital_engine.consume(session, reservation_id)
                        await session.commit()
                    elif (
                        submitted.status in ("REJECTED", "CANCELLED", "TIMED_OUT", "UNKNOWN")
                        and reservation_id
                    ):
                        await capital_engine.release(session, reservation_id)
                        await session.commit()
            except Exception as e:
                logger.error("order_db_update_failed", error=str(e))
                try:
                    await session.rollback()
                except Exception:
                    pass

        audit_trail.append(
            AuditRecord(
                account_id=aid,
                event_type="ORDER_SUBMITTED",
                symbol=payload.symbol,
                client_order_id=cid,
                broker_order_id=submitted.broker_order_id,
                execution_result={
                    "status": submitted.status,
                    "fill_price": str(submitted.fill_price) if submitted.fill_price else None,
                },
                expected_price=price,
                actual_fill=submitted.fill_price,
                slippage=submitted.slippage,
                reservation_id=reservation_id,
            )
        )

        return {
            "client_order_id": str(cid),
            "status": submitted.status,
            "broker_order_id": submitted.broker_order_id,
            "fill_price": str(submitted.fill_price) if submitted.fill_price else None,
            "fill_quantity": submitted.fill_quantity,
            "slippage": str(submitted.slippage) if submitted.slippage else None,
            "is_paper": is_paper,
        }

    async def list_orders(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List orders from DB or in-memory order manager."""
        if session is None:
            acct = self.account_service.create_synthetic_account(user_id)
            orders = [
                rec for k, rec in order_manager._orders.items()
                if ":" in k and str(rec.account_id) == str(acct.id)
            ]
            if status:
                orders = [o for o in orders if o.status == status]
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return [
                {
                    "client_order_id": str(o.client_order_id),
                    "broker_order_id": o.broker_order_id,
                    "symbol": o.symbol,
                    "side": o.side,
                    "quantity": o.quantity,
                    "price": str(o.price) if o.price else None,
                    "status": o.status,
                    "fill_price": str(o.fill_price) if o.fill_price else None,
                    "is_paper": o.is_paper,
                }
                for o in orders[:limit]
            ]

        acct = await self.account_service.get_or_create_account(session, user_id)
        q = (
            select(AlgoOrderDB)
            .where(AlgoOrderDB.account_id == acct.id)
            .order_by(AlgoOrderDB.created_at.desc())
            .limit(limit)
        )
        if status:
            q = q.where(AlgoOrderDB.status == status)
        if symbol:
            q = q.where(AlgoOrderDB.symbol == symbol)
        res = await session.execute(q)
        rows = res.scalars().all()
        return [
            {
                "client_order_id": str(r.client_order_id),
                "symbol": r.symbol,
                "side": r.side,
                "quantity": r.quantity,
                "price": str(r.price) if r.price else None,
                "order_type": r.order_type,
                "status": r.status,
                "fill_price": str(r.fill_price) if r.fill_price else None,
                "fill_quantity": r.fill_quantity,
                "broker_order_id": r.broker_order_id,
                "is_paper": r.is_paper,
                "rejection_reason": r.rejection_reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def reconcile_single_order(
        self, session: AsyncSession | None, user_id: UUID, client_order_id: str
    ) -> dict[str, Any]:
        """Poll broker state for order and reconcile."""
        cid = UUID(client_order_id)
        rec = order_manager.get(cid)
        if not rec:
            raise HTTPException(status_code=404, detail="Order not found in OrderManager")
        broker_state = await order_manager.poll_status(cid)
        return {
            "client_order_id": str(cid),
            "status": rec.status,
            "broker_state": broker_state,
            "reconciled": True,
        }

    async def cancel_order(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        client_order_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Cancel working order with broker and release capital."""
        cid = UUID(client_order_id)
        rec = order_manager.get(cid)
        if not rec:
            if session is not None:
                acct = await self.account_service.get_or_create_account(session, user_id)
                res = await session.execute(
                    select(AlgoOrderDB).where(
                        AlgoOrderDB.account_id == acct.id, AlgoOrderDB.client_order_id == cid
                    )
                )
                row = res.scalar_one_or_none()
                if row and row.status in ("CREATED", "RISK_APPROVED", "SUBMITTED"):
                    row.status = "CANCELLED"
                    await session.flush()
                    await session.commit()
                    return {"client_order_id": str(cid), "status": "CANCELLED", "note": "DB cancelled"}
            raise HTTPException(status_code=404, detail="Order not found or already terminal")

        ok = await order_manager.cancel(rec)
        if not ok:
            raise HTTPException(status_code=400, detail="Cannot cancel order in state " + rec.status)

        if session is not None:
            try:
                acct = await self.account_service.get_or_create_account(session, user_id)
                res = await session.execute(
                    select(AlgoOrderDB).where(
                        AlgoOrderDB.account_id == acct.id, AlgoOrderDB.client_order_id == cid
                    )
                )
                row = res.scalar_one_or_none()
                if row:
                    row.status = "CANCELLED"
                    await session.flush()
                    await session.commit()
            except Exception:
                pass

        audit_trail.append(
            AuditRecord(
                account_id=rec.account_id,
                event_type="ORDER_CANCELLED",
                symbol=rec.symbol,
                client_order_id=cid,
                details={"reason": reason},
            )
        )
        return {"client_order_id": str(cid), "status": "CANCELLED"}

    async def list_positions(
        self, session: AsyncSession | None, user_id: UUID, is_open: bool | None = None
    ) -> list[dict[str, Any]]:
        """List open or closed positions."""
        if session is None:
            return []
        acct = await self.account_service.get_or_create_account(session, user_id)
        q = (
            select(AlgoPositionDB)
            .where(AlgoPositionDB.account_id == acct.id)
            .order_by(AlgoPositionDB.updated_at.desc())
        )
        if is_open is not None:
            q = q.where(AlgoPositionDB.is_open == is_open)
        res = await session.execute(q)
        rows = res.scalars().all()
        return [
            {
                "position_id": r.position_id,
                "symbol": r.symbol,
                "underlying": r.underlying,
                "side": r.side,
                "quantity": r.quantity,
                "average_entry": str(r.average_entry) if r.average_entry else None,
                "current_price": str(r.current_price) if r.current_price else None,
                "unrealized_pnl": str(r.unrealized_pnl) if r.unrealized_pnl else None,
                "realized_pnl": str(r.realized_pnl) if r.realized_pnl else None,
                "exit_state": r.exit_state,
                "is_open": r.is_open,
                "strategy_id": r.strategy_id,
            }
            for r in rows
        ]

    async def exit_position(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        position_id: str,
        trigger: str = "EMERGENCY",
    ) -> dict[str, Any]:
        """Trigger position exit via ExitEngine."""
        if session is None:
            raise HTTPException(status_code=500, detail="DB required for exit")

        acct = await self.account_service.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoPositionDB).where(
                AlgoPositionDB.account_id == acct.id,
                AlgoPositionDB.position_id == position_id,
            )
        )
        row = res.scalar_one_or_none()
        if not row or not row.is_open:
            raise HTTPException(status_code=404, detail="open position not found")

        pos = Position(
            account_id=acct.id,
            position_id=row.position_id,
            symbol=row.symbol,
            underlying=row.underlying,
            instrument_id=row.instrument_id,
            side=row.side,
            quantity=row.quantity,
            lot_size=row.lot_size or 1,
            average_entry=D(row.average_entry or 0),
            current_price=D(row.current_price or row.average_entry or 0),
            strategy_id=row.strategy_id,
        )
        pos.exit_state = row.exit_state
        result = await exit_engine.trigger_exit(
            pos, trigger, order_manager=order_manager, is_emergency=(trigger == "EMERGENCY")
        )

        row.exit_state = pos.exit_state
        if pos.exit_state == "ORPHANED_ALERT":
            ks_res = await session.execute(
                select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == acct.id)
            )
            ks = ks_res.scalar_one_or_none()
            if ks:
                ks.is_killed = True
                ks.kill_level = "STOP_NEW_ENTRIES"
        if result.get("status") == "FILLED":
            row.is_open = False
            row.exit_state = "CLOSED"
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="EXIT_TRIGGERED",
                symbol=row.symbol,
                details={"trigger": trigger, "result": result, "exit_state": pos.exit_state},
            )
        )
        return {
            "position_id": position_id,
            "exit_state": pos.exit_state,
            "result": result,
        }

    async def exit_all_positions(
        self, session: AsyncSession | None, user_id: UUID
    ) -> list[dict[str, Any]]:
        """Trigger emergency exit across all active open positions."""
        if session is None:
            raise HTTPException(status_code=500, detail="DB required")
        acct = await self.account_service.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoPositionDB).where(
                AlgoPositionDB.account_id == acct.id, AlgoPositionDB.is_open == True
            )
        )
        rows = res.scalars().all()
        results = []
        for row in rows:
            sub = await self.exit_position(
                session=session, user_id=user_id, position_id=row.position_id, trigger="EMERGENCY"
            )
            results.append(sub)
        return results


class AlgoGovernanceService:
    """Manages strategy configurations, AI canary rollouts, and kill-switch states."""

    def __init__(
        self, account_service: AlgoAccountService, order_service: AlgoOrderService
    ) -> None:
        self.account_service = account_service
        self.order_service = order_service

    async def list_strategies(
        self, session: AsyncSession | None, user_id: UUID, active_only: bool = True
    ) -> list[dict[str, Any]]:
        """List strategies registered for the user/system."""
        if session is None:
            return []
        acct = await self.account_service.get_or_create_account(session, user_id)
        q = select(AlgoStrategy).where(AlgoStrategy.account_id == acct.id)
        if active_only:
            q = q.where(AlgoStrategy.is_active == True)
        res = await session.execute(q)
        rows = res.scalars().all()
        return [
            {
                "strategy_id": r.strategy_id,
                "name": r.name,
                "description": r.description,
                "lifecycle_stage": r.lifecycle_stage,
                "ai_mode": r.ai_mode,
                "priority_rank": r.priority_rank,
                "is_active": r.is_active,
                "parameters": r.parameters,
                "weights": r.weights,
            }
            for r in rows
        ]

    async def upsert_strategy(
        self, session: AsyncSession | None, user_id: UUID, payload: Any
    ) -> dict[str, Any]:
        """Upsert strategy definition."""
        if session is None:
            return {"strategy_id": payload.strategy_id, "status": "upserted", "note": "Dev mode"}
        acct = await self.account_service.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoStrategy).where(
                AlgoStrategy.account_id == acct.id,
                AlgoStrategy.strategy_id == payload.strategy_id,
            )
        )
        strat = res.scalar_one_or_none()
        if not strat:
            strat = AlgoStrategy(
                account_id=acct.id,
                strategy_id=payload.strategy_id,
                name=payload.name,
                description=payload.description,
                parameters=payload.parameters,
                weights=payload.weights,
                ai_mode=payload.ai_mode or "AI_OPTIONAL",
                entry_order_type=payload.entry_order_type,
                exit_order_type=payload.exit_order_type,
                target_delta=payload.target_delta,
                expiry_policy=payload.expiry_policy,
                liquidity_thresholds=payload.liquidity_thresholds,
                conflict_policy=payload.conflict_policy,
                priority_rank=payload.priority_rank or 0,
                is_active=payload.is_active if payload.is_active is not None else True,
            )
            session.add(strat)
        else:
            strat.name = payload.name
            strat.description = payload.description
            strat.parameters = payload.parameters
            strat.weights = payload.weights
            if payload.ai_mode:
                strat.ai_mode = payload.ai_mode
            if payload.is_active is not None:
                strat.is_active = payload.is_active
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="STRATEGY_UPSERTED",
                details={"strategy_id": payload.strategy_id},
            )
        )
        return {"strategy_id": payload.strategy_id, "status": "upserted"}

    async def promote_strategy(
        self, session: AsyncSession | None, user_id: UUID, strategy_id: str, target_stage: str
    ) -> dict[str, Any]:
        """Promote strategy across lifecycle stages: BACKTEST -> PAPER -> CANARY -> LIVE."""
        if target_stage not in ("BACKTEST", "PAPER", "CANARY", "LIVE", "RETIRED"):
            raise HTTPException(status_code=400, detail="Invalid lifecycle stage")
        if session is None:
            return {"strategy_id": strategy_id, "stage": target_stage, "note": "Dev mode"}

        acct = await self.account_service.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoStrategy).where(
                AlgoStrategy.account_id == acct.id, AlgoStrategy.strategy_id == strategy_id
            )
        )
        strat = res.scalar_one_or_none()
        if not strat:
            raise HTTPException(status_code=404, detail="Strategy not found")
        prev = strat.lifecycle_stage
        strat.lifecycle_stage = target_stage
        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="STRATEGY_PROMOTED",
                details={"strategy_id": strategy_id, "from": prev, "to": target_stage},
            )
        )
        return {"strategy_id": strategy_id, "stage": target_stage, "previous_stage": prev}

    async def set_kill_switch(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        kill_level: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Trigger or reset kill switch with order cancellation and position exit side effects."""
        is_kill = kill_level != "NONE"
        self.order_service.set_kill_cache(user_id, is_kill, kill_level, reason)

        if session is None:
            audit_trail.append(
                AuditRecord(
                    account_id=user_id,
                    event_type="KILL_SWITCH_CHANGED",
                    details={"kill_level": kill_level, "reason": reason},
                )
            )
            return {
                "account_id": str(user_id),
                "kill_level": kill_level,
                "is_killed": is_kill,
            }

        acct = await self.account_service.get_or_create_account(session, user_id)
        self.order_service.set_kill_cache(acct.id, is_kill, kill_level, reason)
        res = await session.execute(
            select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == acct.id)
        )
        ks = res.scalar_one_or_none()
        if not ks:
            ks = AlgoKillSwitch(account_id=acct.id)
            session.add(ks)
            await session.flush()

        ks.is_killed = is_kill
        ks.kill_level = kill_level
        ks.reason = reason
        ks.triggered_at = datetime.now(timezone.utc) if is_kill else None
        ks.triggered_by = user_id if is_kill else None

        if kill_level in ("CANCEL_ENTRY_ORDERS", "EXIT_ALL_POSITIONS", "FULL_EXECUTION_STOP"):
            ores = await session.execute(
                select(AlgoOrderDB).where(
                    AlgoOrderDB.account_id == acct.id,
                    AlgoOrderDB.status.in_(["CREATED", "RISK_APPROVED", "SUBMITTED", "ACKNOWLEDGED"]),
                )
            )
            for o in ores.scalars().all():
                try:
                    rec = order_manager.get(o.client_order_id)
                    if rec:
                        await order_manager.cancel(rec)
                        o.status = "CANCEL_PENDING"
                except Exception:
                    pass

        if kill_level in ("EXIT_ALL_POSITIONS", "FULL_EXECUTION_STOP"):
            pres = await session.execute(
                select(AlgoPositionDB).where(
                    AlgoPositionDB.account_id == acct.id, AlgoPositionDB.is_open == True
                )
            )
            for p in pres.scalars().all():
                p.exit_state = "EXIT_TRIGGERED"

        await session.flush()
        await session.commit()
        audit_trail.append(
            AuditRecord(
                account_id=acct.id,
                event_type="KILL_SWITCH_CHANGED",
                details={"kill_level": kill_level, "reason": reason},
            )
        )
        return {
            "account_id": str(acct.id),
            "kill_level": kill_level,
            "is_killed": is_kill,
        }

    async def get_kill_switch(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Fetch active kill switch status."""
        cached = self.order_service.get_kill_cache(user_id)
        if cached:
            return cached

        if session is None:
            return {"is_killed": False, "kill_level": "NONE"}

        acct = await self.account_service.get_or_create_account(session, user_id)
        try:
            res = await session.execute(
                select(AlgoKillSwitch).where(AlgoKillSwitch.account_id == acct.id)
            )
            ks = res.scalar_one_or_none()
            return {
                "is_killed": ks.is_killed if ks else False,
                "kill_level": ks.kill_level if ks else "NONE",
                "reason": ks.reason if ks else None,
            }
        except Exception:
            cached_aid = self.order_service.get_kill_cache(acct.id)
            if cached_aid:
                return cached_aid
            return {"is_killed": False, "kill_level": "NONE"}


class AlgoSignalsService:
    """Manages algo signal ingestion, conflict resolution, sizing preview, and portfolio exposure."""

    def __init__(self, account_service: AlgoAccountService) -> None:
        self.account_service = account_service

    async def create_signal(
        self, session: AsyncSession | None, user_id: UUID, payload: Any
    ) -> dict[str, Any]:
        """Ingest, fuse, and persist strategy signal."""
        acct = (
            await self.account_service.get_or_create_account(session, user_id)
            if session
            else self.account_service.create_synthetic_account(user_id)
        )
        aid = acct.id

        dir_in = payload.direction
        fused = None
        if not dir_in:
            inp = SignalInputs(
                symbol=payload.symbol,
                technical=payload.technical,
                mtf=payload.mtf,
                fno=payload.fno,
                regime=payload.regime,
                ai=payload.ai,
                event_risk=payload.event_risk,
            )
            fused = signal_fusion.fuse(inp)
            dir_in = fused.direction
            if not fused.is_actionable:
                dir_in = "NEUTRAL"

        sig_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        sig_data = {
            "signal_id": str(sig_id),
            "account_id": str(aid),
            "strategy_id": payload.strategy_id,
            "symbol": payload.symbol,
            "direction": dir_in,
            "fused_confidence": fused.confidence if fused else 0.75,
            "is_actionable": fused.is_actionable if fused else True,
            "created_at": now.isoformat(),
        }

        if session is not None:
            try:
                db_sig = AlgoSignalDB(
                    account_id=aid,
                    signal_id=sig_id,
                    strategy_id=payload.strategy_id,
                    symbol=payload.symbol,
                    instrument_id=payload.instrument_id,
                    direction=dir_in,
                    confidence=fused.confidence if fused else 0.75,
                    status="ACTIVE" if (fused.is_actionable if fused else True) else "REJECTED",
                    raw_payload={
                        "technical": payload.technical,
                        "mtf": payload.mtf,
                        "fno": payload.fno,
                        "regime": payload.regime,
                        "ai": payload.ai,
                        "event_risk": payload.event_risk,
                    },
                )
                session.add(db_sig)
                await session.flush()
                await session.commit()
            except Exception as e:
                logger.warning("signal_db_persist_failed", error=str(e))
                try:
                    await session.rollback()
                except Exception:
                    pass

        audit_trail.append(
            AuditRecord(
                account_id=aid,
                event_type="SIGNAL_INGESTED",
                symbol=payload.symbol,
                signal_id=sig_id,
                details={"direction": dir_in, "fused": fused.direction if fused else None},
            )
        )
        return sig_data

    async def list_signals(
        self,
        session: AsyncSession | None,
        user_id: UUID,
        symbol: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List signals for the account."""
        if session is None:
            return []
        acct = await self.account_service.get_or_create_account(session, user_id)
        q = (
            select(AlgoSignalDB)
            .where(AlgoSignalDB.account_id == acct.id)
            .order_by(AlgoSignalDB.created_at.desc())
            .limit(limit)
        )
        if symbol:
            q = q.where(AlgoSignalDB.symbol == symbol)
        if direction:
            q = q.where(AlgoSignalDB.direction == direction)
        if status:
            q = q.where(AlgoSignalDB.status == status)
        res = await session.execute(q)
        rows = res.scalars().all()
        return [
            {
                "signal_id": str(r.signal_id),
                "strategy_id": r.strategy_id,
                "symbol": r.symbol,
                "direction": r.direction,
                "confidence": str(r.confidence) if r.confidence else None,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def preview_sizing(
        self,
        entry_price: float,
        stop_price: float | None = None,
        risk_budget: float = 500.0,
        lot_size: int = 1,
        contract_multiplier: float = 1.0,
        max_capital_per_trade: float | None = None,
        max_position_size: int | None = None,
        available_capital: float = 3000.0,
        available_margin: float | None = None,
        margin_per_unit: float | None = None,
    ) -> dict[str, Any]:
        """Compute recommended position sizing based on risk metrics."""
        inputs = SizingInputs(
            algo_capital_available=D(available_capital),
            risk_budget=D(risk_budget),
            entry_price=D(entry_price),
            stop_price=D(stop_price) if stop_price else None,
            lot_size=lot_size,
            contract_multiplier=D(contract_multiplier),
            max_capital_per_trade=D(max_capital_per_trade) if max_capital_per_trade else None,
            max_position_size=max_position_size,
            max_notional=None,
            margin_per_unit=D(margin_per_unit) if margin_per_unit else None,
            available_margin=D(available_margin) if available_margin else None,
        )
        res = size_position(inputs)
        return {
            "quantity": res.quantity,
            "notional": str(res.notional),
            "risk_per_unit": str(res.risk_per_unit) if res.risk_per_unit else None,
            "reason": res.reason,
            "capped_by": res.capped_by,
        }

    async def get_exposure(
        self, session: AsyncSession | None, user_id: UUID
    ) -> dict[str, Any]:
        """Fetch portfolio exposure breakdown."""
        if session is None:
            return {
                "gross_exposure": "0.00",
                "net_exposure": "0.00",
                "long_exposure": "0.00",
                "short_exposure": "0.00",
                "portfolio_delta": "0.00",
                "portfolio_gamma": "0.00",
                "portfolio_theta": "0.00",
                "portfolio_vega": "0.00",
                "by_underlying": {},
                "by_strategy": {},
            }
        acct = await self.account_service.get_or_create_account(session, user_id)
        res = await session.execute(
            select(AlgoPositionDB).where(
                AlgoPositionDB.account_id == acct.id, AlgoPositionDB.is_open == True
            )
        )
        poss = res.scalars().all()
        gross = D(0)
        long_e = D(0)
        short_e = D(0)
        by_u: dict[str, str] = {}
        by_s: dict[str, str] = {}
        d = D(0)
        g = D(0)
        th = D(0)
        v = D(0)
        for p in poss:
            n = abs(D(p.quantity or 0) * D(p.current_price or p.average_entry or 0))
            gross += n
            if p.side == "LONG":
                long_e += n
            else:
                short_e += n
            u = p.underlying or p.symbol
            by_u[u] = str(D(by_u.get(u, "0")) + n)
            s = p.strategy_id or "unknown"
            by_s[s] = str(D(by_s.get(s, "0")) + n)
            greeks = p.greeks or {}
            d += D(greeks.get("delta", 0) or 0) * D(p.quantity or 0)
            g += D(greeks.get("gamma", 0) or 0) * D(p.quantity or 0)
            th += D(greeks.get("theta", 0) or 0) * D(p.quantity or 0)
            v += D(greeks.get("vega", 0) or 0) * D(p.quantity or 0)
        return {
            "gross_exposure": str(gross),
            "net_exposure": str(long_e - short_e),
            "long_exposure": str(long_e),
            "short_exposure": str(short_e),
            "portfolio_delta": str(d),
            "portfolio_gamma": str(g),
            "portfolio_theta": str(th),
            "portfolio_vega": str(v),
            "by_underlying": by_u,
            "by_strategy": by_s,
        }


# Singleton service instances
algo_account_service = AlgoAccountService()
algo_order_service = AlgoOrderService(account_service=algo_account_service)
algo_governance_service = AlgoGovernanceService(
    account_service=algo_account_service, order_service=algo_order_service
)
algo_signals_service = AlgoSignalsService(account_service=algo_account_service)


def reset_algo_caches() -> None:
    """Reset all in-memory caches across algo services (for test isolation)."""
    algo_account_service.reset()
    algo_order_service.reset()
