"""Enumerations shared by the Indicator Research module."""

from __future__ import annotations

from enum import Enum


class IndicatorCategory(str, Enum):
    """Research taxonomy (§5). Ordering here drives the UI filter order."""

    MOMENTUM = "Momentum"
    TREND = "Trend"
    VOLATILITY = "Volatility"
    CYCLE = "Cycle"
    VOLUME = "Volume"
    PRICE_ACTION = "Price Action"
    ORDER_FLOW = "Order Flow"
    MEAN_REVERSION = "Mean Reversion"
    HYBRID = "Hybrid"
    MACHINE_LEARNING = "Machine Learning"
    CUSTOM = "Custom"

    @classmethod
    def ui_order(cls) -> list["IndicatorCategory"]:
        return list(cls)


class OutputType(str, Enum):
    """The four supported output shapes (§6)."""

    OSCILLATOR = "oscillator"
    OVERLAY = "overlay"
    MULTI_OUTPUT = "multi_output"
    SIGNAL_ONLY = "signal_only"


class OutputRole(str, Enum):
    """How a single output series should be rendered."""

    LINE = "line"
    HISTOGRAM = "histogram"
    AREA = "area"
    MARKER = "marker"
    BAND_UPPER = "band_upper"
    BAND_LOWER = "band_lower"
    BAND_MIDDLE = "band_middle"


class PaneHint(str, Enum):
    """Where an output belongs on the research chart."""

    PRICE = "price"
    SEPARATE = "separate"
    NONE = "none"


class ParameterType(str, Enum):
    """Parameter control types the frontend auto-renders from metadata."""

    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    STRING = "string"


class LogicOperator(str, Enum):
    """Logical combinators for nested rule groups."""

    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class RuleOperator(str, Enum):
    """Comparison operators usable inside a signal condition (§8).

    Semantics are documented exhaustively in ``signals.rules``; every operator
    only ever reads ``t`` and strictly earlier bars.
    """

    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    EQ = "=="
    NEQ = "!="
    CROSSES_ABOVE = "crosses_above"
    CROSSES_BELOW = "crosses_below"
    TURNS_UP = "turns_up"
    TURNS_DOWN = "turns_down"
    IN_RANGE = "in_range"
    OUTSIDE_RANGE = "outside_range"
    SLOPE_UP = "slope_up"
    SLOPE_DOWN = "slope_down"


class EntryFill(str, Enum):
    """Signal execution model (§11).

    ``NEXT_OPEN`` is the research default and the only fill that is impossible
    to overstate: a signal confirmed by the close of bar ``t`` is filled at the
    open of bar ``t+1``. ``SIGNAL_CLOSE`` reproduces the optimistic — and often
    unattainable — "fill at the close that produced the signal" assumption. It
    is supported for explicit A/B testing and is always labelled as such.
    """

    NEXT_OPEN = "next_open"
    SIGNAL_CLOSE = "signal_close"


class ExitReason(str, Enum):
    """Why a position was closed."""

    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    MAX_BARS = "max_bars"
    OPPOSITE_SIGNAL = "opposite_signal"
    SESSION_CLOSE = "session_close"
    END_OF_DATA = "end_of_data"


class PositionSide(str, Enum):
    """Direction of an open trade."""

    LONG = "LONG"
    SHORT = "SHORT"


class StopMode(str, Enum):
    """How stop-loss / take-profit distances are expressed."""

    NONE = "none"
    PERCENT = "percent"
    ATR = "atr"
    POINTS = "points"


class SizeMode(str, Enum):
    """Position sizing for the equity curve."""

    FIXED_FRACTION = "fixed_fraction"
    FIXED_UNITS = "fixed_units"


class DataAvailability(str, Enum):
    """Honest availability of a requested candle series."""

    AVAILABLE = "available"
    DATASET_MISSING = "dataset_missing"
    EMPTY_RANGE = "empty_range"
    PROVIDER_ERROR = "provider_error"


class OrderFlowProvenance(str, Enum):
    """Provenance and reliability of order flow and microstructure data."""

    REAL = "REAL"
    PROXY = "PROXY"
    UNAVAILABLE = "UNAVAILABLE"


class SampleSizeFlag(str, Enum):
    """Statistical sample size adequacy tier."""

    SUFFICIENT = "SUFFICIENT"
    MARGINAL = "MARGINAL"
    INSUFFICIENT = "INSUFFICIENT"

