from typing import Literal

InstrumentType = Literal["OPTION_BUY", "OPTION_SELL", "FUTURES"]


def calculate_required_margin(
    instrument_type: InstrumentType,
    underlying: str,
    price: float,
    quantity: int,
    is_hedged: bool = False,
) -> float:
    """Calculate realistic NSE SPAN + Exposure margin requirement for Indian F&O positions."""
    underlying_clean = underlying.upper().replace(" 50", "")

    if instrument_type == "OPTION_BUY":
        # Option buyers only pay full premium. If index spot price passed (>2000), estimate ATM premium (~1.5%)
        eff_price = price if price < 2000 else round(price * 0.015, 2)
        return round(eff_price * quantity, 2)

    # Base margin per lot for naked shorting & futures
    lot_size = 10 if "SENSEX" in underlying_clean else 25 if "BANK" in underlying_clean else 65 if "FIN" in underlying_clean else 75
    lots = max(1, quantity // lot_size)

    if "SENSEX" in underlying_clean:
        base_per_lot = 150000.0
    elif "BANK" in underlying_clean:
        base_per_lot = 145000.0
    elif "FIN" in underlying_clean:
        base_per_lot = 115000.0
    else:  # NIFTY
        base_per_lot = 125000.0

    raw_margin = base_per_lot * lots

    if instrument_type == "FUTURES":
        return round(raw_margin, 2)

    # Option Sell with hedge relief
    if is_hedged:
        return round(raw_margin * 0.40, 2)  # 60% margin benefit for hedged spreads

    return round(raw_margin, 2)
