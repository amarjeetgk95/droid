"""
Portfolio-Level Risk — §§51,52,53
Risk across NIFTY, BANKNIFTY, SENSEX, BTCUSD
Gross/net exposure, concentration, correlated equity exposure, margin, daily loss, drawdown,
max concurrent trades, stress scenarios, existing orders, pending executions.
Separate cross-asset model for BTCUSD vs correlated NIFTY family.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.algo.money import D
from app.algo.risk import RiskDecision, RiskCheck

RiskResult = Literal["APPROVED", "REJECTED"]


@dataclass
class PositionExposure:
    instrument_id: str
    notional: Decimal  # signed
    margin: Decimal
    quantity: int = 0


@dataclass
class PortfolioState:
    positions: list[PositionExposure] = field(default_factory=list)
    pending_orders: list[PositionExposure] = field(default_factory=list)  # pending executions
    total_gross_notional: Decimal = field(default_factory=lambda: D(0))
    total_net_notional: Decimal = field(default_factory=lambda: D(0))
    margin_used: Decimal = field(default_factory=lambda: D(0))
    daily_loss: Decimal = field(default_factory=lambda: D(0))
    drawdown_pct: Decimal = field(default_factory=lambda: D(0))
    concurrent_trades: int = 0

    def compute(self) -> None:
        gross = D(0)
        net = D(0)
        margin = D(0)
        for p in self.positions:
            gross += abs(p.notional)
            net += p.notional
            margin += p.margin
        for o in self.pending_orders:
            gross += abs(o.notional)
            net += o.notional
            margin += o.margin
        self.total_gross_notional = gross
        self.total_net_notional = net
        self.margin_used = margin


@dataclass
class PortfolioRiskInput:
    new_order_instrument: str
    new_order_notional: Decimal
    new_order_margin: Decimal
    side: Literal["BUY", "SELL"] = "BUY"
    portfolio: PortfolioState | None = None
    limits: dict = field(default_factory=dict)
    # Strategy-specific
    new_order_strategy: str | None = None
    new_order_underlying: str | None = None


class InstitutionalPortfolioRiskEngine:
    """
    Final authority before execution (§53). Even if MI=bullish, AI=confirmed, strategy=confirmed,
    risk may still RISK_REJECTED and no component may override (§53).
    Individual strategy approval does not guarantee portfolio approval (§79 Portfolio Integrity).
    """

    # Correlation groups — NIFTY family treated as overlapping (§52)
    CORRELATED_GROUPS: dict[str, list[str]] = {
        "INDIAN_EQUITY": ["NIFTY", "BANKNIFTY", "SENSEX"],
        "CRYPTO": ["BTCUSD", "BTC"],
    }

    def _group_for(self, instrument_id: str) -> str | None:
        iid = instrument_id.upper()
        for g, members in self.CORRELATED_GROUPS.items():
            if iid in [m.upper() for m in members]:
                return g
        return None

    def evaluate(self, inp: PortfolioRiskInput) -> RiskDecision:
        checks: list[RiskCheck] = []
        def chk(name, passed, reason=None, value=None, thr=None):
            checks.append(RiskCheck(name=name, passed=passed, reason=reason, value=value, threshold=thr))
            return passed
        try:
            portfolio = inp.portfolio or PortfolioState()
            portfolio.compute()
            limits = inp.limits or {}

            new_notional = D(inp.new_order_notional)
            new_margin = D(inp.new_order_margin)
            # Signed notional based on side
            signed_new = new_notional if inp.side == "BUY" else -new_notional

            # Projected
            proj_gross = portfolio.total_gross_notional + abs(new_notional)
            proj_net = portfolio.total_net_notional + signed_new
            proj_margin = portfolio.margin_used + new_margin

            # Gross / net limits (§51)
            gross_lim = limits.get("gross_exposure_limit")
            net_lim = limits.get("net_exposure_limit")
            if gross_lim is not None:
                if not chk("gross_exposure", proj_gross <= D(gross_lim), f"GROSS_EXPOSURE_BREACH {proj_gross} > {gross_lim}", str(proj_gross), str(gross_lim)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="GROSS_EXPOSURE_BREACH", failed_check="gross_exposure", checks=checks)
            if net_lim is not None:
                if not chk("net_exposure", abs(proj_net) <= D(net_lim), f"NET_EXPOSURE_BREACH {proj_net} > {net_lim}", str(proj_net), str(net_lim)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="NET_EXPOSURE_BREACH", failed_check="net_exposure", checks=checks)

            # Directional concentration / correlated exposure (§52)
            # Do NOT treat NIFTY/BANKNIFTY/SENSEX as fully independent
            group = self._group_for(inp.new_order_instrument)
            if group == "INDIAN_EQUITY":
                # Sum exposure of all Indian equity positions
                indian_gross = D(0)
                for p in portfolio.positions:
                    if self._group_for(p.instrument_id) == "INDIAN_EQUITY":
                        indian_gross += abs(p.notional)
                indian_gross += abs(new_notional)
                corr_limit = limits.get("indian_equity_correlated_limit")
                if corr_limit is not None:
                    if not chk("correlated_equity_exposure", indian_gross <= D(corr_limit), f"CORRELATED_EXPOSURE_BREACH indian equity {indian_gross} > {corr_limit}", str(indian_gross), str(corr_limit)):
                        return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="CORRELATED_EXPOSURE_BREACH", failed_check="correlated_equity_exposure", checks=checks)
            # BTCUSD separate model unless validated correlation rules explicitly configured
            if group == "CRYPTO":
                btc_lim = limits.get("crypto_exposure_limit")
                if btc_lim is not None:
                    btc_gross = sum(abs(p.notional) for p in portfolio.positions if self._group_for(p.instrument_id) == "CRYPTO") + abs(new_notional)
                    if not chk("crypto_exposure", D(btc_gross) <= D(btc_lim), f"CRYPTO_EXPOSURE_BREACH {btc_gross} > {btc_lim}", str(btc_gross), str(btc_lim)):
                        return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="CRYPTO_EXPOSURE_BREACH", failed_check="crypto_exposure", checks=checks)

            # Concentration — instrument / strategy (§51)
            instr_conc_pct = limits.get("instrument_concentration_pct")
            if instr_conc_pct is not None and proj_gross > D(0):
                same_instr_total = sum(abs(p.notional) for p in portfolio.positions if p.instrument_id.upper() == inp.new_order_instrument.upper()) + abs(new_notional)
                conc_pct = same_instr_total / proj_gross * D(100)
                if not chk("instrument_concentration", conc_pct <= D(instr_conc_pct), f"INSTRUMENT_CONCENTRATION_BREACH {conc_pct:.1f}% > {instr_conc_pct}%", str(conc_pct), str(instr_conc_pct)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="INSTRUMENT_CONCENTRATION_BREACH", failed_check="instrument_concentration", checks=checks)

            # Margin
            margin_limit_pct = limits.get("margin_limit_pct")
            # Compare proj_margin vs capital * margin_limit
            capital = limits.get("total_capital")
            if margin_limit_pct is not None and capital is not None and D(capital) > D(0):
                proj_margin_pct = proj_margin / D(capital) * D(100)
                if not chk("margin_limit", proj_margin_pct <= D(margin_limit_pct), f"MARGIN_BREACH {proj_margin_pct:.1f}% > {margin_limit_pct}%", str(proj_margin_pct), str(margin_limit_pct)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="MARGIN_BREACH", failed_check="margin_limit", checks=checks)

            # Daily loss / drawdown
            daily_loss_lim = limits.get("daily_loss_limit")
            if daily_loss_lim is not None and portfolio.daily_loss is not None:
                if not chk("daily_loss", portfolio.daily_loss > -D(daily_loss_lim), f"DAILY_LOSS_BREACH {portfolio.daily_loss} limit {daily_loss_lim}", str(portfolio.daily_loss), str(daily_loss_lim)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="DAILY_LOSS_BREACH", failed_check="daily_loss", checks=checks)
            drawdown_lim = limits.get("drawdown_limit_pct")
            if drawdown_lim is not None and portfolio.drawdown_pct is not None:
                if not chk("drawdown", portfolio.drawdown_pct <= D(drawdown_lim), f"DRAWDOWN_BREACH {portfolio.drawdown_pct}% > {drawdown_lim}%", str(portfolio.drawdown_pct), str(drawdown_lim)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="DRAWDOWN_BREACH", failed_check="drawdown", checks=checks)

            # Max concurrent trades
            max_conc = limits.get("max_concurrent_trades")
            if max_conc is not None:
                proj_conc = portfolio.concurrent_trades + 1
                if not chk("max_concurrent_trades", proj_conc <= int(max_conc), f"MAX_CONCURRENT_TRADES {proj_conc} > {max_conc}", proj_conc, max_conc):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="MAX_CONCURRENT_TRADES_BREACH", failed_check="max_concurrent_trades", checks=checks)

            # Stress scenarios (placeholder)
            stress_lim = limits.get("stress_loss_limit")
            if stress_lim is not None:
                stress_loss = D(new_notional) * D("0.05")  # simplistic 5% stress
                if not chk("stress_scenario", stress_loss <= D(stress_lim), f"STRESS_BREACH {stress_loss} > {stress_lim}", str(stress_loss), str(stress_lim)):
                    return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="STRESS_BREACH", failed_check="stress_scenario", checks=checks)

            # Existing orders / pending executions already included via portfolio.pending_orders summed into proj_*

            chk("all_portfolio_checks", True, "ALL_PORTFOLIO_CHECKS_PASSED")
            return RiskDecision(stage="PORTFOLIO_RISK", result="APPROVED", checks=checks)
        except Exception as e:
            checks.append(RiskCheck(name="engine_error", passed=False, reason=str(e)))
            return RiskDecision(stage="PORTFOLIO_RISK", result="REJECTED", reason="PORTFOLIO_RISK_ENGINE_FAILURE", failed_check="engine_error", checks=checks)


institutional_portfolio_engine = InstitutionalPortfolioRiskEngine()
