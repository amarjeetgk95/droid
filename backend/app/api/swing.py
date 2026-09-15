"""
FastAPI Endpoints for Droid Swing Trading Module (v6.0 Options Overhaul).
Provides REST endpoints for:
  - Options Universe & Underlyings Directory
  - Market Regime & IV Telemetry
  - Active & Filtered Options Setups
  - On-Demand Options Scanner Execution
  - Multi-Day Options Position Management (Dual-Layer Stops)
  - AI Copilot Options Thesis Generation
"""
from __future__ import annotations

import time
from typing import Optional, Literal
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
import structlog

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.swing.models import SwingSetup, SwingPosition, ExitReason
from app.swing.universe import get_all_universe, get_all_sectors, get_swing_universe
from app.swing.scanner import swing_scanner
from app.swing.persistence import load_swing_state, save_swing_state
from app.swing.portfolio_risk import portfolio_risk_manager
from app.swing.lifecycle import create_position_from_setup, close_position

logger = structlog.get_logger()
router = APIRouter(prefix="/api/v1/swing", tags=["Swing Trading"])


class ScanRequest(BaseModel):
    portfolio_equity: float = 1_000_000.0
    force_refresh: bool = False
    limit_symbols: Optional[list[str]] = None
    horizon: str = "ALL"  # "ALL", "POSITIONAL", "INTRADAY"


class EnterPositionRequest(BaseModel):
    setup_id: str
    fill_premium: Optional[float] = None
    fill_price: Optional[float] = None  # Backward compatibility alias
    num_lots: Optional[int] = None
    quantity: Optional[int] = None      # Backward compatibility alias


class ExitPositionRequest(BaseModel):
    position_id: str
    exit_premium: Optional[float] = None
    exit_price: Optional[float] = None  # Backward compatibility alias
    exit_reason: ExitReason = "MANUAL_EXIT"


class ThesisRequest(BaseModel):
    setup_id: str


@router.get("/universe")
async def get_universe():
    """Returns all tracked swing options underlyings."""
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
    """Returns current market regime, India VIX / IV percentile, and sector momentum."""
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
    underlying: Optional[str] = Query(default=None),
    sector: Optional[str] = Query(default=None),
    min_score: Optional[float] = Query(default=None),
    state: Optional[str] = Query(default=None),
    direction: Optional[str] = Query(default=None),
    horizon: Optional[str] = Query(default=None),
):
    """Lists current swing options setups with optional filters."""
    last_res = swing_scanner.get_last_result()
    setups = last_res.get("setups", [])

    filtered = []
    for s in setups:
        if strategy and s.get("strategy", "").upper() != strategy.upper():
            continue
        und_filter = underlying or sector
        if und_filter and s.get("underlying", "").upper() != und_filter.upper():
            continue
        if min_score is not None:
            score_total = s.get("score", {}).get("total", 0.0)
            if score_total < min_score:
                continue
        if state and s.get("signal_state", "").upper() != state.upper():
            continue
        if direction and s.get("direction", "").upper() != direction.upper():
            continue
        if horizon and horizon.upper() != "ALL":
            s_horiz = s.get("horizon", "POSITIONAL")
            if s_horiz.upper() != horizon.upper():
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
    """Triggers an on-demand scan of the swing options universe."""
    try:
        res = await swing_scanner.run_scan(
            portfolio_equity=req.portfolio_equity,
            force_refresh=req.force_refresh,
            limit_symbols=req.limit_symbols,
            horizon=req.horizon,
        )
        return envelope(res, provider="fyers", status=DataStatus.LIVE)
    except Exception as e:
        logger.error("swing_scan_api_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Swing scan failed: {str(e)[:150]}")


@router.get("/positions")
async def get_positions():
    """Returns active open options positions, closed history, and portfolio Greeks."""
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
    """
    Enters a swing options setup into the active portfolio.
    Enforces server-side revalidation (§50):
      - Setup exists and is still valid
      - Four-layer trade validity overall_valid == True
      - Portfolio risk ceiling allows addition
      - Execution fill premium sanity check
    """
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    open_pos: list[SwingPosition] = state.get("open_positions", [])
    closed_pos: list[SwingPosition] = state.get("closed_positions", [])
    regime = state.get("regime")

    target_setup = next((s for s in setups if s.setup_id == req.setup_id), None)
    if not target_setup:
        raise HTTPException(status_code=404, detail="Setup not found.")

    # Server-side revalidation
    if target_setup.signal_state in ("EXPIRED", "INVALIDATED"):
        raise HTTPException(status_code=400, detail=f"Setup is no longer actionable (state: {target_setup.signal_state}).")

    if not target_setup.trade_validity.overall_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Trade validity failed: {', '.join(target_setup.trade_validity.rejection_reasons)}",
        )

    fill_premium = req.fill_premium if req.fill_premium is not None else req.fill_price
    if fill_premium is None or fill_premium <= 0:
        fill_premium = target_setup.entry_premium

    num_lots = req.num_lots if req.num_lots is not None else req.quantity
    if not num_lots or num_lots <= 0:
        # Determine lots from 1% risk budget
        risk_budget = portfolio_risk_manager.total_equity * 0.01
        num_lots = max(1, int(risk_budget / max(1.0, target_setup.premium_risk_per_lot)))

    # Validate portfolio risk gate
    is_allowed, reason = portfolio_risk_manager.validate_candidate(target_setup, open_pos, planned_lots=num_lots)
    if not is_allowed:
        raise HTTPException(status_code=400, detail=f"Risk Gate Rejection: {reason}")

    try:
        new_pos = create_position_from_setup(target_setup, fill_premium, num_lots)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    open_pos.append(new_pos)
    target_setup.signal_state = "ENTERED"

    save_swing_state(setups, open_pos, closed_pos, regime)
    logger.info("swing_position_entered", contract=target_setup.contract_symbol, lots=num_lots, premium=fill_premium)

    return envelope(new_pos.model_dump(mode="json"), provider="fyers", status=DataStatus.LIVE)


@router.post("/positions/exit")
async def exit_position(req: ExitPositionRequest):
    """Closes an active swing options position, updates ledger, and records structured exit reason."""
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    open_pos: list[SwingPosition] = state.get("open_positions", [])
    closed_pos: list[SwingPosition] = state.get("closed_positions", [])
    regime = state.get("regime")

    pos_idx = next((i for i, p in enumerate(open_pos) if p.position_id == req.position_id), None)
    if pos_idx is None:
        raise HTTPException(status_code=404, detail="Position not found.")

    pos = open_pos.pop(pos_idx)
    exit_premium = req.exit_premium if req.exit_premium is not None else req.exit_price
    if exit_premium is None or exit_premium <= 0:
        exit_premium = pos.current_premium

    closed_pos_record = close_position(pos, exit_premium, req.exit_reason)
    closed_pos.append(closed_pos_record)

    save_swing_state(setups, open_pos, closed_pos, regime)
    logger.info("swing_position_closed", contract=pos.contract_symbol, exit_premium=exit_premium, r=closed_pos_record.r_multiple)

    return envelope(closed_pos_record.model_dump(mode="json"), provider="fyers", status=DataStatus.LIVE)


@router.post("/thesis")
async def generate_ai_thesis(req: ThesisRequest):
    """
    Constructs a structured prompt payload for the AI Copilot to deliver an
    unbiased options thesis, volatility context, and invalidation roadmap (§53).
    """
    state = load_swing_state()
    setups: list[SwingSetup] = state.get("setups", [])
    setup = next((s for s in setups if s.setup_id == req.setup_id), None)
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found.")

    delta = setup.greeks.get("delta", 0.0)
    gamma = setup.greeks.get("gamma", 0.0)
    theta_day = setup.greeks.get("theta_day", 0.0)
    vega = setup.greeks.get("vega", 0.0)

    thesis_context = {
        "underlying": setup.underlying,
        "contract": setup.contract_symbol,
        "direction": setup.direction,
        "option_type": setup.option_type,
        "strike": setup.strike,
        "expiry": setup.expiry_date,
        "dte": setup.dte,
        "setup_score": setup.score.total,
        "market_regime": setup.market_regime,
        "iv": f"{setup.iv * 100:.1f}%",
        "iv_percentile": f"{setup.iv_percentile:.1f}% ({setup.iv_regime})",
        "spot_price": f"₹{setup.spot_price:.2f}",
        "spot_trigger": f"₹{setup.spot_trigger:.2f}",
        "spot_stop": f"₹{setup.spot_stop:.2f}",
        "entry_premium": f"₹{setup.entry_premium:.2f}",
        "stop_premium": f"₹{setup.stop_premium:.2f}",
        "target_1": f"₹{setup.target_premium_1:.2f} (1.5R)",
        "target_2": f"₹{setup.target_premium_2:.2f} (3.0R)",
        "greeks": f"Δ: {delta:.2f} | Γ: {gamma:.4f} | Θ: ₹{theta_day:.2f}/day | ν: ₹{vega:.2f}",
        "theta_drag_ratio": f"{setup.theta_drag_ratio:.1f}%",
        "expected_holding_days": setup.expected_holding_days,
        "technical_confirmations": setup.technical_reasons,
        "options_confirmations": setup.options_reasons,
        "risk_factors": setup.risk_reasons,
        "invalidation_criteria": setup.invalidation_rules,
    }

    prompt = f"""You are an elite quantitative options swing trading analyst for the Indian Index Markets (NSE/BSE).
Provide an objective, structured trade briefing based strictly on this verified deterministic setup:

Underlying: {setup.underlying} | Direction: {setup.direction} ({setup.option_type})
Contract: {setup.contract_symbol} (Strike: {setup.strike} | Expiry: {setup.expiry_date} | DTE: {setup.dte})
Underlying Spot: ₹{setup.spot_price} | Trigger: ₹{setup.spot_trigger} | Spot Thesis Invalidation: ₹{setup.spot_stop}
Option Premium: Entry ₹{setup.entry_premium} | Stop ₹{setup.stop_premium} | T1 ₹{setup.target_premium_1} | T2 ₹{setup.target_premium_2}
Greeks: Delta {delta:.2f}, Gamma {gamma:.4f}, Daily Theta ₹{theta_day:.2f}/unit, Vega ₹{vega:.2f}
Volatility: IV {setup.iv * 100:.1f}% | IV Rank {setup.iv_percentile:.1f}% ({setup.iv_regime}) | Theta Drag {setup.theta_drag_ratio:.1f}%
Expected Holding Period: {setup.expected_holding_days} trading days

Confirmations:
{chr(10).join('- ' + r for r in setup.technical_reasons)}
{chr(10).join('- ' + r for r in setup.options_reasons)}

Risks & Invalidation:
{chr(10).join('- ' + r for r in setup.risk_reasons)}
{chr(10).join('- ' + r for r in setup.invalidation_rules)}

Respond in 4 concise sections:
1. **Underlying Directional Thesis**: Why the underlying index is expected to reach the target within {setup.expected_holding_days} days.
2. **Option Contract & Greeks Rationale**: Why this strike, expiry, and delta profile ({delta:.2f}) balance gamma leverage vs theta burn.
3. **Volatility & Threat Analysis**: What could cause this trade to lose despite being directionally correct (IV crush, theta decay, weekend risk).
4. **Dual-Layer Stop Management**: Exact actions if underlying breaches ₹{setup.spot_stop} OR option premium falls below ₹{setup.stop_premium}, and trailing stop protocol at +1.5R.
Never invent price levels or override the stop losses."""

    return envelope(
        {
            "setup_id": setup.setup_id,
            "contract": setup.contract_symbol,
            "context": thesis_context,
            "structured_prompt": prompt,
        },
        provider="fyers",
        status=DataStatus.LIVE,
    )

