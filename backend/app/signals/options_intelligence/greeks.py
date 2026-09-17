"""
Options Intelligence: Analytical Black-Scholes Greeks and IV Solver
Specialized for European Index Options (NSE / BSE - NIFTY, BANKNIFTY, SENSEX).

Calculates:
  - Theoretical Price
  - Delta (Δ)
  - Gamma (Γ)
  - Theta (Θ) per calendar day, per trading day, and per Indian trading hour (6.25h session)
  - Vega (V) per 1% change in IV
  - Rho (ρ)
  - Charm (Δ decay per day / per hour) and Vanna (Δ sensitivity to IV)
  - Implied Volatility (IV) via Newton-Raphson with Brent/Bisection fallback
  - Vectorized smile solver (solve_iv per strike)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional
from pydantic import BaseModel, Field


# Standard normal cumulative distribution function
def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Standard normal probability density function
def norm_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


class GreeksResult(BaseModel):
    theoretical_price: float = Field(..., description="Theoretical option price in ₹")
    delta: float = Field(..., description="Option Delta (rate of change of price per ₹1 move in spot)")
    gamma: float = Field(..., description="Option Gamma (rate of change of delta per ₹1 move in spot)")
    theta_day: float = Field(..., description="Theta decay in ₹ per calendar day (negative)")
    theta_hour: float = Field(..., description="Theta decay in ₹ per market trading hour (negative, 6.25h session)")
    theta_pct_day: float = Field(..., description="Daily theta decay as % of current premium")
    vega: float = Field(..., description="Vega: ₹ change per 1.0% absolute change in IV")
    rho: float = Field(..., description="Rho: ₹ change per 1.0% absolute change in interest rate")
    iv: float = Field(..., description="Implied volatility (annualized, e.g. 0.15 = 15%)")
    moneyness: float = Field(..., description="S / K ratio")
    is_itm: bool
    is_atm: bool
    is_otm: bool
    # P1 extensions (defaulted so old callers / stored blobs keep parsing).
    theta_trading_day: float = Field(default=0.0, description="Theta decay in ₹ per trading day (annual/252, negative)")
    charm_day: float = Field(default=0.0, description="Charm: delta change per calendar day (delta bleed)")
    charm_hour: float = Field(default=0.0, description="Charm: delta change per trading hour")
    vanna: float = Field(default=0.0, description="Vanna: delta change per 1% absolute IV move")
    dte_days: float = Field(default=0.0, description="Days to expiry backing this greek snapshot")


def _degenerate_greeks(
    spot: float,
    strike: float,
    option_type: str,
    iv: float,
    t_years: float,
) -> GreeksResult:
    """None-safe intrinsic fallback for degenerate T / sigma.

    Never raises: at/after expiry the option is intrinsic with binary delta,
    zero gamma/vega/charm/vanna and zero time decay.
    """
    try:
        s = float(spot or 0.0)
        k = float(strike or 1.0)
    except Exception:
        s, k = 0.0, 1.0
    otype = str(option_type or "CE").upper()
    if otype == "CE":
        price = max(0.0, s - k)
        delta = 1.0 if s > k else 0.0
        is_itm, is_otm = s > k, s < k
    else:
        price = max(0.0, k - s)
        delta = -1.0 if s < k else 0.0
        is_itm, is_otm = s < k, s > k
    is_atm = not is_itm and not is_otm
    moneyness = (s / k) if k > 0 else 1.0
    try:
        iv_f = float(iv or 0.0)
    except Exception:
        iv_f = 0.0
    return GreeksResult(
        theoretical_price=round(price, 4),
        delta=round(delta, 4),
        gamma=0.0,
        theta_day=0.0,
        theta_hour=0.0,
        theta_pct_day=0.0,
        vega=0.0,
        rho=0.0,
        iv=round(max(0.0, iv_f), 4),
        moneyness=round(moneyness, 4),
        is_itm=bool(is_itm),
        is_atm=bool(is_atm),
        is_otm=bool(is_otm),
        theta_trading_day=0.0,
        charm_day=0.0,
        charm_hour=0.0,
        vanna=0.0,
        dte_days=round(max(0.0, float(t_years or 0.0)) * 365.0, 4),
    )


class BlackScholesGreeks:
    """
    High-performance analytical Black-Scholes calculator for European Index Options.
    Assumes standard Indian market parameters:
      - Default risk-free rate r = 6.5% (RBI 91-day T-bill reference)
      - Default dividend yield q = 1.2% (NIFTY index dividend yield baseline)
      - Session hours per day = 6.25 hours (09:15 to 15:30 IST)
    """

    DEFAULT_R = 0.065  # 6.5% risk-free rate
    DEFAULT_Q = 0.012  # 1.2% dividend yield
    TRADING_HOURS_PER_DAY = 6.25

    @classmethod
    def calculate_d1_d2(
        cls,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> tuple[float, float]:
        if spot <= 0 or strike <= 0:
            raise ValueError(f"Invalid option inputs: spot={spot}, strike={strike} must be positive")
        if volatility <= 0:
            raise ValueError(f"Invalid volatility: {volatility} must be positive")
        if time_to_expiry_years <= 0:
            return float("-inf"), float("-inf")

        sigma_sqrt_t = volatility * math.sqrt(time_to_expiry_years)
        d1 = (
            math.log(spot / strike)
            + (risk_free_rate - dividend_yield + 0.5 * volatility * volatility) * time_to_expiry_years
        ) / sigma_sqrt_t
        d2 = d1 - sigma_sqrt_t
        return d1, d2

    @classmethod
    def calculate_price(
        cls,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        option_type: Literal["CE", "PE"],
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> float:
        """Calculates theoretical European option price."""
        if time_to_expiry_years <= 1e-7:
            # At expiry
            if option_type == "CE":
                return max(0.0, spot - strike)
            return max(0.0, strike - spot)

        vol = max(0.0001, volatility)
        t = max(1e-6, time_to_expiry_years)
        d1, d2 = cls.calculate_d1_d2(spot, strike, t, vol, risk_free_rate, dividend_yield)

        df_q = math.exp(-dividend_yield * t)
        df_r = math.exp(-risk_free_rate * t)

        if option_type == "CE":
            price = spot * df_q * norm_cdf(d1) - strike * df_r * norm_cdf(d2)
        else:
            price = strike * df_r * norm_cdf(-d2) - spot * df_q * norm_cdf(-d1)

        return max(0.0, price)

    @classmethod
    def _delta_for(
        cls,
        spot: float,
        strike: float,
        t: float,
        vol: float,
        option_type: str,
        r: float,
        q: float,
    ) -> float:
        try:
            d1, _ = cls.calculate_d1_d2(spot, strike, t, vol, r, q)
            df_q = math.exp(-q * t)
            if str(option_type).upper() == "CE":
                return df_q * norm_cdf(d1)
            return -df_q * norm_cdf(-d1)
        except Exception:
            return 0.0

    @classmethod
    def calculate_charm_vanna(
        cls,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        option_type: Literal["CE", "PE"],
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> dict[str, float]:
        """Charm (delta bleed) + vanna via bump-and-revalue (None-safe).

        Analytic charm/vanna formulas are brittle near expiry; finite
        differences on the same pricer the desk already trusts stay stable
        and degenerate-safe.
        """
        try:
            t = float(time_to_expiry_years or 0.0)
            vol = float(volatility or 0.0)
            if spot <= 0 or strike <= 0 or t <= 1e-7 or vol <= 0:
                return {"charm_day": 0.0, "charm_hour": 0.0, "vanna": 0.0}
            base = cls._delta_for(spot, strike, t, vol, option_type, risk_free_rate, dividend_yield)
            # One calendar day less time.
            t_down = max(1e-7, t - 1.0 / 365.0)
            down = cls._delta_for(spot, strike, t_down, vol, option_type, risk_free_rate, dividend_yield)
            charm_day = float(down - base)
            charm_hour = float(charm_day / cls.TRADING_HOURS_PER_DAY)
            # ±1 vol point bump.
            bump = 0.01
            d_up = cls._delta_for(spot, strike, t, min(4.0, vol + bump), option_type, risk_free_rate, dividend_yield)
            d_dn = cls._delta_for(spot, strike, t, max(0.0001, vol - bump), option_type, risk_free_rate, dividend_yield)
            vanna = float((d_up - d_dn) / 2.0)
            return {
                "charm_day": round(charm_day, 6),
                "charm_hour": round(charm_hour, 6),
                "vanna": round(vanna, 6),
            }
        except Exception:
            return {"charm_day": 0.0, "charm_hour": 0.0, "vanna": 0.0}

    @classmethod
    def calculate_greeks(
        cls,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        volatility: float,
        option_type: Literal["CE", "PE"],
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> GreeksResult:
        """Calculates complete suite of first and second-order Greeks (None-safe)."""
        # Degenerate inputs → intrinsic fallback instead of raising, so the
        # selector / simulator can veto the strike instead of crashing.
        try:
            s = float(spot or 0.0)
            k = float(strike or 0.0)
            v = float(volatility or 0.0)
            t_in = float(time_to_expiry_years or 0.0)
        except Exception:
            return _degenerate_greeks(spot or 0.0, strike or 1.0, str(option_type), 0.0, 0.0)
        if s <= 0 or k <= 0 or v <= 0 or t_in <= 1e-7:
            return _degenerate_greeks(s if s > 0 else 0.0, k if k > 0 else 1.0, str(option_type), v, t_in)
        t = max(1e-6, t_in)
        vol = max(0.0001, v)

        d1, d2 = cls.calculate_d1_d2(s, k, t, vol, risk_free_rate, dividend_yield)

        df_q = math.exp(-dividend_yield * t)
        df_r = math.exp(-risk_free_rate * t)
        pdf_d1 = norm_pdf(d1)
        sqrt_t = math.sqrt(t)

        # 1. Price
        if option_type == "CE":
            theo_price = s * df_q * norm_cdf(d1) - k * df_r * norm_cdf(d2)
            delta = df_q * norm_cdf(d1)
            rho = (k * t * df_r * norm_cdf(d2)) * 0.01
            # Theta for European Call
            theta_annual = (
                -(s * df_q * vol * pdf_d1) / (2.0 * sqrt_t)
                - risk_free_rate * k * df_r * norm_cdf(d2)
                + dividend_yield * s * df_q * norm_cdf(d1)
            )
        else:
            theo_price = k * df_r * norm_cdf(-d2) - s * df_q * norm_cdf(-d1)
            delta = -df_q * norm_cdf(-d1)
            rho = (-k * t * df_r * norm_cdf(-d2)) * 0.01
            # Theta for European Put
            theta_annual = (
                -(s * df_q * vol * pdf_d1) / (2.0 * sqrt_t)
                + risk_free_rate * k * df_r * norm_cdf(-d2)
                - dividend_yield * s * df_q * norm_cdf(-d1)
            )

        theo_price = max(0.0, theo_price)

        # 2. Gamma (identical for Call and Put)
        gamma = (df_q * pdf_d1) / (s * vol * sqrt_t) if (s * vol * sqrt_t) > 0 else 0.0

        # 3. Vega (per 1% absolute IV change, e.g. 15% -> 16%)
        vega_total = s * df_q * sqrt_t * pdf_d1
        vega_per_point = vega_total * 0.01

        # 4. Theta conversions (calendar day = / 365, trading day = /252,
        #    trading hour = / (252 * 6.25))
        theta_day = theta_annual / 365.0
        theta_trading_day = theta_annual / 252.0
        # Indian market has ~252 trading days * 6.25 hours = 1575 trading hours/year
        theta_hour = theta_annual / (252.0 * cls.TRADING_HOURS_PER_DAY)
        theta_pct_day = (theta_day / theo_price * 100.0) if theo_price > 0.05 else 0.0

        # 5. Charm + vanna (bump-and-revalue, degenerate-safe).
        cv = cls.calculate_charm_vanna(s, k, t, vol, option_type, risk_free_rate, dividend_yield)

        # Moneyness checks
        moneyness = s / k if k > 0 else 1.0
        atm_threshold = 0.005  # Within 0.5% is considered ATM
        if option_type == "CE":
            is_itm = s > (k * (1.0 + atm_threshold))
            is_otm = s < (k * (1.0 - atm_threshold))
            is_atm = not is_itm and not is_otm
        else:
            is_itm = s < (k * (1.0 - atm_threshold))
            is_otm = s > (k * (1.0 + atm_threshold))
            is_atm = not is_itm and not is_otm

        return GreeksResult(
            theoretical_price=round(theo_price, 4),
            delta=round(delta, 4),
            gamma=round(gamma, 6),
            theta_day=round(theta_day, 4),
            theta_hour=round(theta_hour, 4),
            theta_pct_day=round(theta_pct_day, 2),
            vega=round(vega_per_point, 4),
            rho=round(rho, 4),
            iv=round(vol, 4),
            moneyness=round(moneyness, 4),
            is_itm=is_itm,
            is_atm=is_atm,
            is_otm=is_otm,
            theta_trading_day=round(theta_trading_day, 4),
            charm_day=cv["charm_day"],
            charm_hour=cv["charm_hour"],
            vanna=cv["vanna"],
            dte_days=round(t * 365.0, 4),
        )

    @classmethod
    def solve_iv(
        cls,
        market_price: float,
        spot: float,
        strike: float,
        time_to_expiry_years: float,
        option_type: Literal["CE", "PE"],
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
        initial_guess: float = 0.18,
        max_iterations: int = 100,
        tolerance: float = 1e-4,
    ) -> Optional[float]:
        """
        Solves for Implied Volatility (IV) from option market price.
        Uses Newton-Raphson with robust Brent/Bisection fallback.
        Returns annualized IV as a decimal (e.g. 0.15 = 15.0%), or None if unresolved.
        None-safe: degenerate T / sigma / intrinsic violations return None.
        """
        try:
            if market_price is None or spot is None or strike is None or time_to_expiry_years is None:
                return None
            if market_price <= 0 or spot <= 0 or strike <= 0 or time_to_expiry_years <= 1e-6:
                return None
        except Exception:
            return None

        try:
            t = max(1e-6, time_to_expiry_years)
            df_q = math.exp(-dividend_yield * t)
            df_r = math.exp(-risk_free_rate * t)

            if option_type == "CE":
                intrinsic = max(0.0, spot * df_q - strike * df_r)
            else:
                intrinsic = max(0.0, strike * df_r - spot * df_q)

            if market_price <= intrinsic:
                return None

            upper_theo = cls.calculate_price(spot, strike, t, 4.0, option_type, risk_free_rate, dividend_yield)
            if market_price > upper_theo * 1.05:
                return None

            sigma = max(0.02, min(initial_guess, 2.0))

            # Newton-Raphson loop
            for _ in range(max_iterations):
                theo = cls.calculate_price(spot, strike, t, sigma, option_type, risk_free_rate, dividend_yield)
                diff = theo - market_price
                if abs(diff) < tolerance:
                    return round(sigma, 4)

                # Vega for Newton step
                d1, _ = cls.calculate_d1_d2(spot, strike, t, sigma, risk_free_rate, dividend_yield)
                vega = spot * df_q * math.sqrt(t) * norm_pdf(d1)

                if vega < 1e-6:
                    break  # Vega near zero, abort Newton-Raphson and use Bisection

                step = diff / vega
                sigma -= step

                # If step throws sigma into invalid region, abort to Bisection
                if sigma <= 0.001 or sigma >= 5.0:
                    break

            # Fallback: Bisection / Brent search on [0.001, 4.0] (0.1% to 400% IV)
            low = 0.001
            high = 4.0
            for _ in range(60):
                mid = 0.5 * (low + high)
                theo = cls.calculate_price(spot, strike, t, mid, option_type, risk_free_rate, dividend_yield)
                diff = theo - market_price
                if abs(diff) < tolerance:
                    return round(mid, 4)
                if diff > 0:
                    high = mid
                else:
                    low = mid

            final_theo = cls.calculate_price(spot, strike, t, 0.5 * (low + high), option_type, risk_free_rate, dividend_yield)
            if abs(final_theo - market_price) > tolerance * 10:
                return None
            return round(0.5 * (low + high), 4)
        except Exception:
            return None

    @classmethod
    def solve_iv_smile(
        cls,
        market_prices_by_strike: dict[float, float],
        spot: float,
        time_to_expiry_years: float,
        option_type: Literal["CE", "PE"],
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> dict[float, Optional[float]]:
        """Vectorized smile: solve_iv per strike (None-safe per leg).

        One bad quote (stale / crossed / below intrinsic) yields None for that
        strike only — never poisons the rest of the smile.
        """
        out: dict[float, Optional[float]] = {}
        for strike, px in (market_prices_by_strike or {}).items():
            try:
                k = float(strike)
                out[strike] = cls.solve_iv(
                    float(px or 0.0), float(spot or 0.0), k,
                    float(time_to_expiry_years or 0.0), option_type,
                    risk_free_rate, dividend_yield,
                )
            except Exception:
                out[strike] = None
        return out

    @classmethod
    def calculate_greeks_smile(
        cls,
        spot: float,
        strikes: list[float],
        time_to_expiry_years: float,
        iv_by_strike: dict[float, float],
        option_type: Literal["CE", "PE"],
        fallback_iv: Optional[float] = None,
        risk_free_rate: float = DEFAULT_R,
        dividend_yield: float = DEFAULT_Q,
    ) -> dict[float, GreeksResult]:
        """Greeks per strike off the per-strike smile (None-safe)."""
        out: dict[float, GreeksResult] = {}
        for k in strikes or []:
            try:
                iv = iv_by_strike.get(float(k), iv_by_strike.get(k, fallback_iv))
                if iv is None or float(iv) <= 0:
                    if fallback_iv is None or float(fallback_iv) <= 0:
                        out[float(k)] = _degenerate_greeks(spot, float(k), str(option_type), 0.0, time_to_expiry_years)
                        continue
                    iv = fallback_iv
                out[float(k)] = cls.calculate_greeks(
                    spot, float(k), time_to_expiry_years, float(iv),
                    option_type, risk_free_rate, dividend_yield,
                )
            except Exception:
                try:
                    out[float(k)] = _degenerate_greeks(spot, float(k), str(option_type), 0.0, time_to_expiry_years)
                except Exception:
                    continue
        return out
