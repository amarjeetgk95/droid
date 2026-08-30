import math
from typing import Literal, NamedTuple
from app.quant.black76 import _norm_cdf, _norm_pdf


class BlackScholesGreeks(NamedTuple):
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    theoretical_price: float
    intrinsic_value: float
    time_value: float


def black_scholes_price(
    flag: Literal["CE", "PE", "C", "P"],
    s: float,      # Spot price
    k: float,      # Strike price
    t: float,      # Time to expiry in fractional years
    r: float,      # Risk-free rate
    sigma: float,  # Implied Volatility
) -> float:
    """Compute theoretical European option price under Black-Scholes model.
    
    Adheres strictly to Section 29 of the quantitative engine spec.
    """
    flag_clean = flag.upper().replace("E", "")
    if t <= 0 or sigma <= 0 or s <= 0 or k <= 0:
        if flag_clean == "C":
            return max(0.0, s - k)
        return max(0.0, k - s)

    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    df = math.exp(-r * t)

    if flag_clean == "C":
        price = s * _norm_cdf(d1) - k * df * _norm_cdf(d2)
    else:
        price = k * df * _norm_cdf(-d2) - s * _norm_cdf(-d1)

    return max(0.0, price)


def black_scholes_greeks(
    flag: Literal["CE", "PE", "C", "P"],
    s: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
) -> BlackScholesGreeks:
    """Compute Black-Scholes analytical Greeks with standard Indian market normalization."""
    flag_clean = flag.upper().replace("E", "")
    intrinsic = max(0.0, s - k) if flag_clean == "C" else max(0.0, k - s)

    if t <= 1e-6 or sigma <= 1e-6 or s <= 0 or k <= 0:
        theo = intrinsic
        return BlackScholesGreeks(
            delta=1.0 if flag_clean == "C" and s > k else (-1.0 if flag_clean == "P" and k > s else 0.0),
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
            theoretical_price=theo,
            intrinsic_value=intrinsic,
            time_value=0.0,
        )

    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (r + 0.5 * sigma * sigma) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    df = math.exp(-r * t)
    pdf_d1 = _norm_pdf(d1)

    if flag_clean == "C":
        theo_price = s * _norm_cdf(d1) - k * df * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        raw_theta = -(s * pdf_d1 * sigma) / (2.0 * sqrt_t) - r * k * df * _norm_cdf(d2)
        raw_rho = k * t * df * _norm_cdf(d2)
    else:
        theo_price = k * df * _norm_cdf(-d2) - s * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        raw_theta = -(s * pdf_d1 * sigma) / (2.0 * sqrt_t) + r * k * df * _norm_cdf(-d2)
        raw_rho = -k * t * df * _norm_cdf(-d2)

    gamma = pdf_d1 / (s * sigma * sqrt_t)
    raw_vega = s * sqrt_t * pdf_d1
    vega_norm = raw_vega / 100.0
    theta_norm = raw_theta / 365.0
    rho_norm = raw_rho / 100.0

    time_val = max(0.0, theo_price - intrinsic)

    return BlackScholesGreeks(
        delta=round(delta, 4),
        gamma=round(gamma, 6),
        theta=round(theta_norm, 4),
        vega=round(vega_norm, 4),
        rho=round(rho_norm, 4),
        theoretical_price=round(theo_price, 2),
        intrinsic_value=round(intrinsic, 2),
        time_value=round(time_val, 2),
    )
