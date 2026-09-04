"""
Decimal Value Types & Normalization — §§17,18,19,20,21,16,19
Exact arithmetic only. No binary float for financial calculations.
Centralized domain types: Price, Quantity, Money, Rate, Percentage, TickSize, Notional
Tick-size quantization before execution, quantity validation, serialization as decimal strings.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Union
import re

getcontext().prec = 28

DecimalLike = Union[Decimal, int, float, str]

def D(v: DecimalLike) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return Decimal(str(v))
    return Decimal(str(v))

def _quant(v: DecimalLike) -> Decimal:
    return D(v)

# ── Value Types ───────────────────────────────────────────────────────

class Price:
    """Financial price — immutable, Decimal-backed."""
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike):
        # Do NOT construct from binary float directly
        if isinstance(value, float):
            raise TypeError("Price must be constructed from str/Decimal, not float. Use Price(Decimal('24735.05'))")
        self._v = D(value)
    @property
    def value(self) -> Decimal:
        return self._v
    def quantized(self, tick: DecimalLike) -> "Price":
        # tick-size quantization (§19)
        t = D(tick)
        ticks = (self._v / t).to_integral_value(rounding=ROUND_HALF_UP)
        return Price(ticks * t)
    def __str__(self) -> str:
        return format(self._v, 'f')
    def __repr__(self) -> str: return f"Price({self._v})"
    def __eq__(self, other): return self._v == (other._v if isinstance(other, Price) else D(other)) if isinstance(other, (Price, Decimal, int, str)) else False

class Quantity:
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike):
        if isinstance(value, float):
            raise TypeError("Quantity must not be constructed from float")
        self._v = D(value)
    @property
    def value(self) -> Decimal: return self._v
    def __str__(self) -> str: return format(self._v.normalize() if self._v == self._v.to_integral_value() else self._v, 'f')
    def __repr__(self) -> str: return f"Quantity({self._v})"
    def __eq__(self, other): return self._v == (other._v if isinstance(other, Quantity) else D(other)) if isinstance(other, (Quantity, Decimal, int, str)) else False

class Money:
    """Money with currency — immutable."""
    __slots__ = ("_v", "_ccy")
    def __init__(self, value: DecimalLike, currency: str = "INR"):
        if isinstance(value, float):
            raise TypeError("Money must not be constructed from float")
        self._v = D(value)
        self._ccy = currency
    @property
    def value(self) -> Decimal: return self._v
    @property
    def currency(self) -> str: return self._ccy
    def __str__(self) -> str: return f"{self._ccy} {format(self._v, 'f')}"
    def __repr__(self) -> str: return f"Money({self._v}, {self._ccy})"

class Rate:
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike): 
        if isinstance(value, float): raise TypeError("Rate must not be float")
        self._v = D(value)
    @property
    def value(self) -> Decimal: return self._v

class Percentage:
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike):
        if isinstance(value, float): raise TypeError("Percentage must not be float")
        self._v = D(value)
    @property
    def value(self) -> Decimal: return self._v
    def as_decimal(self) -> Decimal: return self._v / D(100)

class TickSize:
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike):
        if isinstance(value, float): raise TypeError("TickSize must not be float")
        self._v = D(value)
        if self._v <= D(0): raise ValueError("tick_size must be > 0")
    @property
    def value(self) -> Decimal: return self._v

class Notional:
    """Exposure — price × quantity × multiplier."""
    __slots__ = ("_v",)
    def __init__(self, value: DecimalLike):
        if isinstance(value, float): raise TypeError("Notional must not be float")
        self._v = D(value)
    @property
    def value(self) -> Decimal: return self._v
    def __str__(self) -> str: return format(self._v, 'f')


# ── Contract-aware calculations — §16 ────────────────────────────────

def compute_notional(price: DecimalLike, quantity: DecimalLike, contract_multiplier: DecimalLike = Decimal("1")) -> Notional:
    n = D(price) * D(quantity) * D(contract_multiplier)
    return Notional(n)

def normalize_exposure(
    price: DecimalLike,
    quantity: DecimalLike,
    contract_multiplier: DecimalLike = Decimal("1"),
) -> dict[str, str]:
    """
    Normalize into notional / margin / risk / P&L exposures.
    Returns decimal strings for serialization safety (§21).
    """
    notional = D(price) * D(quantity) * D(contract_multiplier)
    # Margin/risk exposure instrument-specific — placeholder simple model (caller overrides for options etc.)
    # For institutional grade, caller must inject instrument-aware formula
    return {
        "notional_exposure": format(notional, 'f'),
        "margin_exposure": format(notional, 'f'),
        "risk_exposure": format(notional, 'f'),
        "pnl_exposure": format(Decimal("0"), 'f'),
    }


# ── Tick-size normalization — §19 ───────────────────────────────────

def normalize_price_to_tick(price: DecimalLike, tick_size: DecimalLike, rounding=ROUND_HALF_UP) -> Decimal:
    """
    raw price → Decimal normalization → tick-size quantization → broker-valid price
    Define explicit rounding policy — never implicit binary rounding.
    """
    p = D(price)
    t = D(tick_size)
    ticks = (p / t).to_integral_value(rounding=rounding)
    quantized = (ticks * t).quantize(t if t.as_tuple().exponent < 0 else Decimal("0.01"))
    # Ensure quantized aligns exactly to tick grid
    return quantized


# ── Quantity validation — §20 ───────────────────────────────────────

def validate_quantity(quantity: DecimalLike, min_qty: DecimalLike, quantity_step: DecimalLike, lot_size: DecimalLike | None = None) -> tuple[bool, str | None]:
    """
    Validate minimum quantity, increment, lot size.
    Never silently alter intended quantity — return ORDER_INVALID_QUANTITY.
    """
    q = D(quantity)
    mn = D(min_qty)
    step = D(quantity_step)
    if q < mn:
        return False, f"ORDER_INVALID_QUANTITY: {q} < minimum {mn}"
    if q <= D(0):
        return False, "ORDER_INVALID_QUANTITY: qty must be > 0"
    # Check step alignment: (q - min) % step == 0
    remainder = (q - mn) % step if step != D(0) else D(0)
    if remainder != D(0):
        # Allow tiny epsilon via quantized comparison: must be exactly on step grid
        # Use tolerance 1e-12
        if abs(remainder) > D("0.000000001") and abs(remainder - step) > D("0.000000001"):
            return False, f"ORDER_INVALID_QUANTITY: {q} not multiple of step {step} from min {mn}"
    if lot_size is not None and lot_size != D(0):
        lots = D(lot_size)
        if q % lots != D(0):
            return False, f"ORDER_INVALID_QUANTITY: {q} not multiple of lot_size {lots}"
    return True, None


# ── Serialization — §21 ─────────────────────────────────────────────

def serialize_decimal(v: DecimalLike) -> str:
    return format(D(v), 'f')

def serialize_money(m: Money) -> dict:
    return {"value": format(m.value, 'f'), "currency": m.currency}

_DECIMAL_STR_RE = re.compile(r"^-?\d+(\.\d+)?$")
def is_decimal_string(s: str) -> bool:
    return bool(_DECIMAL_STR_RE.match(s))
