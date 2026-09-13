"""
FastAPI Endpoints for Droid Swing Trading Module (v5.0).
Provides REST endpoints for:
  - Universe & Sector Directory
  - Market Regime & Breadth
  - Active & Filtered Setups
  - On-Demand Scanner Execution
  - Multi-Day Position Management
  - AI Copilot Thesis Generation
"""
from __future__ import annotations

import time
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
import structlog

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.swing.models import SwingSetup, SwingPosition
from app.swing.universe import get_all_universe, get_all_sectors, get_swing_universe
from app.swing.scanner import swing_scanner
from app.swing.persistence import load_swing_state, save_swing_state
from app.swing.portfolio_risk import portfolio_risk_manager
from app.swing.lifecycle import create_position_from_setup

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/swing", tags=["Swing Trading"])


class ScanRequest(BaseModel):
    portfolio_equity: float = 1_000_000.0
    force_refresh: bool = False
    limit_symbols: Optional[list[str]] = None


class EnterPositionRequest(BaseModel):
    setup_id: str
    fill_price: float
    quantity: Optional[int] = None


class ExitPositionRequest(BaseModel):
    position_id: str
    exit_price: float
    exit_reason: str = "MANUAL_EXIT"


class ThesisRequest(BaseModel):
    setup_id: str


@router.get("/universe")
async def get_universe():
    """Returns all tracked swing equities and benchmark indices."""
    universe = get_all_universe()
    sectors = get_all_sectors()
    return envelope(
        {
            "total_count": len(universe),
            "sectors": sectors,
            "instruments": [u.model_dump(mode="json") for u in universe],
        },
        provider="fyers",
        status=DataStatus.LIVE,
    )


@router.get("/regime")
async def get_regime():
    """Returns current market regime and sector momentum."""
    last_res = swing_scanner.get_last_result()
    regime = last_res.get("regime")
    sectors = last_res.get("sectors", [])
    return envelope(
        {
            "regime": regime,
            "sectors": sectors,
            "scan_timestamp_utc": last_res.get("scan_timestamp_utc"),
        },
        provider="fyers",
        status=DataStatus.LIVE if regime else DataStatus.OFFLINE,
    )


@router.get("/setups")
async def get_setups(
    strategy: Optional[str] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """Lists current swing setups with optional filters."""
    last_res = swing_scanner.get_last_result()
    setups = last_res.get("setups", [])

    filtered = []
    for s in setups:
        if strategy and s.get("strategy", "").upper() != strategy.upper():
            continue
        if sector and s.get("sector", "").lower() != sector.lower():
            continue
        if min_score is not None:
            score_total = s.get("score", {}).get("total", 0.0)
            if score_total < min_score:
                continue
        if state and s.get("signal_state", "").upper() != state.upper():
            continue
        filtered.append(s)

    return envelope(
        {
            "count": len(filtered),
            "total_unfiltered": len(setups),
            "setups": filtered,
        },
        provider="fyers",
        status=DataStatus.LIVE,
    )


@router.post("/scan")
async def trigger_scan(req: ScanRequest = Body(default=ScanRequest())):
    """Triggers an on-demand scan of the swing universe."""
    try:
        res = await swing_scanner.run_scan(
            portfolio_equity=req.portfolio_equity,
            force_refresh=req.force_refresh,
            limit_symbols=req.limit_symbols,
        )
        return envelope(res, provider="fyers", status=DataStatus.LIVE)
    except Exception as e:
        logger.error("swing_scan_api_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Swing scan failed: {str(e)[:150]}")


@router.get("/positions")
async def get_positions():
    """Returns active open positions, closed history, and portfolio heat metrics."""
    state = load_swing_state()
    open_pos = state.get("open_positions", [])
    closed_pos = state.get("closed_positions", [])
    port_state = portfolio_risk_manager.compute_portfolio_state(open_pos)

    return envelope(
        {
            "open_positions": [p.model_dump(mode="json") for p in open_pos],
            "closed_positions": [p.model_dump(mode="json") for p in closed_pos[-50:]],
            "portfolio_risk": port_state.model_dump(mode="json"),
        },
        provider="fyers",
        status=DataStatus.LIVE,
    )


@router.post("/positions/enter")
async def enter_position(req: EnterPositionRequest):
    """Enters a swing setup into the active multi-day portfolio."""
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    open_pos: list[SwingPosition] = state.get("open_positions", [])
    closed_pos: list[SwingPosition] = state.get("closed_positions", [])
    regime = state.get("regime")

    target_setup = next((s for s in setups if s.setup_id == req.setup_id), None)
    if not target_setup:
        raise HTTPException(status_code=404, detail="Setup not found.")

    # Validate portfolio risk gate
    is_allowed, reason = portfolio_risk_manager.validate_candidate(target_setup, open_pos)
    if not is_allowed:
        raise HTTPException(status_code=400, detail=f"Risk Gate Rejection: {reason}")

    # Determine quantity
    qty = req.quantity
    if not qty or qty <= 0:
        # Calculate from 1% risk budget
        risk_budget = portfolio_risk_manager.total_equity * 0.01
        qty = max(1, int(risk_budget / max(0.01, target_setup.risk_per_share)))

    new_pos = create_position_from_setup(target_setup, req.fill_price, qty)
    open_pos.append(new_pos)

    # Update setup state to ENTERED
    target_setup.signal_state = "ENTERED"

    save_swing_state(setups, open_pos, closed_pos, regime)
    logger.info("swing_position_entered", symbol=target_setup.symbol, qty=qty, price=req.fill_price)

    return envelope(new_pos.model_dump(mode="json"), provider="fyers", status=DataStatus.LIVE)


@router.post("/positions/exit")
async def exit_position(req: ExitPositionRequest):
    """Manually or rule-based exits an active swing position."""
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    open_pos: list[SwingPosition] = state.get("open_positions", [])
    closed_pos: list[SwingPosition] = state.get("closed_positions", [])
    regime = state.get("regime")

    pos_idx = next((i for i, p in enumerate(open_pos) if p.position_id == req.position_id), None)
    if pos_idx is None:
        raise HTTPException(status_code=404, detail="Position not found.")

    pos = open_pos.pop(pos_idx)
    pos.status = "CLOSED"
    pos.close_price = round(req.exit_price, 2)
    pos.closed_at_utc = int(time.time() * 1000)
    pos.exit_reason = req.exit_reason

    risk_dist = max(0.01, pos.entry_price - pos.initial_stop)
    final_gain = pos.close_price - pos.entry_price
    pos.unrealized_pnl = round(final_gain * pos.quantity, 2)
    pos.pnl_pct = round((final_gain / pos.entry_price) * 100.0, 2)
    pos.r_multiple = round(final_gain / risk_dist, 2)

    closed_pos.append(pos)
    save_swing_state(setups, open_pos, closed_pos, regime)
    logger.info("swing_position_closed", symbol=pos.symbol, exit_price=req.exit_price, r=pos.r_multiple)

    return envelope(pos.model_dump(mode="json"), provider="fyers", status=DataStatus.LIVE)


@router.post("/thesis")
async def generate_ai_thesis(req: ThesisRequest):
    """
    Constructs a structured prompt payload for the AI Copilot to deliver an
    unbiased thesis, catalyst analysis, and invalidation roadmap (§57).
    """
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    setup = next((s for s in setups if s.setup_id == req.setup_id), None)
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found.")

    # Structured prompt input ensuring AI does not hallucinate levels
    thesis_context = {
        "symbol": setup.symbol,
        "sector": setup.sector,
        "strategy": setup.strategy,
        "setup_score": setup.score.total,
        "market_regime": setup.market_regime,
        "sector_trend": setup.sector_state,
        "entry_range": f"₹{setup.entry_zone_min} - ₹{setup.entry_zone_max}",
        "trigger": f"₹{setup.trigger_price}",
        "stop_loss": f"₹{setup.stop_price} (ATR Floor: ₹{setup.atr_floor})",
        "target_1": f"₹{setup.target_1} (1.5R)",
        "target_2": f"₹{setup.target_2} (3.0R)",
        "expected_holding_days": setup.expected_holding_days,
        "technical_confirmations": setup.technical_reasons,
        "risk_factors": setup.risk_reasons,
        "invalidation_criteria": setup.invalidation_rules,
    }

    prompt = f"""You are an elite quantitative swing trading analyst for the Indian Stock Market.
Provide a concise, objective trade briefing based strictly on this verified deterministic setup:

Symbol: {setup.symbol} ({setup.sector})
Strategy: {setup.strategy} | Score: {setup.score.total}/100
Market Regime: {setup.market_regime} | Sector Trend: {setup.sector_state}
Trigger: ₹{setup.trigger_price} | Invalidation Stop: ₹{setup.stop_price}
Target 1: ₹{setup.target_1} (1.5R) | Target 2: ₹{setup.target_2} (3.0R)
Expected Holding Period: {setup.expected_holding_days} trading days

Confirmations:
{chr(10).join('- ' + r for r in setup.technical_reasons)}

Risks & Invalidation:
{chr(10).join('- ' + r for r in setup.risk_reasons)}
{chr(10).join('- ' + r for r in setup.invalidation_rules)}

Respond in 4 concise sections:
1. **Thesis (Why This Setup Works)**: Structural context and price action quality.
2. **Key Catalysts & Tailwinds**: Sector alignment and momentum rationale.
3. **Invalidation Checklist**: Exactly what price behavior voids this thesis.
4. **Execution Advice**: Max chase warning (+1.0% limit) and trailing stop protocol.
Never invent price targets or override the stop loss."""

    return envelope(
        {
            "setup_id": setup.setup_id,
            "symbol": setup.symbol,
            "context": thesis_context,
            "structured_prompt": prompt,
        },
        provider="fyers",
        status=DataStatus.LIVE,
    )
