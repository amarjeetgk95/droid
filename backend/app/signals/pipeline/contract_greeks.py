"""Chain-implied Greeks for fallback option contracts.

Detectors resolve fallback contracts via ``resolve_option_contract`` (no
chain quotes are passed to the quantitative selector, so it fail-closes to
None). Those contracts carry a LIVE chain premium but no Greeks — and the
friction gate hard-fails without per-strike IV (REJECT_NO_LIVE_IV). Left as
is, no candidate could ever reach registration: a structural drought.

``attach_chain_implied_greeks`` closes the gap with market-implied math only:
solve IV from the live chain premium with the same Black-Scholes solver the
selector uses, then derive delta/theta from that IV. Nothing is defaulted —
no premium, no solvable IV, or an out-of-band IV returns a reason and the
candidate keeps ``greeks=None`` (fail-closed downstream as before).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import structlog

from app.signals.options_intelligence.greeks import BlackScholesGreeks
from app.signals.safety.clocks import IST as IST_TZ

logger = structlog.get_logger()

# Solved-IV sanity band (annualized). Outside it the premium/inputs are
# inconsistent (stale mark vs moved spot) — fail closed, never attach.
MIN_PLAUSIBLE_IV = 0.02
MAX_PLAUSIBLE_IV = 2.50


def _contract_field(contract: Any, name: str) -> Any:
    if contract is None:
        return None
    if isinstance(contract, dict):
        return contract.get(name)
    return getattr(contract, name, None)


def _live_premium_for(candidate: Any, contract: Any) -> Optional[float]:
    for raw in (
        _contract_field(contract, "live_premium"),
        _mark_price(_contract_field(contract, "broker_symbol")),
    ):
        try:
            if raw is not None and float(raw) > 0:
                return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _mark_price(broker_symbol: Any) -> Optional[float]:
    if not broker_symbol:
        return None
    try:
        from app.signals.option_marks import option_mark_registry

        mark = option_mark_registry.get_usable(str(broker_symbol), allow_model=False)
        if mark is not None and mark.price and float(mark.price) > 0:
            return float(mark.price)
    except Exception:
        pass
    return None


def _dte_years(expiry: Any) -> Optional[float]:
    try:
        exp_date = expiry.date() if isinstance(expiry, datetime) else expiry
        if not isinstance(exp_date, date):
            return None
        now = datetime.now(IST_TZ)
        close = datetime(exp_date.year, exp_date.month, exp_date.day, 15, 30, tzinfo=IST_TZ)
        hours = (close - now).total_seconds() / 3600.0
        return max(1e-6, hours / 8760.0)
    except Exception:
        return None


def attach_chain_implied_greeks(candidate: Any) -> Optional[str]:
    """Attach solver-derived Greeks from the live chain premium.

    Returns None when Greeks are present or were attached; otherwise a
    short reason code (candidate stays greeks-less, downstream fail-closed).
    """
    try:
        existing = getattr(candidate, "greeks", None) or {}
        giv = existing.get("iv") if isinstance(existing, dict) else getattr(existing, "iv", None)
        if giv is not None and float(giv) > 0:
            return None
    except (TypeError, ValueError):
        pass

    contract = getattr(candidate, "option_contract", None)
    if contract is None:
        return "no_contract"

    # Chain provenance only: a formula-derived symbol (offline weekday rules,
    # never confirmed by the broker chain) must never be valued — solving IV
    # off it would launder a fabrication through real math.
    try:
        source = str(_contract_field(contract, "contract_source") or "").lower()
        if source and source not in ("fyers_chain", "chain_quotes"):
            return "formula_only_no_chain_mark"
    except Exception:
        pass

    try:
        strike = float(_contract_field(contract, "strike") or 0.0)
        spot = float(getattr(candidate, "spot_price", 0.0) or 0.0)
    except (TypeError, ValueError):
        return "bad_inputs"
    if strike <= 0 or spot <= 0:
        return "bad_inputs"

    premium = _live_premium_for(candidate, contract)
    if premium is None:
        return "no_live_premium"

    direction = str(getattr(candidate, "direction", "") or "")
    opt_type = "CE" if "CALL" in direction.upper() else "PE"

    t_years = _dte_years(_contract_field(contract, "expiry_date"))
    if t_years is None:
        return "no_expiry"

    try:
        iv = BlackScholesGreeks.solve_iv(premium, spot, strike, t_years, opt_type)  # type: ignore[arg-type]
    except Exception:
        return "iv_solver_error"
    if iv is None or not (MIN_PLAUSIBLE_IV <= float(iv) <= MAX_PLAUSIBLE_IV):
        return "iv_unsolvable"

    try:
        greeks = BlackScholesGreeks.calculate_greeks(
            spot=spot,
            strike=strike,
            time_to_expiry_years=t_years,
            volatility=float(iv),
            option_type=opt_type,  # type: ignore[arg-type]
        )
    except Exception:
        return "greeks_error"

    try:
        candidate.greeks = greeks.model_dump()
    except Exception:
        return "attach_failed"
    logger.debug(
        "chain_implied_greeks_attached",
        strategy=getattr(candidate, "strategy", "?"),
        underlying=getattr(candidate, "underlying", "?"),
        iv=round(float(iv), 4),
        delta=round(float(greeks.delta), 4),
    )
    return None
