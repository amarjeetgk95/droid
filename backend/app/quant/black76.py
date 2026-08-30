import math
from typing import Literal, NamedTuple


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function N(x)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function N'(x)."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


class Black76Greeks(NamedTuple):
    delta: float          # Spot Delta (-1 to +1)
    gamma: float          # Gamma
    theta: float          # Normalized Theta (per calendar day)
    vega: float           # Normalized Vega (per 1% change in IV)
    rho: float            # Normalized Rho (per 1% change in interest rate)
    theoretical_price: float
    intrinsic_value: float
    time_value: float


def black76_price(
    flag: Literal["CE", "PE", "C", "P"],
    f: float,      # Futures price
    k: float,      # Strike price
    t: float,      # Time to expiry in fractional years
    r: float,      # Risk-free interest rate
    sigma: float,  # Implied Volatility (e.g. 0.15 for 15%)
) -> float:
    """Compute theoretical European option price under Black-76 model.
    
    Adheres strictly to Section 28 of the quantitative engine spec.
    """
    flag_clean = flag.upper().replace("E", "")
    if t <= 0 or sigma <= 0 or f <= 0 or k <= 0:
        # Intrinsic value fallback at expiration / zero vol
        if flag_clean == "C":
            return max(0.0, f - k)
        return max(0.0, k - f)

    d1 = (math.log(f / k) + 0.5 * sigma * sigma * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    df = math.exp(-r * t)

    if flag_clean == "C":
        price = df * (f * _norm_cdf(d1) - k * _norm_cdf(d2))
    else:
        price = df * (k * _norm_cdf(-d2) - f * _norm_cdf(-d1))

    return max(0.0, price)


def black76_greeks(
    flag: Literal["CE", "PE", "C", "P"],
    f: float,
    k: float,
    t: float,
    r: float,
    sigma: float,
) -> Black76Greeks:
    """Compute analytical Greeks with standard Indian market normalization.
    
    Normalizations (Section 30):
    - Theta: Divided by 365 (decay per calendar day)
    - Vega: Divided by 100 (price sensitivity per 1% absolute IV change)
    - Rho: Divided by 100 (price sensitivity per 1% absolute rate change)
    """
    flag_clean = flag.upper().replace("E", "")
    intrinsic = max(0.0, f - k) if flag_clean == "C" else max(0.0, k - f)

    if t <= 1e-6 or sigma <= 1e-6 or f <= 0 or k <= 0:
        theo = intrinsic
        return Black76Greeks(
            delta=1.0 if flag_clean == "C" and f > k else (-1.0 if flag_clean == "P" and k > f else 0.0),
            gamma=0.0,
            theta=0.0,
            vega=0.0,
            rho=0.0,
            theoretical_price=theo,
            intrinsic_value=intrinsic,
            time_value=0.0,
        )

    sqrt_t = math.sqrt(t)
    d1 = (math.log(f / k) + 0.5 * sigma * sigma * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    df = math.exp(-r * t)
    pdf_d1 = _norm_pdf(d1)

    # Theoretical Price
    if flag_clean == "C":
        theo_price = df * (f * _norm_cdf(d1) - k * _norm_cdf(d2))
        delta = df * _norm_cdf(d1)
        raw_theta = -(f * df * pdf_d1 * sigma) / (2.0 * sqrt_t) + r * f * df * _norm_cdf(d1) - r * k * df * _norm_cdf(d2)
    else:
        theo_price = df * (k * _norm_cdf(-d2) - f * _norm_cdf(-d1))
        delta = -df * _norm_cdf(-d1)
        raw_theta = -(f * df * pdf_d1 * sigma) / (2.0 * sqrt_t) - r * f * df * _norm_cdf(-d1) + r * k * df * _norm_cdf(-d2)

    # Gamma (identical for Call and Put)
    gamma = (df * pdf_d1) / (f * sigma * sqrt_t)

    # Normalized Vega: sensitivity per 1% change in IV (sigma * 0.01)
    raw_vega = f * df * sqrt_t * pdf_d1
    vega_norm = raw_vega / 100.0

    # Normalized Theta: decay per calendar day
    theta_norm = raw_theta / 365.0

    # Normalized Rho: sensitivity per 1% change in rate
    raw_rho = -t * theo_price
    rho_norm = raw_rho / 100.0

    time_val = max(0.0, theo_price - intrinsic)

    return Black76Greeks(
        delta=round(delta, 4),
        gamma=round(gamma, 6),
        theta=round(theta_norm, 4),
        vega=round(vega_norm, 4),
        rho=round(rho_norm, 4),
        theoretical_price=round(theo_price, 2),
        intrinsic_value=round(intrinsic, 2),
        time_value=round(time_val, 2),
    )
