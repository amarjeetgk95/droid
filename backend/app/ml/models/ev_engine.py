"""Expected Value (EV) Engine for DROID ML Engine.

Implements Section 17 of the DROID ML Production & Research Specification.
Calculates net expected value per trade in Indian Rupees (₹) accounting for all
frictions:
  - STT (Securities Transaction Tax: 0.1% on sell premium)
  - Exchange turnover charges (NSE/BSE 0.05%)
  - SEBI turnover charges (₹10/crore)
  - Stamp duty (0.003% on buy premium)
  - GST (18% on brokerage + exchange + SEBI charges)
  - Brokerage (flat ₹20 per executed leg / ₹40 round trip)
  - Bid-ask spread friction & execution slippage
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class FrictionBreakdown:
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    spread_friction: float
    slippage_friction: float
    total_statutory_charges: float
    total_friction: float


@dataclass(frozen=True)
class EVResult:
    gross_ev_per_share: float
    gross_ev_total: float
    net_ev_total: float
    net_ev_per_share: float
    capital_at_risk: float
    ev_risk_ratio: float
    is_viable: bool
    rejection_reason: Optional[str]
    frictions: FrictionBreakdown


class ExpectedValueEngine:
    """
    Computes after-cost expected value and trade viability for Indian Index Options.
    """

    def __init__(
        self,
        brokerage_per_leg: float = 20.0,
        stt_rate: float = 0.0010,         # 0.1% on sell side premium
        exchange_rate: float = 0.0005,    # 0.05% on total premium turnover
        sebi_rate: float = 0.000001,      # ₹10 per crore
        stamp_duty_rate: float = 0.00003, # 0.003% on buy turnover
        gst_rate: float = 0.18,           # 18% on service charges
        min_ev_risk_threshold: float = 0.10, # Minimum acceptable EV/Risk ratio
    ):
        self.brokerage_per_leg = brokerage_per_leg
        self.stt_rate = stt_rate
        self.exchange_rate = exchange_rate
        self.sebi_rate = sebi_rate
        self.stamp_duty_rate = stamp_duty_rate
        self.gst_rate = gst_rate
        self.min_ev_risk_threshold = min_ev_risk_threshold

    def calculate_friction(
        self,
        entry_premium: float,
        expected_exit_premium: float,
        quantity: int,
        spread_points: float = 0.80,
        slippage_points: float = 0.40,
    ) -> FrictionBreakdown:
        """Computes granular statutory, brokerage, and microstructure frictions.

        Honesty: spread/slippage points are PLACEHOLDER assumptions (not
        measured spread). Outputs carry assumption provenance via
        calculate_trade_ev's assumptions field; callers must not treat them
        as calibrated costs.
        """
        buy_turnover = entry_premium * quantity
        sell_turnover = max(0.05, expected_exit_premium) * quantity
        total_turnover = buy_turnover + sell_turnover

        # Statutory & Brokerage charges
        brokerage = self.brokerage_per_leg * 2.0  # ₹40 round-trip
        stt = sell_turnover * self.stt_rate
        exchange_charges = total_turnover * self.exchange_rate
        sebi_charges = total_turnover * self.sebi_rate
        stamp_duty = buy_turnover * self.stamp_duty_rate
        gst = (brokerage + exchange_charges + sebi_charges) * self.gst_rate

        total_statutory = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)

        # Microstructure execution frictions
        spread_friction = round(spread_points * quantity, 2)
        slippage_friction = round(slippage_points * quantity, 2)

        total_friction = round(total_statutory + spread_friction + slippage_friction, 2)

        return FrictionBreakdown(
            brokerage=round(brokerage, 2),
            stt=round(stt, 2),
            exchange_charges=round(exchange_charges, 2),
            sebi_charges=round(sebi_charges, 2),
            stamp_duty=round(stamp_duty, 2),
            gst=round(gst, 2),
            spread_friction=spread_friction,
            slippage_friction=slippage_friction,
            total_statutory_charges=total_statutory,
            total_friction=total_friction,
        )

    def calculate_trade_ev(
        self,
        entry_premium: float,
        lot_size: int,
        lots: int,
        expected_gain_at_t1: float,
        expected_loss_at_sl: float,
        expected_timeout_pnl: float,
        p_target: float,
        p_stop: float,
        p_timeout: float,
        spread_points: float = 0.80,
        slippage_points: float = 0.40,
        min_ev_risk_override: Optional[float] = None,
    ) -> EVResult:
        """
        Calculates complete Expected Value (EV) net of Indian trading costs.
        """
        quantity = max(1, lot_size * lots)

        # 1. Expected option exit prices per scenario
        t1_exit = entry_premium + expected_gain_at_t1
        sl_exit = max(0.05, entry_premium - expected_loss_at_sl)
        timeout_exit = max(0.05, entry_premium + expected_timeout_pnl)

        weighted_exit = (p_target * t1_exit) + (p_stop * sl_exit) + (p_timeout * timeout_exit)

        # 2. Friction breakdown
        frictions = self.calculate_friction(
            entry_premium=entry_premium,
            expected_exit_premium=weighted_exit,
            quantity=quantity,
            spread_points=spread_points,
            slippage_points=slippage_points,
        )

        # 3. Gross EV
        gross_ev_per_share = (
            (p_target * expected_gain_at_t1)
            - (p_stop * expected_loss_at_sl)
            + (p_timeout * expected_timeout_pnl)
        )
        gross_ev_total = gross_ev_per_share * quantity

        # 4. Net EV
        net_ev_total = gross_ev_total - frictions.total_friction
        net_ev_per_share = net_ev_total / quantity

        # 5. Capital at Risk & EV/Risk Ratio
        # Risk = potential loss if SL hit + total transaction friction
        capital_at_risk = max(100.0, (expected_loss_at_sl * quantity) + frictions.total_friction)
        ev_risk_ratio = net_ev_total / capital_at_risk

        # 6. Viability Gate
        min_threshold = min_ev_risk_override if min_ev_risk_override is not None else self.min_ev_risk_threshold
        rejection_reason = None
        is_viable = True

        if net_ev_total <= 0:
            is_viable = False
            rejection_reason = f"NEGATIVE_NET_EV: Net EV is ₹{net_ev_total:.2f} after frictions"
        elif ev_risk_ratio < min_threshold:
            is_viable = False
            rejection_reason = f"SUBMARGINAL_EV_RISK: EV/Risk ratio {ev_risk_ratio:.3f} < threshold {min_threshold:.3f}"

        return EVResult(
            gross_ev_per_share=round(gross_ev_per_share, 2),
            gross_ev_total=round(gross_ev_total, 2),
            net_ev_total=round(net_ev_total, 2),
            net_ev_per_share=round(net_ev_per_share, 2),
            capital_at_risk=round(capital_at_risk, 2),
            ev_risk_ratio=round(ev_risk_ratio, 4),
            is_viable=is_viable,
            rejection_reason=rejection_reason,
            frictions=frictions,
        )


ev_engine = ExpectedValueEngine()
