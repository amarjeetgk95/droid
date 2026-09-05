"""
Deterministic Pricing Authority + Risk/Reward + Position Sizing — §25, §26, §27

Python controls exact mathematical pricing.
Example BUY:  target = P90, invalidation = min(P10, VWAP - k × ATR)
Example SELL: target = P10, invalidation = max(P90, VWAP + k × ATR)
Make k configurable. Do not permit AI to override these values.
P10/P90 are forecast boundaries, not guaranteed price levels.

Risk/Reward: require R:R >= configured minimum (default 1.5)
Do not rely on AI-generated R:R.

Position sizing remains deterministic:
account equity, risk percentage, risk per unit, ATR, max position, max exposure
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class PricingResult:
    bias: str
    entry: float
    target: float
    invalidation: float
    potential_reward: float
    potential_risk: float
    risk_reward_ratio: float
    k: float
    vwap: float | None
    atr: float | None
    p10: float
    p50: float
    p90: float
    valid: bool
    reason: str | None = None


def calculate_deterministic_pricing(
    bias: Literal["BUY", "SELL"],
    current_price: float,
    p10: float,
    p50: float,
    p90: float,
    vwap: float | None = None,
    atr: float | None = None,
    k: float = 1.0,
    entry_override: float | None = None,
) -> PricingResult:
    """
    Deterministic pricing per §25.
    AI must NOT override these values.
    """
    if bias not in ("BUY", "SELL"):
        raise ValueError(f"pricing only for BUY/SELL, got {bias}")

    entry = entry_override if entry_override is not None else current_price

    # Validate quantiles already validated upstream, but double-check
    if not (math.isfinite(p10) and math.isfinite(p50) and math.isfinite(p90)):
        return PricingResult(bias=bias, entry=entry, target=0, invalidation=0, potential_reward=0, potential_risk=0, risk_reward_ratio=0, k=k, vwap=vwap, atr=atr, p10=p10, p50=p50, p90=p90, valid=False, reason="quantiles not finite")
    if not (p10 < p50 < p90):
        return PricingResult(bias=bias, entry=entry, target=0, invalidation=0, potential_reward=0, potential_risk=0, risk_reward_ratio=0, k=k, vwap=vwap, atr=atr, p10=p10, p50=p50, p90=p90, valid=False, reason="quantiles ordering invalid")

    # VWAP fallback if not provided
    _vwap = vwap if vwap is not None and math.isfinite(vwap) and vwap > 0 else entry
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return PricingResult(bias=bias, entry=entry, target=0, invalidation=0, potential_reward=0, potential_risk=0, risk_reward_ratio=0, k=k, vwap=vwap, atr=atr, p10=p10, p50=p50, p90=p90, valid=False, reason="ATR missing or non-positive")
    _atr = atr

    if bias == "BUY":
        target = p90
        invalidation = min(p10, _vwap - k * _atr)
    else:  # SELL
        target = p10
        invalidation = max(p90, _vwap + k * _atr)

    # Ensure risk/reward positive directionally
    if bias == "BUY":
        potential_reward = target - entry
        potential_risk = entry - invalidation
    else:
        potential_reward = entry - target
        potential_risk = invalidation - entry

    # Guard against non-positive risk/reward
    if potential_risk <= 0:
        return PricingResult(bias=bias, entry=entry, target=target, invalidation=invalidation, potential_reward=potential_reward, potential_risk=potential_risk, risk_reward_ratio=0, k=k, vwap=vwap, atr=atr, p10=p10, p50=p50, p90=p90, valid=False, reason="potential_risk <=0")
    if potential_reward <= 0:
        return PricingResult(bias=bias, entry=entry, target=target, invalidation=invalidation, potential_reward=potential_reward, potential_risk=potential_risk, risk_reward_ratio=0, k=k, vwap=vwap, atr=atr, p10=p10, p50=p50, p90=p90, valid=False, reason="potential_reward <=0")

    rr = potential_reward / potential_risk if potential_risk != 0 else 0.0
    return PricingResult(
        bias=bias,
        entry=round(entry, 2),
        target=round(target, 2),
        invalidation=round(invalidation, 2),
        potential_reward=round(potential_reward, 2),
        potential_risk=round(potential_risk, 2),
        risk_reward_ratio=round(rr, 2),
        k=k,
        vwap=vwap,
        atr=atr,
        p10=p10,
        p50=p50,
        p90=p90,
        valid=True,
    )


def validate_risk_reward(pricing: PricingResult, minimum_rr: float = 1.5) -> tuple[bool, str]:
    if not pricing.valid:
        return False, f"pricing invalid: {pricing.reason}"
    if pricing.risk_reward_ratio < minimum_rr:
        return False, f"R:R {pricing.risk_reward_ratio} < minimum {minimum_rr}"
    return True, f"R:R {pricing.risk_reward_ratio} >= {minimum_rr} OK"


def calculate_position_size(
    account_equity: float,
    risk_per_trade_pct: float = 1.0,
    risk_per_unit: float | None = None,
    atr: float | None = None,
    entry: float | None = None,
    invalidation: float | None = None,
    max_position: int | None = None,
    max_exposure_pct: float | None = None,
) -> dict:
    """
    Deterministic position sizing per §27.
    Use account equity, risk %, risk per unit, ATR, max position/exposure.

    risk_per_unit = abs(entry - invalidation) if not provided
    """
    if account_equity <= 0:
        raise ValueError("account_equity must be >0")
    risk_amount = account_equity * (risk_per_trade_pct / 100.0)

    if risk_per_unit is None:
        if entry is not None and invalidation is not None:
            risk_per_unit = abs(entry - invalidation)
        elif atr is not None:
            risk_per_unit = atr
        else:
            risk_per_unit = account_equity * 0.01  # fallback

    if risk_per_unit <= 0:
        raise ValueError("risk_per_unit must be >0")

    raw_qty = int(risk_amount // risk_per_unit) if risk_per_unit > 0 else 0
    raw_qty = max(0, raw_qty)

    # Apply max position limit
    if max_position is not None:
        raw_qty = min(raw_qty, max_position)

    # Apply max exposure
    if max_exposure_pct is not None and entry is not None:
        max_exposure_value = account_equity * (max_exposure_pct / 100.0)
        max_qty_by_exposure = int(max_exposure_value // entry) if entry > 0 else raw_qty
        raw_qty = min(raw_qty, max_qty_by_exposure)

    return {
        "account_equity": account_equity,
        "risk_per_trade_pct": risk_per_trade_pct,
        "risk_amount": round(risk_amount, 2),
        "risk_per_unit": round(risk_per_unit, 2),
        "quantity": raw_qty,
        "exposure_value": round(raw_qty * (entry or 0), 2),
    }


def validate_quantitative_confirmation(
    ai_bias: str,
    prob_up: float | None = None,
    prob_down: float | None = None,
    prob_threshold: float = 0.6,
    p50: float | None = None,
    current_price: float | None = None,
    forecast_valid: bool = True,
    rr_valid: bool = True,
    liquidity_valid: bool = True,
    spread_valid: bool = True,
    volatility_acceptable: bool = True,
    risk_limits_valid: bool = True,
) -> tuple[bool, str]:
    """
    Deterministic quantitative confirmation per §24.
    For BUY, require configurable conditions; same for SELL.
    AI is one layer of evidence.
    """
    bias = (ai_bias or "").upper()
    if bias not in ("BUY", "SELL"):
        return False, f"AI bias {bias} not BUY/SELL – no trade expected"

    if bias == "BUY":
        if prob_up is not None and prob_up < prob_threshold:
            return False, f"LightGBM prob_up {prob_up:.2f} < threshold {prob_threshold}"
        if p50 is not None and current_price is not None and p50 <= current_price:
            return False, f"P50 {p50} does not support bullish direction (price {current_price})"
    else:  # SELL
        if prob_down is not None and prob_down < prob_threshold:
            return False, f"LightGBM prob_down {prob_down:.2f} < threshold {prob_threshold}"
        if p50 is not None and current_price is not None and p50 >= current_price:
            return False, f"P50 {p50} does not support bearish direction (price {current_price})"

    if not forecast_valid:
        return False, "forecast invalid"
    if not rr_valid:
        return False, "R:R invalid"
    if not liquidity_valid:
        return False, "liquidity invalid"
    if not spread_valid:
        return False, "spread invalid"
    if not volatility_acceptable:
        return False, "volatility not acceptable"
    if not risk_limits_valid:
        return False, "risk limits invalid"

    return True, f"{bias} quantitative confirmation passed"
