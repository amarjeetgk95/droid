"""Indicators package for Research Laboratory.

Registers all standard and proprietary indicators automatically.
"""

from app.research.indicators.macd_indicator import MACDIndicator
from app.research.indicators.momentum_indicator import MomentumIndicator
from app.research.indicators.ompi import OMPIIndicator
from app.research.indicators.rsi_indicator import RSIIndicator
from app.research.indicators.vwap_indicator import VWAPIndicator
from app.research.registry import IndicatorRegistry

# Register built-in indicators
IndicatorRegistry.register(RSIIndicator())
IndicatorRegistry.register(VWAPIndicator())
IndicatorRegistry.register(MACDIndicator())
IndicatorRegistry.register(MomentumIndicator())
IndicatorRegistry.register(OMPIIndicator())

__all__ = [
    "RSIIndicator",
    "VWAPIndicator",
    "MACDIndicator",
    "MomentumIndicator",
    "OMPIIndicator",
]
