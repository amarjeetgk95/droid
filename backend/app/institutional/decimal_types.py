"""
Decimal Value Types & Normalization — Re-exports canonical implementation from app.signals.safety.decimal_types.
Maintained for backward compatibility.
"""
from app.signals.safety.decimal_types import (
    D,
    _quant,
    Price,
    Quantity,
    Money,
    Rate,
    Percentage,
    TickSize,
    Notional,
    compute_notional,
    normalize_exposure,
    normalize_price_to_tick,
    validate_quantity,
    serialize_decimal,
    serialize_money,
    is_decimal_string,
    DecimalLike,
)

__all__ = [
    "D",
    "_quant",
    "Price",
    "Quantity",
    "Money",
    "Rate",
    "Percentage",
    "TickSize",
    "Notional",
    "compute_notional",
    "normalize_exposure",
    "normalize_price_to_tick",
    "validate_quantity",
    "serialize_decimal",
    "serialize_money",
    "is_decimal_string",
    "DecimalLike",
]
