"""
Financial Precision — §8

All authoritative financial calculations use exact Decimal.
Never float for price/P&L/fees/margin/capital/risk.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, getcontext
from typing import Union

# Sufficient precision for intermediate calculations
getcontext().prec = 28

DecimalLike = Union[Decimal, int, float, str]

# Canonical precision per instrument class
PRICE_QUANT = Decimal("0.01")        # paisa — 2 dp
QTY_QUANT = Decimal("1")
MARGIN_QUANT = Decimal("0.01")


def D(v: DecimalLike) -> Decimal:
    """Coerce to Decimal without float binary leakage."""
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        # float -> str -> Decimal to avoid binary artifacts
        return Decimal(str(v))
    return Decimal(str(v))


def quantize_price(p: Decimal, tick_size: Decimal | None = None) -> Decimal:
    """Quantize price to tick_size or paisa, HALF_UP."""
    q = D(tick_size) if tick_size and tick_size > 0 else PRICE_QUANT
    # Align price to nearest tick increment (round HALF_UP)
    # e.g. tick 0.05: (p / tick).quantize(1, HALF_UP) * tick
    ticks = (D(p) / q).to_integral_value(rounding=ROUND_HALF_UP)
    return (ticks * q).quantize(q)


def quantize_qty(qty: Decimal, lot_size: int | None = None) -> Decimal:
    """Floor quantity to valid lot size (never round up — §32)."""
    d = D(qty).to_integral_value(rounding=ROUND_DOWN)
    if lot_size and lot_size > 1:
        lots = (d // D(lot_size)) * D(lot_size)
        return lots
    return d


class Money:
    """Immutable Decimal money helper — always paisa quantized."""

    __slots__ = ("_value",)

    def __init__(self, value: DecimalLike):
        self._value = D(value).quantize(PRICE_QUANT, rounding=ROUND_HALF_UP)

    @property
    def value(self) -> Decimal:
        return self._value

    def __add__(self, other: "Money | DecimalLike") -> "Money":
        o = other.value if isinstance(other, Money) else D(other)
        return Money(self._value + o)

    def __sub__(self, other: "Money | DecimalLike") -> "Money":
        o = other.value if isinstance(other, Money) else D(other)
        return Money(self._value - o)

    def __mul__(self, other: DecimalLike) -> "Money":
        return Money(self._value * D(other))

    def __truediv__(self, other: DecimalLike) -> "Money":
        return Money(self._value / D(other))

    def __neg__(self) -> "Money":
        return Money(-self._value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Money):
            return self._value == other._value
        if isinstance(other, Decimal):
            return self._value == other
        return False

    def __lt__(self, other: "Money | DecimalLike") -> bool:
        o = other.value if isinstance(other, Money) else D(other)
        return self._value < o

    def __le__(self, other: "Money | DecimalLike") -> bool:
        o = other.value if isinstance(other, Money) else D(other)
        return self._value <= o

    def __gt__(self, other: "Money | DecimalLike") -> bool:
        o = other.value if isinstance(other, Money) else D(other)
        return self._value > o

    def __ge__(self, other: "Money | DecimalLike") -> bool:
        o = other.value if isinstance(other, Money) else D(other)
        return self._value >= o

    def __repr__(self) -> str:
        return f"Money({self._value})"

    def __str__(self) -> str:
        return f"₹{self._value:,.2f}"

    def to_float(self) -> float:
        return float(self._value)
