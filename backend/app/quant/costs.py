"""Statutory Cost and Execution Friction Engine for Indian Markets (Tier 0).

Accurately models:
- STT (Securities Transaction Tax) on Indian Equity Derivatives (NSE & BSE)
- Exchange turnover charges (BSE for SENSEX, NSE for NIFTY)
- SEBI turnover fee (₹10 / crore)
- Stamp Duty (Buy turnover)
- Brokerage (Flat ₹20 / order default)
- GST (18% on Brokerage + Exchange + SEBI)
- Non-linear square-root slippage based on volume participation
- Cost Stress Testing (1.0x, 1.25x, 1.5x, 2.0x)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple, Literal, Optional

ExchangeVenue = Literal["NSE", "BSE"]
InstrumentSegment = Literal["OPTIONS", "FUTURES", "INDEX_EQUITY"]


class CostBreakdown(NamedTuple):
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    brokerage: float
    gst: float
    slippage: float
    total_cost: float
    net_drag_bps: float  # Basis points of total turnover


@dataclass
class StatutorySchedule:
    venue: ExchangeVenue
    segment: InstrumentSegment
    stt_rate_sell: float          # e.g. 0.00125 for options (0.125%), 0.0002 for futures (0.02%)
    exchange_rate: float          # e.g. 0.0005 for options (0.05%), 0.000019 for futures
    sebi_rate: float              # 0.000001 (₹10 per crore)
    stamp_duty_rate_buy: float    # 0.00003 for options (0.003%), 0.00002 for futures
    gst_rate: float               # 0.18 (18%)
    flat_brokerage: float         # ₹20 per order


# Default schedules for Indian Exchanges (Post-Budget 2024 revisions)
BSE_SENSEX_OPTIONS = StatutorySchedule(
    venue="BSE",
    segment="OPTIONS",
    stt_rate_sell=0.00125,
    exchange_rate=0.0005,
    sebi_rate=0.000001,
    stamp_duty_rate_buy=0.00003,
    gst_rate=0.18,
    flat_brokerage=20.0,
)

BSE_SENSEX_FUTURES = StatutorySchedule(
    venue="BSE",
    segment="FUTURES",
    stt_rate_sell=0.0002,
    exchange_rate=0.000019,
    sebi_rate=0.000001,
    stamp_duty_rate_buy=0.00002,
    gst_rate=0.18,
    flat_brokerage=20.0,
)

NSE_NIFTY_OPTIONS = StatutorySchedule(
    venue="NSE",
    segment="OPTIONS",
    stt_rate_sell=0.00125,
    exchange_rate=0.0005,
    sebi_rate=0.000001,
    stamp_duty_rate_buy=0.00003,
    gst_rate=0.18,
    flat_brokerage=20.0,
)


def calculate_square_root_slippage(
    order_size: float,
    available_volume: float,
    base_spread_bps: float = 2.0,
    impact_constant: float = 0.1,
) -> float:
    """Calculates non-linear market impact slippage:
    Slippage BPS = base_half_spread + impact_constant * sqrt(order_size / available_volume)
    """
    participation = max(1e-6, min(1.0, order_size / max(1.0, available_volume)))
    slippage_bps = (base_spread_bps * 0.5) + (impact_constant * math.sqrt(participation) * 100.0)
    return slippage_bps * 1e-4  # in decimal


def calculate_trade_costs(
    buy_turnover: float,
    sell_turnover: float,
    num_orders: int = 2,
    schedule: StatutorySchedule = BSE_SENSEX_OPTIONS,
    slippage_rate: float = 0.001,  # 10 bps default slippage (ASSUMPTION placeholder)
    stress_multiplier: float = 1.0,
) -> CostBreakdown:
    """Calculates granular Indian statutory charges, brokerage, and slippage under optional stress.

    Honesty: slippage_rate default (10 bps) is a PLACEHOLDER assumption, not a
    measured spread. Callers needing calibrated costs must pass explicit
    slippage and surface costs_version/assumptions downstream.
    """
    total_turnover = buy_turnover + sell_turnover

    # 1. STT on sell side turnover
    stt = (sell_turnover * schedule.stt_rate_sell) * stress_multiplier

    # 2. Exchange turnover fees
    exchange_charges = (total_turnover * schedule.exchange_rate) * stress_multiplier

    # 3. SEBI turnover fee
    sebi_charges = (total_turnover * schedule.sebi_rate) * stress_multiplier

    # 4. Stamp duty on buy side turnover
    stamp_duty = (buy_turnover * schedule.stamp_duty_rate_buy) * stress_multiplier

    # 5. Brokerage
    brokerage = (num_orders * schedule.flat_brokerage) * stress_multiplier

    # 6. GST (18% on Brokerage + Exchange + SEBI)
    gst = (brokerage + exchange_charges + sebi_charges) * schedule.gst_rate

    # 7. Slippage
    slippage = (total_turnover * slippage_rate) * stress_multiplier

    total_cost = stt + exchange_charges + sebi_charges + stamp_duty + brokerage + gst + slippage
    net_drag_bps = (total_cost / max(1.0, total_turnover)) * 10000.0

    return CostBreakdown(
        stt=round(stt, 2),
        exchange_charges=round(exchange_charges, 2),
        sebi_charges=round(sebi_charges, 2),
        stamp_duty=round(stamp_duty, 2),
        brokerage=round(brokerage, 2),
        gst=round(gst, 2),
        slippage=round(slippage, 2),
        total_cost=round(total_cost, 2),
        net_drag_bps=round(net_drag_bps, 2),
    )


class BSECostEngine:
    """BSE Statutory Cost Engine for Equity and Index Options (SENSEX)."""

    @staticmethod
    def calculate_options_cost(
        buy_turnover: float,
        sell_turnover: float,
        num_orders: int = 2,
        schedule: StatutorySchedule = BSE_SENSEX_OPTIONS,
        slippage_rate: float = 0.0,
        stress_multiplier: float = 1.0,
    ) -> CostBreakdown:
        """Calculates multi-leg options statutory costs under BSE SENSEX schedule.

        Models:
        - STT 0.125% on sell turnover
        - Exchange turnover charges 0.05%
        - SEBI turnover charges ₹10/crore
        - Stamp duty 0.003% on buy turnover
        - Brokerage ₹20 per executed order leg
        - GST 18% on (Brokerage + Exchange + SEBI)
        """
        return calculate_trade_costs(
            buy_turnover=buy_turnover,
            sell_turnover=sell_turnover,
            num_orders=num_orders,
            schedule=schedule,
            slippage_rate=slippage_rate,
            stress_multiplier=stress_multiplier,
        )


# Legacy backward-compatible signature
def calculate_option_costs(
    buy_turnover: float,
    sell_turnover: float,
    num_orders: int = 2,
    brokerage_per_order: float = 20.0,
    slippage_pct: float = 0.001,
) -> CostBreakdown:
    schedule = StatutorySchedule(
        venue="NSE",
        segment="OPTIONS",
        stt_rate_sell=0.00125,
        exchange_rate=0.0005,
        sebi_rate=0.000001,
        stamp_duty_rate_buy=0.00003,
        gst_rate=0.18,
        flat_brokerage=brokerage_per_order,
    )
    return calculate_trade_costs(
        buy_turnover=buy_turnover,
        sell_turnover=sell_turnover,
        num_orders=num_orders,
        schedule=schedule,
        slippage_rate=slippage_pct,
        stress_multiplier=1.0,
    )

