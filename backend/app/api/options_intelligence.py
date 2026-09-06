"""
Options Intelligence & Multi-Horizon Research REST API
Exposes the institutional engine to the dashboard and API clients:
  - Analytical Black-Scholes Greeks & IV solver
  - Path-dependent option simulator with Indian statutory friction
  - Quantitative Strike & Expiry selector
  - Expected Move & Timing engine
  - AI Financial Research Context & Contradiction reporting (§42)
  - Portfolio Greeks Ledger & Cross-Horizon summary (§36, §51)
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Query

from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult
from app.signals.options_intelligence.path_simulator import (
    PathDependentOptionSimulator,
    PathSimulationReport,
)
from app.signals.options_intelligence.selector import (
    quantitative_contract_selector,
    StrikeSelectionResult,
)
from app.signals.expected_move import (
    expected_move_engine,
    ExpectedMoveProjection,
    TradingHorizon,
    DirectionalBias,
)
from app.signals.portfolio_greeks import (
    portfolio_greeks_ledger,
    PortfolioGreeksSummary,
    MarginalGreekCheckResult,
)
from app.ai.financial_research.context_store import ai_context_store
from app.ai.financial_research.engine import financial_research_engine
from app.ai.financial_research.schemas import FinancialResearchReport

router = APIRouter(prefix="/api/v1/options-intelligence", tags=["options-intelligence"])
simulator = PathDependentOptionSimulator()


# Request / Response DTOs
class GreeksRequest(BaseModel):
    spot: float
    strike: float
    dte_days: float
    volatility: float
    option_type: Literal["CE", "PE"]
    risk_free_rate: float = 0.065
    dividend_yield: float = 0.012


class SolveIVRequest(BaseModel):
    market_price: float
    spot: float
    strike: float
    dte_days: float
    option_type: Literal["CE", "PE"]


class PathSimulateRequest(BaseModel):
    underlying: str
    spot: float
    strike: float
    option_type: Literal["CE", "PE"]
    dte_days: float
    iv: float
    target_spot: float
    stop_spot: float
    quantity: int = 75
    expected_fast_hours: float = 0.5
    expected_slow_hours: float = 3.0


class SelectContractRequest(BaseModel):
    underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    spot_price: float
    direction: Literal["LONG_CALL", "LONG_PUT"]
    expected_move_points: Optional[float] = None
    stop_loss_points: float = 30.0
    target_horizon_hours: float = 1.0
    current_iv: float = 0.16


class ExpectedMoveRequest(BaseModel):
    underlying: str
    spot: float
    direction: DirectionalBias
    horizon: TradingHorizon = "INTRADAY"
    current_iv: float = 0.15
    atr: Optional[float] = None
    structural_target: Optional[float] = None
    regime: str = "TREND_UP"
    hourly_theta_decay: Optional[float] = None


@router.post("/greeks", response_model=GreeksResult)
def calculate_greeks(req: GreeksRequest):
    """Calculate analytical Black-Scholes Greeks and theoretical pricing."""
    t_years = max(1e-6, req.dte_days / 365.0)
    return BlackScholesGreeks.calculate_greeks(
        spot=req.spot,
        strike=req.strike,
        time_to_expiry_years=t_years,
        volatility=req.volatility,
        option_type=req.option_type,
        risk_free_rate=req.risk_free_rate,
        dividend_yield=req.dividend_yield,
    )


@router.post("/solve-iv")
def solve_implied_volatility(req: SolveIVRequest):
    """Solve annualized implied volatility (IV) from option market premium."""
    t_years = max(1e-6, req.dte_days / 365.0)
    iv = BlackScholesGreeks.solve_iv(
        market_price=req.market_price,
        spot=req.spot,
        strike=req.strike,
        time_to_expiry_years=t_years,
        option_type=req.option_type,
    )
    return {"implied_volatility": iv, "iv_percent": round(iv * 100.0, 2)}


@router.post("/simulate-path", response_model=PathSimulationReport)
def simulate_option_path(req: PathSimulateRequest):
    """Simulate 5 path-dependent scenarios with Indian regulatory and microstructure friction."""
    return simulator.evaluate_candidate(
        underlying=req.underlying,
        spot=req.spot,
        strike=req.strike,
        option_type=req.option_type,
        dte_days=req.dte_days,
        iv=req.iv,
        target_spot=req.target_spot,
        stop_spot=req.stop_spot,
        quantity=req.quantity,
        expected_fast_hours=req.expected_fast_hours,
        expected_slow_hours=req.expected_slow_hours,
    )


@router.post("/select-contract")
def select_optimal_option_contract(req: SelectContractRequest):
    """Rank ITM, ATM, OTM candidates and select the best risk-adjusted contract."""
    res = quantitative_contract_selector.select_optimal_contract(
        underlying=req.underlying,
        spot_price=req.spot_price,
        direction=req.direction,
        expected_move_points=req.expected_move_points,
        stop_loss_points=req.stop_loss_points,
        target_horizon_hours=req.target_horizon_hours,
        current_iv=req.current_iv,
    )
    if not res:
        raise HTTPException(status_code=400, detail="Unable to evaluate contracts for given underlying")
    return res.model_dump(mode="json")


@router.post("/expected-move", response_model=ExpectedMoveProjection)
def project_expected_move(req: ExpectedMoveRequest):
    """Project underlying expected move magnitude, timing, and velocity vs option theta."""
    return expected_move_engine.project_move(
        underlying=req.underlying,
        spot=req.spot,
        direction=req.direction,
        horizon=req.horizon,
        current_iv=req.current_iv,
        atr=req.atr,
        structural_target=req.structural_target,
        regime=req.regime,
        hourly_theta_decay=req.hourly_theta_decay,
    )


@router.get("/portfolio-greeks/summary", response_model=PortfolioGreeksSummary)
def get_portfolio_greeks_summary():
    """Retrieve consolidated portfolio Greeks ledger (Delta, Gamma, Theta, Vega) across horizons."""
    return portfolio_greeks_ledger.get_summary()


@router.get("/financial-research/{underlying}", response_model=FinancialResearchReport)
def get_financial_research_context(
    underlying: str,
    horizon: TradingHorizon = Query(default="INTRADAY"),
    direction: Literal["BULLISH", "BEARISH"] = Query(default="BULLISH"),
):
    """Retrieve active or deterministic fallback AI financial research and contradiction analysis (§42)."""
    return ai_context_store.get_or_fallback_default(underlying=underlying, horizon=horizon, direction=direction)


class SynthesizeResearchRequest(BaseModel):
    underlying: str = "NIFTY"
    horizon: TradingHorizon = "INTRADAY"
    direction: Literal["BULLISH", "BEARISH"] = "BULLISH"


@router.post("/financial-research/synthesize", response_model=FinancialResearchReport)
def synthesize_financial_research(req: SynthesizeResearchRequest):
    """Dynamically synthesize fresh AI financial research and contradiction analysis for given underlying."""
    return financial_research_engine.generate_index_intelligence(
        underlying=req.underlying,
        horizon=req.horizon,
        direction=req.direction,
    )
