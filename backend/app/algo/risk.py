"""
Trade-Level & Portfolio-Level Risk Engines — §33-43, §82, §88

Fail-closed: any engine failure → REJECT (§82, §88.34-35)
Hierarchy: TradeRisk PASS → PortfolioRisk PASS → ExecutionSafety PASS
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Any
from uuid import UUID
from enum import Enum
import structlog

from app.algo.money import D

logger = structlog.get_logger()

RiskResult = Literal["APPROVED", "REJECTED"]
RiskStage = Literal["TRADE_RISK", "PORTFOLIO_RISK", "EXECUTION_SAFETY"]
PortfolioState = Literal["NORMAL","WARNING","RESTRICTED","LIMIT_REACHED","LIMIT_BREACHED","STRESS_BREACH","MARGIN_BREACH","CORRELATION_BREACH","GREEK_BREACH"]


@dataclass
class RiskCheck:
    name: str
    passed: bool
    reason: str | None = None
    value: Any | None = None
    threshold: Any | None = None


@dataclass
class RiskDecision:
    stage: RiskStage
    result: RiskResult
    reason: str | None = None
    failed_check: str | None = None
    checks: list[RiskCheck] = field(default_factory=list)
    portfolio_snapshot: dict | None = None


@dataclass
class OrderIntent:
    account_id: UUID
    client_order_id: UUID
    symbol: str
    instrument_id: str | None
    underlying: str | None
    side: str  # BUY/SELL
    quantity: int
    price: Decimal
    product: str = "INTRADAY"
    order_type: str = "LIMIT"
    strategy_id: str | None = None
    spread_id: UUID | None = None
    # optional for validation
    bid: Decimal | None = None
    ask: Decimal | None = None
    iv: Decimal | None = None
    greeks: dict | None = None
    expiry: str | None = None
    # market context
    data_health: str = "HEALTHY"  # HEALTHY/DEGRADED/STALE
    clock_health: str = "HEALTHY"
    broker_health: str = "HEALTHY"
    reconciliation_health: str = "HEALTHY"
    kill_switch_active: bool = False
    is_tradable: bool = True
    has_circuit: bool = False
    has_gap: bool = False
    capital_available: Decimal | None = None
    margin_available: Decimal | None = None
    estimated_margin: Decimal | None = None
    daily_loss: Decimal | None = None
    daily_loss_limit: Decimal | None = None
    # liquidity
    oi: int | None = None
    volume: int | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    spread_pct: Decimal | None = None
    slippage_pct: Decimal | None = None
    trading_hours_ok: bool = True
    is_duplicate_signal: bool = False
    is_duplicate_order: bool = False


class TradeRiskEngine:
    """
    Deterministic trade-level checks — §33
    Independent of AI (§33 last line)
    """

    def evaluate(self, intent: OrderIntent, limits: dict | None = None) -> RiskDecision:
        limits = limits or {}
        checks: list[RiskCheck] = []

        def chk(name: str, passed: bool, reason: str | None = None, value=None, threshold=None) -> bool:
            checks.append(RiskCheck(name=name, passed=passed, reason=reason, value=value, threshold=threshold))
            return passed

        try:
            # Kill switch first (§79 / §88.36)
            if not chk("kill_switch", not intent.kill_switch_active, "KILL_SWITCH_ACTIVE"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="KILL_SWITCH_ACTIVE", failed_check="kill_switch", checks=checks)

            # Data health (§82)
            if not chk("data_health", intent.data_health != "STALE", f"DATA_HEALTH_{intent.data_health}", value=intent.data_health):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="STALE_DATA", failed_check="data_health", checks=checks)

            # Clock health (§6)
            if not chk("clock_health", intent.clock_health != "STALE", "CLOCK_DRIFT_CRITICAL"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="CLOCK_DRIFT_CRITICAL", failed_check="clock_health", checks=checks)

            # Broker health
            if not chk("broker_health", intent.broker_health not in ("CRITICAL","DISCONNECTED"), f"BROKER_{intent.broker_health}"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="BROKER_UNHEALTHY", failed_check="broker_health", checks=checks)

            # Reconciliation health (§71)
            if not chk("reconciliation", intent.reconciliation_health != "BLOCKED", "RECONCILIATION_MISMATCH"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="RECONCILIATION_BLOCKED", failed_check="reconciliation", checks=checks)

            # Instrument valid & tradable (§10, §81)
            if not chk("instrument_tradable", intent.is_tradable, "INSTRUMENT_NOT_TRADABLE"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INSTRUMENT_NOT_TRADABLE", failed_check="instrument_tradable", checks=checks)

            # Circuit / halt (§58)
            if not chk("circuit", not intent.has_circuit, "CIRCUIT_OR_HALT_ACTIVE"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="CIRCUIT_OR_HALT_ACTIVE", failed_check="circuit", checks=checks)

            # Duplicate signal / order (§27 §51)
            if not chk("duplicate_signal", not intent.is_duplicate_signal, "DUPLICATE_SIGNAL"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="DUPLICATE_SIGNAL", failed_check="duplicate_signal", checks=checks)
            if not chk("duplicate_order", not intent.is_duplicate_order, "DUPLICATE_ORDER"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="DUPLICATE_ORDER", failed_check="duplicate_order", checks=checks)

            # Trading hours
            if not chk("trading_hours", intent.trading_hours_ok, "OUTSIDE_TRADING_HOURS"):
                return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="OUTSIDE_TRADING_HOURS", failed_check="trading_hours", checks=checks)

            # Capital available (§44-45)
            if intent.capital_available is not None:
                need = D(intent.price) * D(intent.quantity)
                # For options price*lot*qty already; simplified check
                if intent.estimated_margin is not None:
                    need = D(intent.estimated_margin)
                if not chk("algo_capital", D(need) <= D(intent.capital_available), f"INSUFFICIENT_CAPITAL need {need} avail {intent.capital_available}", value=str(need), threshold=str(intent.capital_available)):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INSUFFICIENT_CAPITAL", failed_check="algo_capital", checks=checks)

            # Margin (§40)
            if intent.margin_available is not None and intent.estimated_margin is not None:
                if not chk("margin", D(intent.estimated_margin) <= D(intent.margin_available), f"INSUFFICIENT_MARGIN {intent.estimated_margin} > {intent.margin_available}"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INSUFFICIENT_MARGIN", failed_check="margin", checks=checks)

            # Position / quantity limits
            max_qty = limits.get("max_position_quantity")
            if max_qty is not None:
                if not chk("position_size", intent.quantity <= int(max_qty), f"POSITION_SIZE_EXCEEDED {intent.quantity} > {max_qty}", value=intent.quantity, threshold=max_qty):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="POSITION_SIZE_EXCEEDED", failed_check="position_size", checks=checks)

            # Daily loss §78
            if intent.daily_loss is not None and intent.daily_loss_limit is not None:
                if not chk("daily_loss", D(intent.daily_loss) > -D(intent.daily_loss_limit), f"DAILY_LOSS_LIMIT_HIT {intent.daily_loss} limit {intent.daily_loss_limit}", value=str(intent.daily_loss), threshold=str(intent.daily_loss_limit)):
                    # Allow exits but block new entries — caller handles product; we REJECT new entry
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="DAILY_LOSS_LIMIT_HIT", failed_check="daily_loss", checks=checks)

            # Liquidity & spread §15
            min_oi = limits.get("min_oi")
            min_vol = limits.get("min_volume")
            min_bid = limits.get("min_bid_size")
            min_ask = limits.get("min_ask_size")
            max_spread = limits.get("max_spread_pct")
            max_slippage = limits.get("max_slippage_pct")

            if min_oi is not None and intent.oi is not None:
                if not chk("min_oi", intent.oi >= int(min_oi), f"OI_TOO_LOW {intent.oi} < {min_oi}"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="ILLIQUID_OI", failed_check="min_oi", checks=checks)
            if min_vol is not None and intent.volume is not None:
                if not chk("min_volume", intent.volume >= int(min_vol), f"VOLUME_TOO_LOW {intent.volume} < {min_vol}"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="ILLIQUID_VOLUME", failed_check="min_volume", checks=checks)
            if min_bid is not None and intent.bid_size is not None:
                if not chk("bid_size", intent.bid_size >= int(min_bid), f"BID_SIZE_TOO_LOW"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="ILLIQUID_BID_SIZE", failed_check="bid_size", checks=checks)
            if min_ask is not None and intent.ask_size is not None:
                if not chk("ask_size", intent.ask_size >= int(min_ask), f"ASK_SIZE_TOO_LOW"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="ILLIQUID_ASK_SIZE", failed_check="ask_size", checks=checks)

            # Spread validation §15 — never interpret invalid quotes as zero spread
            if intent.bid is not None and intent.ask is not None:
                bid, ask = D(intent.bid), D(intent.ask)
                if bid <= D(0) or ask <= D(0) or ask < bid:
                    chk("spread_valid", False, "INVALID_QUOTE: bid/ask invalid → REJECT", value=f"bid={bid} ask={ask}")
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INVALID_QUOTE", failed_check="spread_valid", checks=checks)
                mid = (bid + ask) / D(2)
                spread_pct = ((ask - bid) / mid * D(100)) if mid > 0 else D(999)
                if max_spread is not None:
                    if not chk("max_spread", spread_pct <= D(max_spread), f"SPREAD_TOO_WIDE {spread_pct:.2f}% > {max_spread}%", value=str(spread_pct), threshold=str(max_spread)):
                        return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="SPREAD_TOO_WIDE", failed_check="max_spread", checks=checks)
                # also check explicit intent spread_pct
                if intent.spread_pct is not None and max_spread is not None:
                    if D(intent.spread_pct) > D(max_spread):
                        return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="SPREAD_TOO_WIDE", failed_check="max_spread", checks=checks)

            # Slippage
            if max_slippage is not None and intent.slippage_pct is not None:
                if not chk("slippage", D(intent.slippage_pct) <= D(max_slippage), f"SLIPPAGE_EXCEEDED {intent.slippage_pct} > {max_slippage}"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="SLIPPAGE_TOO_HIGH", failed_check="slippage", checks=checks)

            # Greeks validation §15 — never substitute zero
            if intent.greeks is not None:
                for g_name in ("delta","gamma","theta","vega","iv"):
                    gv = intent.greeks.get(g_name)
                    if gv is None:
                        continue
                    try:
                        dv = D(gv)
                        if dv.is_nan() or not dv.is_finite():
                            chk("greeks_valid", False, f"INVALID_GREEK {g_name}=NaN/infinite")
                            return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INVALID_GREEKS", failed_check="greeks_valid", checks=checks)
                    except Exception:
                        chk("greeks_valid", False, f"INVALID_GREEK {g_name}")
                        return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INVALID_GREEKS", failed_check="greeks_valid", checks=checks)
                # IV null → reject new entries
                if intent.greeks.get("iv") is None and intent.greeks.get("iv_required"):
                    return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="INVALID_IV", failed_check="greeks_valid", checks=checks)

            # All passed
            chk("all_trade_checks", True, "ALL_TRADE_CHECKS_PASSED")
            return RiskDecision(stage="TRADE_RISK", result="APPROVED", checks=checks)

        except Exception as e:
            # Fail-closed §88.34
            logger.error("trade_risk_engine_failure", error=str(e))
            return RiskDecision(stage="TRADE_RISK", result="REJECTED", reason="RISK_ENGINE_FAILURE", failed_check="engine_error", checks=checks + [RiskCheck(name="engine_error", passed=False, reason=str(e))])


# ============================================================
# Portfolio Risk Engine — §34-43
# ============================================================

@dataclass
class PortfolioExposure:
    gross_exposure: Decimal = D(0)
    net_exposure: Decimal = D(0)
    long_exposure: Decimal = D(0)
    short_exposure: Decimal = D(0)
    margin_utilization_pct: Decimal = D(0)
    capital_utilization_pct: Decimal = D(0)
    # Greeks
    portfolio_delta: Decimal = D(0)
    portfolio_gamma: Decimal = D(0)
    portfolio_theta: Decimal = D(0)
    portfolio_vega: Decimal = D(0)
    # breakdowns
    by_underlying: dict[str, Decimal] = field(default_factory=dict)
    by_strategy: dict[str, Decimal] = field(default_factory=dict)
    by_expiry: dict[str, Decimal] = field(default_factory=dict)


@dataclass
class PortfolioRiskInput:
    existing_exposure: PortfolioExposure
    new_order_notional: Decimal
    new_order_margin: Decimal
    new_order_greeks: dict | None = None
    new_order_underlying: str | None = None
    new_order_strategy: str | None = None
    new_order_expiry: str | None = None
    limits: dict = field(default_factory=dict)
    # risk metrics
    current_var: Decimal | None = None
    incremental_var: Decimal | None = None
    stress_loss: Decimal | None = None
    correlation_risk: Decimal | None = None
    # overall
    available_margin: Decimal | None = None
    total_required_margin: Decimal | None = None


class PortfolioRiskEngine:
    """Portfolio-aware — per account (§3). Fails closed."""

    def evaluate(self, inp: PortfolioRiskInput) -> RiskDecision:
        checks: list[RiskCheck] = []
        def chk(name, passed, reason=None, value=None, threshold=None):
            checks.append(RiskCheck(name=name, passed=passed, reason=reason, value=value, threshold=threshold))
            return passed

        try:
            exp = inp.existing_exposure
            limits = inp.limits or {}
            new_notional = D(inp.new_order_notional)
            new_margin = D(inp.new_order_margin)

            # Projected exposures
            proj_gross = exp.gross_exposure + abs(new_notional)
            proj_net = exp.net_exposure + new_notional  # signed
            # need direction; simplified: assume new_notional signed already? treat as additive gross for check

            # Gross / net limits §35
            gross_limit = limits.get("portfolio_gross_exposure_limit")
            net_limit = limits.get("portfolio_net_exposure_limit")
            if gross_limit is not None:
                if not chk("gross_exposure", proj_gross <= D(gross_limit), f"GROSS_EXPOSURE_BREACH {proj_gross} > {gross_limit}", value=str(proj_gross), threshold=str(gross_limit)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="GROSS_EXPOSURE_BREACH", failed_check="gross_exposure", checks=checks)
            if net_limit is not None:
                if not chk("net_exposure", abs(proj_net) <= D(net_limit), f"NET_EXPOSURE_BREACH {proj_net} > {net_limit}", value=str(proj_net), threshold=str(net_limit)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="NET_EXPOSURE_BREACH", failed_check="net_exposure", checks=checks)

            # Margin utilization §40
            margin_limit_pct = limits.get("portfolio_margin_limit_pct")
            if margin_limit_pct is not None and inp.available_margin is not None and inp.total_required_margin is not None:
                total_margin = D(inp.total_required_margin) + new_margin
                avail = D(inp.available_margin)
                # utilization = total_margin / (total_margin+avail) ... simplified: total_margin / capital_limit
                # Use passed margin_utilization_pct from snapshot if available, else compute
                # Compute projected utilization against limit
                proj_margin_util = (total_margin / (total_margin + avail) * D(100)) if (total_margin+avail) > 0 else D(0)
                # Alternative: compare total_margin against capital * margin_limit
                if not chk("margin_utilization", proj_margin_util <= D(margin_limit_pct), f"MARGIN_BREACH {proj_margin_util:.1f}% > {margin_limit_pct}%", value=str(proj_margin_util), threshold=str(margin_limit_pct)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="MARGIN_BREACH", failed_check="margin_utilization", checks=checks)

            # Concentration §39
            # Single underlying, strategy, expiry
            for conc_key, label in [
                ("underlying_concentration_pct", "UNDERLYING_CONCENTRATION"),
                ("strategy_concentration_pct", "STRATEGY_CONCENTRATION"),
                ("expiry_concentration_pct", "EXPIRY_CONCENTRATION"),
            ]:
                conc_limit = limits.get(conc_key)
                if conc_limit is None:
                    continue
                # For new order, check its contribution vs gross
                if proj_gross > D(0):
                    new_pct = (abs(new_notional) / proj_gross * D(100))
                    # Plus existing bucket — use by_* maps
                    bucket_map = {}
                    if "underlying" in conc_key:
                        bucket_map = exp.by_underlying
                        key = inp.new_order_underlying
                    elif "strategy" in conc_key:
                        bucket_map = exp.by_strategy
                        key = inp.new_order_strategy
                    else:
                        bucket_map = exp.by_expiry
                        key = inp.new_order_expiry
                    if key and key in bucket_map:
                        bucket_existing = D(bucket_map[key])
                        combined = bucket_existing + abs(new_notional)
                        combined_pct = combined / proj_gross * D(100)
                        if not chk(f"concentration_{label}", combined_pct <= D(conc_limit), f"{label}_BREACH {combined_pct:.1f}% > {conc_limit}% for {key}", value=str(combined_pct), threshold=str(conc_limit)):
                            return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason=f"{label}_BREACH", failed_check=f"concentration_{label}", checks=checks)
                    else:
                        # new bucket
                        if not chk(f"concentration_{label}", new_pct <= D(conc_limit), f"{label}_BREACH {new_pct:.1f}% > {conc_limit}%", value=str(new_pct), threshold=str(conc_limit)):
                            return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason=f"{label}_BREACH", failed_check=f"concentration_{label}", checks=checks)

            # Greeks aggregation §38 — don't assume delta hedge removes gamma/vega
            if inp.new_order_greeks:
                proj_delta = exp.portfolio_delta + D(inp.new_order_greeks.get("delta", 0))
                proj_gamma = exp.portfolio_gamma + D(inp.new_order_greeks.get("gamma", 0))
                proj_theta = exp.portfolio_theta + D(inp.new_order_greeks.get("theta", 0))
                proj_vega = exp.portfolio_vega + D(inp.new_order_greeks.get("vega", 0))
                for name, proj, limit_key, code in [
                    ("delta", proj_delta, "portfolio_delta_limit", "DELTA_BREACH"),
                    ("gamma", proj_gamma, "portfolio_gamma_limit", "GAMMA_BREACH"),
                    ("vega", proj_vega, "portfolio_vega_limit", "VEGA_BREACH"),
                ]:
                    lim = limits.get(limit_key)
                    if lim is not None and lim != "" and D(lim) != D(0):
                        if not chk(f"greek_{name}", abs(proj) <= abs(D(lim)), f"GREEK_{code} {proj} > {lim}", value=str(proj), threshold=str(lim)):
                            return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason=code, failed_check=f"greek_{name}", checks=checks)
                # Also always evaluate vega even if delta hedged — speculative alert but not breach unless limit

            # VaR / Stress §41-42 — where model/data quality permits
            var_limit = limits.get("portfolio_var_limit")
            if var_limit is not None and inp.current_var is not None:
                proj_var = D(inp.current_var) + D(inp.incremental_var or 0)
                if not chk("var_limit", proj_var <= D(var_limit), f"VAR_BREACH {proj_var} > {var_limit}", value=str(proj_var), threshold=str(var_limit)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="VAR_BREACH", failed_check="var_limit", checks=checks)
            stress_limit = limits.get("portfolio_stress_limit")
            if stress_limit is not None and inp.stress_loss is not None:
                if not chk("stress_limit", D(inp.stress_loss) <= D(stress_limit), f"STRESS_BREACH {inp.stress_loss} > {stress_limit}", value=str(inp.stress_loss), threshold=str(stress_limit)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="STRESS_BREACH", failed_check="stress_limit", checks=checks)

            # Correlation — never treat missing as zero (§36)
            corr_conf = limits.get("correlation_confidence")
            if corr_conf == "LOW":
                chk("correlation_confidence", True, "CORRELATION_CONFIDENCE_LOW — using conservative fallback")
                # conservative fallback already applied by caller via inflated exposure; we just warn

            # Also need to consider correlated exposure across strategies for same underlying
            # Example §37: if existing NIFTY exposure high, new NIFTY order triggers extra check
            # Already covered via concentration; additional correlation breach check placeholder
            # (full correlation matrix would be model-based)

            chk("all_portfolio_checks", True, "ALL_PORTFOLIO_CHECKS_PASSED")
            return RiskDecision(stage="PORTFOLIO_RISK", result="APPROVED", checks=checks)

        except Exception as e:
            logger.error("portfolio_risk_engine_failure", error=str(e))
            return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="PORTFOLIO_RISK_ENGINE_FAILURE", failed_check="engine_error", checks=checks + [RiskCheck(name="engine_error", passed=False, reason=str(e))])

    def portfolio_state(self, exp: PortfolioExposure, limits: dict) -> PortfolioState:
        """Derive §43 state."""
        # Check breaches in order
        if limits.get("portfolio_gross_exposure_limit") and exp.gross_exposure >= D(limits["portfolio_gross_exposure_limit"]):
            return "LIMIT_BREACHED"
        if limits.get("portfolio_margin_limit_pct") and exp.margin_utilization_pct >= D(limits["portfolio_margin_limit_pct"]):
            return "MARGIN_BREACH"
        # etc simplified
        if exp.margin_utilization_pct > D(70) or exp.gross_exposure > D(limits.get("portfolio_gross_exposure_limit", 999999999)) * D("0.8"):
            return "WARNING"
        return "NORMAL"


trade_risk_engine = TradeRiskEngine()
portfolio_risk_engine = PortfolioRiskEngine()
