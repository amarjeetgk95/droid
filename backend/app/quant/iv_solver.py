import math
from typing import Literal
from app.quant.black76 import black76_price, black76_greeks
from app.quant.black_scholes import black_scholes_price, black_scholes_greeks

IV_MIN_BRACKET: float = 0.005  # 0.5% min IV
IV_MAX_BRACKET: float = 5.0    # 500% max IV
MAX_ITERATIONS: int = 50
TOLERANCE: float = 1e-4


def calculate_iv_black76(
    flag: Literal["CE", "PE", "C", "P"],
    target_price: float,
    f: float,
    k: float,
    t: float,
    r: float,
    initial_guess: float = 0.20,
) -> float | None:
    """Invert Black-76 option pricing formula to solve for Implied Volatility.
    
    Adheres strictly to Section 33 of the quantitative engine spec.
    Uses Brent's root-finding method with Newton-Raphson acceleration.
    """
    flag_clean = flag.upper().replace("E", "")
    intrinsic = max(0.0, f - k) if flag_clean == "C" else max(0.0, k - f)
    discounted_intrinsic = math.exp(-r * t) * intrinsic

    # If target price is less than discounted intrinsic, IV is mathematically undefined
    if target_price <= discounted_intrinsic or target_price <= 0.05 or t <= 1e-5:
        return None

    # Newton-Raphson fast convergence attempt
    sigma = initial_guess
    for _ in range(MAX_ITERATIONS):
        price = black76_price(flag, f, k, t, r, sigma)
        diff = price - target_price
        if abs(diff) < TOLERANCE:
            return round(sigma, 4)

        greeks = black76_greeks(flag, f, k, t, r, sigma)
        vega = greeks.vega * 100.0  # Unnormalized vega (dPrice/dSigma)
        if vega < 1e-4:
            break  # Switch to Brent's bisection if vega too small

        step = diff / vega
        sigma -= step

        if sigma < IV_MIN_BRACKET or sigma > IV_MAX_BRACKET:
            break  # Out of bounds, fall back to Brent's method

    # Robust Brent's Bisection Fallback
    low = IV_MIN_BRACKET
    high = IV_MAX_BRACKET
    f_low = black76_price(flag, f, k, t, r, low) - target_price
    f_high = black76_price(flag, f, k, t, r, high) - target_price

    if f_low * f_high > 0:
        # Root is not bracketed within 0.5% to 500%
        return None

    for _ in range(MAX_ITERATIONS):
        mid = 0.5 * (low + high)
        f_mid = black76_price(flag, f, k, t, r, mid) - target_price

        if abs(f_mid) < TOLERANCE or (high - low) < TOLERANCE:
            return round(mid, 4)

        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return round(0.5 * (low + high), 4)


def calculate_iv_black_scholes(
    flag: Literal["CE", "PE", "C", "P"],
    target_price: float,
    s: float,
    k: float,
    t: float,
    r: float,
    initial_guess: float = 0.20,
) -> float | None:
    """Invert Black-Scholes pricing formula to solve for Implied Volatility."""
    flag_clean = flag.upper().replace("E", "")
    intrinsic = max(0.0, s - k) if flag_clean == "C" else max(0.0, k - s)

    if target_price <= intrinsic or target_price <= 0.05 or t <= 1e-5:
        return None

    low = IV_MIN_BRACKET
    high = IV_MAX_BRACKET
    f_low = black_scholes_price(flag, s, k, t, r, low) - target_price
    f_high = black_scholes_price(flag, s, k, t, r, high) - target_price

    if f_low * f_high > 0:
        return None

    for _ in range(MAX_ITERATIONS):
        mid = 0.5 * (low + high)
        f_mid = black_scholes_price(flag, s, k, t, r, mid) - target_price

        if abs(f_mid) < TOLERANCE or (high - low) < TOLERANCE:
            return round(mid, 4)

        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid

    return round(0.5 * (low + high), 4)
