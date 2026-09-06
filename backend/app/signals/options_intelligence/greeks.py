"""
Options Intelligence: Analytical Black-Scholes Greeks and IV Solver
Specialized for European Index Options (NSE / BSE - NIFTY, BANKNIFTY, SENSEX).

Calculates:
  - Theoretical Price
  - Delta (Δ)
  - Gamma (Γ)
  - Theta (Θ) per calendar day and per Indian trading hour (6.25h session)
  - Vega (V) per 1% change in IV
  - Rho (ρ)
  - Implied Volatility (IV) via Newton-Raphson with Brent/Bisection fallback
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
        if spot <= 0 or strike <= 0 or time_to_expiry_years <= 0 or volatility <= 0:
            return 0.0, 0.0
        
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
        """Calculates complete suite of first and second-order Greeks."""
        t = max(1e-6, time_to_expiry_years)
        vol = max(0.0001, volatility)
        
        d1, d2 = cls.calculate_d1_d2(spot, strike, t, vol, risk_free_rate, dividend_yield)
        
        df_q = math.exp(-dividend_yield * t)
        df_r = math.exp(-risk_free_rate * t)
        pdf_d1 = norm_pdf(d1)
        sqrt_t = math.sqrt(t)

        # 1. Price
        if option_type == "CE":
            theo_price = spot * df_q * norm_cdf(d1) - strike * df_r * norm_cdf(d2)
            delta = df_q * norm_cdf(d1)
            rho = (strike * t * df_r * norm_cdf(d2)) * 0.01
            # Theta for European Call
            theta_annual = (
                -(spot * df_q * vol * pdf_d1) / (2.0 * sqrt_t)
                - risk_free_rate * strike * df_r * norm_cdf(d2)
                + dividend_yield * spot * df_q * norm_cdf(d1)
            )
        else:
            theo_price = strike * df_r * norm_cdf(-d2) - spot * df_q * norm_cdf(-d1)
            delta = -df_q * norm_cdf(-d1)
            rho = (-strike * t * df_r * norm_cdf(-d2)) * 0.01
            # Theta for European Put
            theta_annual = (
                -(spot * df_q * vol * pdf_d1) / (2.0 * sqrt_t)
                + risk_free_rate * strike * df_r * norm_cdf(-d2)
                - dividend_yield * spot * df_q * norm_cdf(-d1)
            )

        theo_price = max(0.0, theo_price)

        # 2. Gamma (identical for Call and Put)
        gamma = (df_q * pdf_d1) / (spot * vol * sqrt_t) if (spot * vol * sqrt_t) > 0 else 0.0

        # 3. Vega (per 1% absolute IV change, e.g. 15% -> 16%)
        vega_total = spot * df_q * sqrt_t * pdf_d1
        vega_per_point = vega_total * 0.01

        # 4. Theta conversions (calendar day = / 365, trading hour = / (252 * 6.25))
        theta_day = theta_annual / 365.0
        # Indian market has ~252 trading days * 6.25 hours = 1575 trading hours/year
        theta_hour = theta_annual / (252.0 * cls.TRADING_HOURS_PER_DAY)
        theta_pct_day = (theta_day / theo_price * 100.0) if theo_price > 0.05 else 0.0

        # Moneyness checks
        moneyness = spot / strike if strike > 0 else 1.0
        atm_threshold = 0.005  # Within 0.5% is considered ATM
        if option_type == "CE":
            is_itm = spot > (strike * (1.0 + atm_threshold))
            is_otm = spot < (strike * (1.0 - atm_threshold))
            is_atm = not is_itm and not is_otm
        else:
            is_itm = spot < (strike * (1.0 - atm_threshold))
            is_otm = spot > (strike * (1.0 + atm_threshold))
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
    ) -> float:
        """
        Solves for Implied Volatility (IV) from option market price.
        Uses Newton-Raphson with robust Brent/Bisection fallback.
        Returns annualized IV as a decimal (e.g. 0.15 = 15.0%).
        """
        if market_price <= 0 or spot <= 0 or strike <= 0 or time_to_expiry_years <= 1e-6:
            return 0.0

        # Lower bound: Intrinsic value discounted
        t = max(1e-6, time_to_expiry_years)
        df_q = math.exp(-dividend_yield * t)
        df_r = math.exp(-risk_free_rate * t)

        if option_type == "CE":
            intrinsic = max(0.0, spot * df_q - strike * df_r)
        else:
            intrinsic = max(0.0, strike * df_r - spot * df_q)

        if market_price <= intrinsic:
            return 0.001  # At lower boundary / near intrinsic

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

        return round(0.5 * (low + high), 4)
