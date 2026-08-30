import math
from typing import Literal, NamedTuple
from app.quant.black76 import black76_price, black76_greeks, _norm_cdf


class LegParams(NamedTuple):
    option_type: Literal["CE", "PE"]
    side: Literal["BUY", "SELL"]  # BUY = +1, SELL = -1
    strike: float
    quantity: int                 # in lots
    price: float                  # entry premium per unit
    iv: float                     # Implied volatility (e.g. 0.16)
    lot_size: int = 75


class PayoffPoint(NamedTuple):
    spot_price: float
    expiry_pnl: float
    t0_pnl: float


class StrategyAnalytics(NamedTuple):
    payoff_curve: list[PayoffPoint]
    net_premium: float            # Positive = Debit (Paid), Negative = Credit (Received)
    max_profit: float | None      # None = Unlimited
    max_loss: float | None        # None = Unlimited
    breakevens: list[float]
    risk_reward_ratio: float | None
    pop_percent: float            # Probability of Profit (0-100%)
    net_delta: float
    net_gamma: float
    net_theta: float              # Daily Theta decay in Rupees
    net_vega: float               # Vega P&L per 1% IV in Rupees


def calculate_strategy_payoff(
    legs: list[LegParams],
    spot_price: float,
    time_to_expiry: float,
    risk_free_rate: float = 0.0675,
    num_points: int = 80,
) -> StrategyAnalytics:
    """Simulate Dual-Curve (At-Expiry & T+0) Payoff and aggregate portfolio Greeks.
    
    Adheres strictly to Sections 61 through 70 of the quantitative spec.
    """
    if not legs:
        return StrategyAnalytics(
            payoff_curve=[],
            net_premium=0.0,
            max_profit=0.0,
            max_loss=0.0,
            breakevens=[],
            risk_reward_ratio=None,
            pop_percent=50.0,
            net_delta=0.0,
            net_gamma=0.0,
            net_theta=0.0,
            net_vega=0.0,
        )

    # 1. Calculate Net Entry Premium and Net Greeks
    net_prem = 0.0
    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0
    all_strikes = [l.strike for l in legs]

    for leg in legs:
        sign = 1.0 if leg.side == "BUY" else -1.0
        total_units = leg.quantity * leg.lot_size
        net_prem += sign * total_units * leg.price

        # Greek calculation
        g = black76_greeks(leg.option_type, spot_price, leg.strike, time_to_expiry, risk_free_rate, leg.iv)
        net_delta += sign * total_units * g.delta
        net_gamma += sign * total_units * g.gamma
        net_theta += sign * total_units * g.theta
        net_vega += sign * total_units * g.vega

    # 2. Determine Spot Price Range for Payoff Simulation
    min_k = min(all_strikes)
    max_k = max(all_strikes)
    span = max(max_k - min_k, spot_price * 0.10)
    p_min = max(100.0, min(spot_price, min_k) - span * 0.8)
    p_max = max(spot_price, max_k) + span * 0.8
    step = (p_max - p_min) / (num_points - 1)

    payoff_curve: list[PayoffPoint] = []
    expiry_pnls: list[float] = []

    for idx in range(num_points):
        s = p_min + idx * step
        exp_pnl = 0.0
        t0_pnl = 0.0

        for leg in legs:
            sign = 1.0 if leg.side == "BUY" else -1.0
            total_units = leg.quantity * leg.lot_size

            # At-Expiry Intrinsic
            if leg.option_type == "CE":
                intrinsic = max(0.0, s - leg.strike)
            else:
                intrinsic = max(0.0, leg.strike - s)

            exp_pnl += sign * total_units * (intrinsic - leg.price)

            # T+0 Model Price
            m_price = black76_price(leg.option_type, s, leg.strike, time_to_expiry, risk_free_rate, leg.iv)
            t0_pnl += sign * total_units * (m_price - leg.price)

        payoff_curve.append(PayoffPoint(
            spot_price=round(s, 2),
            expiry_pnl=round(exp_pnl, 2),
            t0_pnl=round(t0_pnl, 2),
        ))
        expiry_pnls.append(exp_pnl)

    # 3. Breakevens & Max Profit / Max Loss
    breakevens: list[float] = []
    for i in range(1, len(payoff_curve)):
        p1 = payoff_curve[i - 1]
        p2 = payoff_curve[i]
        if (p1.expiry_pnl <= 0 and p2.expiry_pnl >= 0) or (p1.expiry_pnl >= 0 and p2.expiry_pnl <= 0):
            # Linear interpolation for zero crossing
            denom = (p2.expiry_pnl - p1.expiry_pnl)
            if abs(denom) > 1e-4:
                be = p1.spot_price - p1.expiry_pnl * (p2.spot_price - p1.spot_price) / denom
                breakevens.append(round(be, 2))

    min_pnl = min(expiry_pnls)
    max_pnl = max(expiry_pnls)

    # Check for unbounded ends
    left_slope = (expiry_pnls[1] - expiry_pnls[0])
    right_slope = (expiry_pnls[-1] - expiry_pnls[-2])

    max_profit = None if (right_slope > 1.0 or left_slope < -1.0) else round(max_pnl, 2)
    max_loss = None if (right_slope < -1.0 or left_slope > 1.0) else round(abs(min(0.0, min_pnl)), 2)

    # Risk-Reward
    rr_ratio = None
    if max_profit and max_loss and max_profit > 0 and max_loss > 0:
        rr_ratio = round(max_loss / max_profit, 2)

    # 4. Probability of Profit (POP) Calculation
    atm_iv = legs[0].iv if legs else 0.15
    sigma_t = atm_iv * math.sqrt(max(1e-4, time_to_expiry))
    drift = (risk_free_rate - 0.5 * atm_iv * atm_iv) * time_to_expiry

    def _prob_below(k_val: float) -> float:
        """P(S_T <= k_val) under lognormal terminal distribution."""
        d = (math.log(k_val / spot_price) - drift) / sigma_t
        return _norm_cdf(d)

    if len(breakevens) == 1:
        be = breakevens[0]
        p_below = _prob_below(be)
        if expiry_pnls[-1] > 0:  # Bullish strategy (profit above BE)
            pop = (1.0 - p_below) * 100.0
        else:  # Bearish strategy (profit below BE)
            pop = p_below * 100.0
    elif len(breakevens) >= 2:
        be_low = min(breakevens)
        be_high = max(breakevens)
        prob_between = max(0.0, _prob_below(be_high) - _prob_below(be_low)) * 100.0

        # Check if inside is profit (e.g. Iron Condor) or outside is profit (e.g. Straddle)
        mid_idx = num_points // 2
        if expiry_pnls[mid_idx] > 0:
            pop = prob_between
        else:
            pop = 100.0 - prob_between
    else:
        pop = 50.0

    pop_clamped = round(max(5.0, min(95.0, pop)), 1)

    return StrategyAnalytics(
        payoff_curve=payoff_curve,
        net_premium=round(net_prem, 2),
        max_profit=max_profit,
        max_loss=max_loss,
        breakevens=breakevens,
        risk_reward_ratio=rr_ratio,
        pop_percent=pop_clamped,
        net_delta=round(net_delta, 3),
        net_gamma=round(net_gamma, 5),
        net_theta=round(net_theta, 2),
        net_vega=round(net_vega, 2),
    )
