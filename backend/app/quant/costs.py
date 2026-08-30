from typing import NamedTuple


class CostBreakdown(NamedTuple):
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    brokerage: float
    gst: float
    slippage: float
    total_cost: float


def calculate_option_costs(
    buy_turnover: float,
    sell_turnover: float,
    num_orders: int = 2,
    brokerage_per_order: float = 20.0,
    slippage_pct: float = 0.001,
) -> CostBreakdown:
    """Calculate realistic statutory taxes, exchange fees, brokerage, and slippage for Indian Options."""
    total_turnover = buy_turnover + sell_turnover

    # 1. STT: 0.125% on sell side premium turnover
    stt = round(sell_turnover * 0.00125, 2)

    # 2. NSE Exchange Turnover Charges: 0.05% on total premium turnover
    exchange_charges = round(total_turnover * 0.0005, 2)

    # 3. SEBI Turnover Charges: ₹10 per crore (0.0001%)
    sebi_charges = round(total_turnover * 0.000001, 2)

    # 4. Stamp Duty: 0.003% on buy turnover
    stamp_duty = round(buy_turnover * 0.00003, 2)

    # 5. Brokerage: Flat ₹20 per executed order
    brokerage = round(num_orders * brokerage_per_order, 2)

    # 6. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
    gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)

    # 7. Slippage: Adverse price movement impact
    slippage = round(total_turnover * slippage_pct, 2)

    total_cost = round(stt + exchange_charges + sebi_charges + stamp_duty + brokerage + gst + slippage, 2)

    return CostBreakdown(
        stt=stt,
        exchange_charges=exchange_charges,
        sebi_charges=sebi_charges,
        stamp_duty=stamp_duty,
        brokerage=brokerage,
        gst=gst,
        slippage=slippage,
        total_cost=total_cost,
    )
