"""
Cross-Desk Inventory Arbiter (§31, §51).
Prevents inventory cannibalization and portfolio risk inflation when Scalp and Intraday desks
generate opposing or simultaneous signals on the same underlying.

P1: iterates ALL same-underlying trades (never first-only), maps PositionState
(OPEN/T1_PARTIAL_EXIT/…) alongside signal FSM states, applies a cross-index
beta haircut for correlated books, and consults the portfolio Greeks ledger
veto before ALLOW.

Governed by the Deterministic State Priority Matrix:
  - Intraday FLAT: Allow all valid scalps.
  - Intraday IN PROFIT (>1R):
      - Same direction: ALLOW (pyramiding within risk limits).
      - Opposing direction: HARVEST_WARNING (tighten intraday stop to breakeven or partial scale-out).
  - Intraday IN DRAWDOWN (<0):
      - Same direction: ALLOW if within overall desk risk envelope.
      - Opposing direction: HARD SUPPRESS (never trade against an already stressed intraday trade).
"""
from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field

ArbiterAction = Literal["ALLOW", "SUPPRESS", "HARVEST_WARNING", "REDUCE_SIZE"]

ACTIVE_SIGNAL_STATES = frozenset({"CONFIRMED", "TARGET_1_HIT", "ACTIVE", "PARTIALLY_FILLED"})
ACTIVE_POSITION_STATES = frozenset({"OPEN", "T1_PARTIAL_EXIT", "PARTIALLY_FILLED", "ASSIGNED"})

# Same-family beta: NIFTY/BANKNIFTY/SENSEX move together — a live book on a
# sibling index is not diversification.
INDEX_FAMILY = frozenset({"NIFTY", "BANKNIFTY", "SENSEX"})
CROSS_INDEX_BETA_HAIRCUT = 0.70


def _is_active_trade(t: Any) -> bool:
    try:
        st = str(getattr(t, "fsm_state", "") or getattr(t, "position_state", "") or "").upper()
        if not st:
            ps = getattr(t, "position_state", None)
            st = str(ps.value if hasattr(ps, "value") else ps or "").upper()
        return st in ACTIVE_SIGNAL_STATES or st in ACTIVE_POSITION_STATES
    except Exception:
        return False


def _trade_r_multiple(t: Any) -> float:
    for attr in ("r_multiple", "unrealized_r", "realized_rr", "pnl_r"):
        try:
            v = getattr(t, attr, None)
            if v is not None:
                return float(v)
        except Exception:
            continue
    return 0.0


def _is_scalp_trade(t: Any) -> bool:
    try:
        if bool(getattr(t, "is_scalp", False)):
            return True
        return str(getattr(t, "timeframe", "5M")) in ("1M", "3M")
    except Exception:
        return False


class ArbiterDecision(BaseModel):
    action: ArbiterAction = "ALLOW"
    passed: bool = True
    reason: Optional[str] = None
    suggested_intraday_action: Optional[str] = None  # e.g., "TIGHTEN_STOP_TO_BE", "SCALE_OUT_50"
    sizing_multiplier: float = 1.0


class CrossDeskArbiter:
    """
    Arbitrates execution permissions between Scalp Desk and Intraday Desk.
    """

    def arbitrate(
        self,
        candidate_is_scalp: bool,
        candidate_underlying: str,
        candidate_direction: str,
        active_trades: list[Any],
        candidate_greeks: Optional[dict[str, Any]] = None,
        candidate_quantity: Optional[int] = None,
        candidate_expiry: Optional[str] = None,
        candidate_horizon: Optional[str] = None,
    ) -> ArbiterDecision:
        """
        Evaluates candidate against ALL currently active trades on the same
        underlying (plus a beta haircut for correlated sibling indices).
        """
        # Same-underlying active book (signal FSM + PositionState mapped).
        underlying_trades = [
            t for t in (active_trades or [])
            if str(getattr(t, "underlying", "") or "") == candidate_underlying
            and _is_active_trade(t)
        ]

        # ── Portfolio ledger veto (consulted before any ALLOW) ──
        try:
            if candidate_greeks and candidate_quantity:
                from app.signals.portfolio_greeks import portfolio_greeks_ledger
                g = candidate_greeks or {}
                otype = "CE" if "CALL" in str(candidate_direction).upper() else "PE"
                strike = float(g.get("strike", 0) or 0)
                check = portfolio_greeks_ledger.evaluate_marginal_trade(
                    underlying=candidate_underlying,
                    horizon=(candidate_horizon or ("SCALP" if candidate_is_scalp else "INTRADAY")),  # type: ignore[arg-type]
                    option_type=otype,  # type: ignore[arg-type]
                    strike=strike,
                    expiry_date=str(candidate_expiry or ""),
                    quantity=int(candidate_quantity),
                    unit_delta=float(g.get("delta", 0.5) or 0.5),
                    unit_gamma=float(g.get("gamma", 0.0005) or 0.0005),
                    unit_theta_day=float(g.get("theta_day", g.get("theta", -10.0)) or -10.0),
                    unit_vega=float(g.get("vega", 10.0) or 10.0),
                )
                if not check.allowed:
                    return ArbiterDecision(
                        action="SUPPRESS", passed=False,
                        reason=f"REJECT_PORTFOLIO_VETO: {check.rejection_reason}",
                        sizing_multiplier=0.0,
                    )
        except Exception:
            pass

        # ── Cross-index beta haircut (correlated family book) ──
        beta_multiplier = 1.0
        beta_note: Optional[str] = None
        try:
            if candidate_underlying in INDEX_FAMILY:
                sib_opposing = [
                    t for t in (active_trades or [])
                    if str(getattr(t, "underlying", "") or "") in INDEX_FAMILY
                    and str(getattr(t, "underlying", "") or "") != candidate_underlying
                    and _is_active_trade(t)
                    and str(getattr(t, "direction", "") or "") != candidate_direction
                ]
                if sib_opposing:
                    beta_multiplier = CROSS_INDEX_BETA_HAIRCUT
                    beta_note = (
                        f"Cross-index beta haircut x{CROSS_INDEX_BETA_HAIRCUT}: "
                        f"{len(sib_opposing)} opposing correlated-index position(s)"
                    )
        except Exception:
            pass

        def _with_beta(dec: ArbiterDecision) -> ArbiterDecision:
            if beta_multiplier < 1.0 and dec.passed:
                dec.sizing_multiplier = round(float(dec.sizing_multiplier) * beta_multiplier, 2)
                dec.reason = f"{dec.reason or ''} | {beta_note}".strip(" |")
                if dec.action == "ALLOW" and dec.sizing_multiplier < 1.0:
                    dec.action = "REDUCE_SIZE"
            return dec

        if not underlying_trades:
            if beta_multiplier < 1.0:
                return ArbiterDecision(action="REDUCE_SIZE", passed=True, reason=beta_note, sizing_multiplier=beta_multiplier)
            return ArbiterDecision(action="ALLOW", passed=True, reason="No active trades on underlying")

        # Check if candidate is a Scalp trade while an Intraday trade exists
        if candidate_is_scalp:
            intraday_trades = [t for t in underlying_trades if not _is_scalp_trade(t)]

            if not intraday_trades:
                return _with_beta(ArbiterDecision(action="ALLOW", passed=True, reason="No active intraday trades on underlying"))

            # P1: evaluate EVERY active intraday trade — worst conflict wins,
            # never the first row in the list.
            suppress_reasons: list[str] = []
            harvest: Optional[ArbiterDecision] = None
            sizing_note = 1.0
            for it in intraday_trades:
                it_direction = getattr(it, "direction", "")
                is_same_dir = (it_direction == candidate_direction)
                r_multiple = _trade_r_multiple(it)

                # State 1: Intraday trade is in drawdown (< 0R)
                if r_multiple < 0:
                    if not is_same_dir:
                        suppress_reasons.append(
                            f"opposing scalp ({candidate_direction}) vs intraday {getattr(it, 'signal_id', '')} underwater ({r_multiple:.2f}R)"
                        )
                    else:
                        if r_multiple < -0.5:
                            sizing_note = min(sizing_note, 0.75)
                # State 2: Intraday trade is in solid profit (> 1.0R)
                elif r_multiple >= 1.0:
                    if not is_same_dir:
                        if harvest is None:
                            harvest = ArbiterDecision(
                                action="HARVEST_WARNING",
                                passed=True,
                                reason=f"Counter-trend scalp detected while intraday trade is up +{r_multiple:.2f}R. Signal to tighten intraday stop to breakeven.",
                                suggested_intraday_action="TIGHTEN_STOP_TO_BE",
                                sizing_multiplier=0.50,
                            )
                    # same direction pyramid: no conflict
                # State 3: around breakeven (0 to 1.0R)
                else:
                    if not is_same_dir:
                        suppress_reasons.append(
                            f"opposing scalp suppressed while intraday {getattr(it, 'signal_id', '')} near breakeven ({r_multiple:.2f}R)"
                        )

            if suppress_reasons:
                return ArbiterDecision(
                    action="SUPPRESS", passed=False,
                    reason="REJECT_CROSS_DESK_CONFLICT: " + "; ".join(suppress_reasons),
                )
            if harvest is not None:
                return _with_beta(harvest)
            if sizing_note < 1.0:
                return _with_beta(ArbiterDecision(
                    action="ALLOW", passed=True,
                    reason="Same direction scalp aligned with intraday trade(s) in mild pullback",
                    sizing_multiplier=sizing_note,
                ))
            return _with_beta(ArbiterDecision(action="ALLOW", passed=True, reason="Cross-desk risk check passed"))

        # Candidate is Intraday trade while Scalp trade exists
        else:
            scalp_trades = [t for t in underlying_trades if _is_scalp_trade(t)]
            opposed = [st for st in scalp_trades if getattr(st, "direction", "") != candidate_direction]
            if opposed:
                # Intraday macro trade overrides fast scalp, but flag it
                return _with_beta(ArbiterDecision(
                    action="ALLOW",
                    passed=True,
                    reason=f"Macro intraday trade {candidate_direction} takes precedence over micro scalp(s) {', '.join(str(getattr(s, 'direction', '')) for s in opposed)}",
                    suggested_intraday_action="MONITOR_SCALP_EXIT",
                ))

        return _with_beta(ArbiterDecision(action="ALLOW", passed=True, reason="Cross-desk risk check passed"))


cross_desk_arbiter = CrossDeskArbiter()
