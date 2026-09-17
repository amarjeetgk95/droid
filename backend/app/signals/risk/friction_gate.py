"""
Net Edge & Friction Gate (§27, §28).
Fail-closed: no trade passes without a LIVE premium, a LIVE per-strike spread
and a per-strike IV (selector greeks). Fabrications removed:
  - no spot*0.008 premium guess
  - no 0.50 default delta
  - no static 1/3/5 spread table
Holding time comes from the expected-move projection duration (real holding
clock), never from max TTL. Thresholds: netRR>=1.2, cost<=30%.
Math delegates to the single canonical schedule (IndianOptionCosts /
compute_option_friction_r in transaction_costs + path_simulator).

Rejection Code: REJECT_FRICTION / REJECT_NET_EDGE
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.signals.strategies.base import SignalCandidate


class NetEdgeResult(BaseModel):
    passed: bool
    expected_gross_edge_pts: float
    total_friction_pts: float
    expected_net_edge_pts: float
    cost_to_target_ratio_pct: float
    net_reward_risk_ratio: float
    rejection_reason: Optional[str] = None
    breakdown: dict[str, float] = Field(default_factory=dict)
    # P1 audit provenance.
    premium_source: str = "unknown"
    spread_source: str = "unknown"
    delta_source: str = "unknown"
    holding_seconds: int = 0


def _resolve_live_premium(
    candidate: SignalCandidate,
    live_premium: Optional[float],
    estimated_premium: Optional[float],
) -> tuple[Optional[float], str]:
    """LIVE premium only. estimated_premium is accepted as an explicit caller
    quote (backward compat) but never fabricated from spot."""
    for val, src in ((live_premium, "live_arg"), (estimated_premium, "explicit_arg")):
        try:
            if val is not None and float(val) > 0:
                return float(val), src
        except Exception:
            pass
    # Chain mark on the resolved contract.
    try:
        opt = getattr(candidate, "option_contract", None)
        sym = None
        if isinstance(opt, dict):
            sym = opt.get("broker_symbol")
            lp = opt.get("live_premium")
            if lp is not None and float(lp) > 0:
                return float(lp), "contract_live_premium"
        else:
            sym = getattr(opt, "broker_symbol", None)
            lp = getattr(opt, "live_premium", None)
            if lp is not None and float(lp) > 0:
                return float(lp), "contract_live_premium"
        if sym:
            from app.signals.option_marks import option_mark_registry
            mark = option_mark_registry.get_usable(str(sym), allow_model=False)
            if mark is not None and mark.price and mark.price > 0:
                return float(mark.price), "chain_mark"
    except Exception:
        pass
    return None, "missing"


def _resolve_live_spread(
    candidate: SignalCandidate,
    spread_pts: Optional[float],
) -> tuple[Optional[float], str]:
    if spread_pts is not None:
        try:
            if float(spread_pts) > 0:
                return float(spread_pts), "live_arg"
        except Exception:
            pass
    try:
        opt = getattr(candidate, "option_contract", None)
        sym = opt.get("broker_symbol") if isinstance(opt, dict) else getattr(opt, "broker_symbol", None)
        if sym:
            from app.signals.option_marks import option_mark_registry
            mark = option_mark_registry.get(str(sym))
            if mark is not None and getattr(mark, "spread_pts", None):
                sp = float(mark.spread_pts)  # type: ignore[arg-type]
                if sp > 0:
                    return sp, "chain_mark"
            # Chain cache bid/ask fallback.
            from app.signals.live_contract_cache import live_contract_cache
            info = live_contract_cache.find_by_symbol(str(sym))
            if info is not None and info.bid > 0 and info.ask > info.bid:
                return round(float(info.ask) - float(info.bid), 2), "chain_bidask"
    except Exception:
        pass
    return None, "missing"


def _resolve_delta(
    candidate: SignalCandidate,
    live_iv: Optional[float],
) -> tuple[Optional[float], str]:
    try:
        g = getattr(candidate, "greeks", None) or {}
        if isinstance(g, dict) and g.get("delta") is not None:
            d = abs(float(g["delta"]))
            if d > 0:
                return d, "selector_greeks"
        elif hasattr(g, "delta"):
            d = abs(float(getattr(g, "delta")))
            if d > 0:
                return d, "selector_greeks"
    except Exception:
        pass
    # Derive from live IV when the contract geometry is known.
    try:
        if live_iv is not None and float(live_iv) > 0:
            opt = getattr(candidate, "option_contract", None)
            strike = None
            otype = "CE" if "CALL" in str(getattr(candidate, "direction", "")) else "PE"
            if isinstance(opt, dict):
                strike = opt.get("strike")
                if opt.get("option_type"):
                    otype = str(opt.get("option_type"))
            else:
                strike = getattr(opt, "strike", None)
            spot = float(getattr(candidate, "spot_price", 0) or 0)
            if strike and spot > 0:
                from app.signals.options_intelligence.greeks import BlackScholesGreeks
                gr = BlackScholesGreeks.calculate_greeks(spot, float(strike), 3.0 / 365.0, float(live_iv), otype)  # type: ignore[arg-type]
                return abs(float(gr.delta)), "derived_live_iv"
    except Exception:
        pass
    return None, "missing"


def _resolve_holding_seconds(
    candidate: SignalCandidate,
    expected_holding_seconds: Optional[int],
    expected_move_projection: Optional[Any],
) -> tuple[int, str]:
    # 1. Expected-move projection duration (real holding clock).
    try:
        if expected_move_projection is not None:
            for attr in ("duration_seconds", "duration", "expected_duration_hours"):
                v = getattr(expected_move_projection, attr, None)
                if callable(v):
                    v = v()
                if v is not None and float(v) > 0:
                    secs = int(float(v) * 3600) if "hour" in attr or attr == "duration" else int(float(v))
                    if secs > 0:
                        return secs, "expected_move_projection"
            if isinstance(expected_move_projection, dict):
                for k in ("duration_seconds", "expected_duration_hours"):
                    if expected_move_projection.get(k):
                        v = float(expected_move_projection[k])
                        secs = int(v * 3600) if "hour" in k else int(v)
                        if secs > 0:
                            return secs, "expected_move_projection"
    except Exception:
        pass
    # 2. Explicit arg / active time-stop (holding clock), never trigger TTL.
    if expected_holding_seconds and expected_holding_seconds > 0:
        return int(expected_holding_seconds), "explicit_arg"
    try:
        ts = getattr(candidate, "time_stop_seconds", None)
        if ts and int(ts) > 0:
            return int(ts), "time_stop"
    except Exception:
        pass
    return 0, "missing"


class FrictionGate:
    """
    Evaluates net profitability after statutory charges, slippage, and spread.
    Fail-closed: missing live premium / spread / delta / holding => REJECT.
    """

    def __init__(
        self,
        min_net_reward_risk: float = 1.2,
        max_cost_to_target_ratio: float = 0.30,  # Max 30% of gross target eaten by costs
        default_nifty_lot: int = 75,
        default_banknifty_lot: int = 30,
        default_sensex_lot: int = 10,
    ):
        self.min_net_reward_risk = min_net_reward_risk
        self.max_cost_to_target_ratio = max_cost_to_target_ratio
        self.lot_sizes = {
            "NIFTY": default_nifty_lot,
            "BANKNIFTY": default_banknifty_lot,
            "SENSEX": default_sensex_lot,
        }

    def _lot_size_for(self, underlying: str) -> int:
        try:
            from app.signals.transaction_costs import resolve_lot_size_for_underlying
            return resolve_lot_size_for_underlying(underlying)
        except Exception:
            return self.lot_sizes.get(underlying, 75)

    def evaluate(
        self,
        candidate: SignalCandidate,
        estimated_premium: Optional[float] = None,
        spread_pts: Optional[float] = None,
        slippage_pct: float = 0.002,
        expected_holding_seconds: Optional[int] = None,
        live_premium: Optional[float] = None,
        live_spread_pts: Optional[float] = None,
        live_iv: Optional[float] = None,
        slippage_pts: Optional[float] = None,
        expected_move_projection: Optional[Any] = None,
    ) -> NetEdgeResult:
        u = candidate.underlying
        lot_size = self._lot_size_for(u)

        # ── Fail-closed live inputs ──
        premium, prem_src = _resolve_live_premium(candidate, live_premium, estimated_premium)
        if premium is None:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=0.0, total_friction_pts=0.0,
                expected_net_edge_pts=0.0, cost_to_target_ratio_pct=100.0,
                net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_LIVE_PREMIUM: live option premium required (no spot*0.008 fabrication)",
                breakdown={}, premium_source="missing", spread_source="missing",
                delta_source="missing", holding_seconds=0,
            )
        live_spread, spread_src = _resolve_live_spread(candidate, live_spread_pts if live_spread_pts is not None else spread_pts)
        if live_spread is None:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=0.0, total_friction_pts=0.0,
                expected_net_edge_pts=0.0, cost_to_target_ratio_pct=100.0,
                net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_LIVE_SPREAD: per-strike live spread required (no static 1/3/5 fallback)",
                breakdown={}, premium_source=prem_src, spread_source="missing",
                delta_source="missing", holding_seconds=0,
            )
        # Per-strike IV provenance: explicit live_iv > selector greeks iv > fail.
        eff_iv = live_iv
        try:
            g = getattr(candidate, "greeks", None) or {}
            giv = g.get("iv") if isinstance(g, dict) else getattr(g, "iv", None)
            if (eff_iv is None or float(eff_iv) <= 0) and giv and float(giv) > 0:
                eff_iv = float(giv)
        except Exception:
            pass
        if eff_iv is None or float(eff_iv) <= 0:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=0.0, total_friction_pts=0.0,
                expected_net_edge_pts=0.0, cost_to_target_ratio_pct=100.0,
                net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_LIVE_IV: per-strike IV required (no 15% default)",
                breakdown={}, premium_source=prem_src, spread_source=spread_src,
                delta_source="missing", holding_seconds=0,
            )
        delta, delta_src = _resolve_delta(candidate, float(eff_iv))
        if delta is None:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=0.0, total_friction_pts=0.0,
                expected_net_edge_pts=0.0, cost_to_target_ratio_pct=100.0,
                net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_DELTA: selector delta required (no 0.50 default)",
                breakdown={}, premium_source=prem_src, spread_source=spread_src,
                delta_source="missing", holding_seconds=0,
            )
        holding_sec, _hold_src = _resolve_holding_seconds(candidate, expected_holding_seconds, expected_move_projection)
        if holding_sec <= 0:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=0.0, total_friction_pts=0.0,
                expected_net_edge_pts=0.0, cost_to_target_ratio_pct=100.0,
                net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_HOLDING_CLOCK: expected-move duration or time-stop required (never TTL)",
                breakdown={}, premium_source=prem_src, spread_source=spread_src,
                delta_source=delta_src, holding_seconds=0,
            )

        # Spot risk and target points
        spot_risk = float(candidate.risk_points)
        spot_target = float(candidate.target_1 - candidate.trigger) if candidate.direction == "LONG_CALL" else float(candidate.trigger - candidate.target_1)
        spot_target = max(0.1, spot_target)

        # Projected Option Points Move (live delta)
        gross_option_target_pts = spot_target * delta
        gross_option_risk_pts = spot_risk * delta

        # Single-schedule friction math (canonical IndianOptionCosts).
        from app.signals.options_intelligence.path_simulator import IndianOptionCosts
        costs = IndianOptionCosts()
        slip_pts = float(slippage_pts) if slippage_pts is not None and float(slippage_pts) >= 0 else round(premium * float(slippage_pct), 2)
        exit_premium = premium + gross_option_target_pts
        friction_map = costs.calculate_total_costs(
            entry_premium=premium,
            exit_premium=exit_premium,
            quantity=lot_size,
            spread_pts=float(live_spread),
            slippage_pts=slip_pts,
        )
        statutory_points = (friction_map.get("statutory_taxes", 0.0)) / lot_size

        # Theta Decay Drag over the REAL holding clock.
        theta_drag_pts = 0.0
        try:
            g = getattr(candidate, "greeks", None) or {}
            th = g.get("theta_hour", g.get("theta")) if isinstance(g, dict) else getattr(g, "theta_hour", None)
            if th is not None:
                theta_drag_pts = abs(float(th)) * (holding_sec / 3600.0)
            else:
                # Derive from live IV geometry when theta is absent.
                from app.signals.options_intelligence.greeks import BlackScholesGreeks
                opt = getattr(candidate, "option_contract", None)
                strike = opt.get("strike") if isinstance(opt, dict) else getattr(opt, "strike", None)
                otype = "CE" if "CALL" in str(candidate.direction) else "PE"
                if strike and float(getattr(candidate, "spot_price", 0) or 0) > 0:
                    gr = BlackScholesGreeks.calculate_greeks(
                        float(candidate.spot_price), float(strike), 3.0 / 365.0, float(eff_iv), otype,  # type: ignore[arg-type]
                    )
                    theta_drag_pts = abs(float(gr.theta_hour)) * (holding_sec / 3600.0)
        except Exception:
            theta_drag_pts = 0.0
        if theta_drag_pts <= 0:
            return NetEdgeResult(
                passed=False, expected_gross_edge_pts=round(gross_option_target_pts, 2),
                total_friction_pts=0.0, expected_net_edge_pts=0.0,
                cost_to_target_ratio_pct=100.0, net_reward_risk_ratio=0.0,
                rejection_reason="REJECT_NO_THETA_CLOCK: theta/hour required to price holding decay",
                breakdown={}, premium_source=prem_src, spread_source=spread_src,
                delta_source=delta_src, holding_seconds=holding_sec,
            )

        # Total friction (option premium points): statutory + market
        # (spread+slip already inside market_friction) + theta over the real clock.
        total_friction_pts = (friction_map.get("total_friction", 0.0) / lot_size) + theta_drag_pts

        # Expected Net Edge (Option points)
        net_edge_pts = gross_option_target_pts - total_friction_pts

        # Ratios (tightened: netRR>=1.2, cost<=30%)
        cost_ratio = (total_friction_pts / gross_option_target_pts) if gross_option_target_pts > 0 else 1.0
        net_reward_risk = (net_edge_pts / (gross_option_risk_pts + total_friction_pts)) if (gross_option_risk_pts + total_friction_pts) > 0 else 0.0

        rejection: Optional[str] = None
        if net_edge_pts <= 0:
            rejection = f"REJECT_NET_EDGE: Total friction ({total_friction_pts:.2f} pts) exceeds gross expected move ({gross_option_target_pts:.2f} pts)"
        elif cost_ratio > self.max_cost_to_target_ratio:
            rejection = f"REJECT_FRICTION: Friction consumes {cost_ratio * 100.0:.1f}% of target (max allowed: {self.max_cost_to_target_ratio * 100.0:.1f}%)"
        elif net_reward_risk < self.min_net_reward_risk:
            rejection = f"REJECT_POOR_NET_RR: Net R/R ({net_reward_risk:.2f}) is below minimum threshold ({self.min_net_reward_risk:.2f})"

        passed = (rejection is None)

        return NetEdgeResult(
            passed=passed,
            expected_gross_edge_pts=round(gross_option_target_pts, 2),
            total_friction_pts=round(total_friction_pts, 2),
            expected_net_edge_pts=round(net_edge_pts, 2),
            cost_to_target_ratio_pct=round(cost_ratio * 100.0, 1),
            net_reward_risk_ratio=round(net_reward_risk, 2),
            rejection_reason=rejection,
            breakdown={
                "spread_pts": round(float(live_spread), 2),
                "statutory_charges_rupees": round(friction_map.get("statutory_taxes", 0.0), 2),
                "statutory_pts": round(statutory_points, 2),
                "market_friction_rupees": round(friction_map.get("market_friction_rupees", 0.0), 2),
                "theta_decay_drag_pts": round(theta_drag_pts, 2),
                "slippage_pts": round(slip_pts, 2),
                "live_iv": round(float(eff_iv), 4),
                "holding_seconds": float(holding_sec),
            },
            premium_source=prem_src,
            spread_source=spread_src,
            delta_source=delta_src,
            holding_seconds=holding_sec,
        )


friction_gate = FrictionGate()
