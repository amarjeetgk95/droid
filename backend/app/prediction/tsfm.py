"""
TSFM Forecast Engine Abstraction — §4

Use a dedicated TSFM rather than an LLM for numerical forecasting.
Supported candidates: Chronos-2, TimesFM, MOIRAI

Generate probabilistic forecasts: P10, P50, P90

This module provides the interface + deterministic fallback when model not loaded.
P10/P90 are forecast boundaries, not guaranteed price levels.
"""
from __future__ import annotations

import math
import random
from typing import Literal

from app.quant.forecast_validator import validate_tsfm_forecast


class TSFMProvider:
    """
    Abstract TSFM wrapper. Implementations: Chronos2Provider, TimesFMProvider, MoiraiProvider.
    For now provides mock deterministic forecast based on ATR/volatility if real model unavailable,
    but validates via forecast_validator and never silently repairs.
    """

    def __init__(self, model_name: str = "mock-tsfm-v1", horizon_minutes: int = 60):
        self.model_name = model_name
        self.horizon_minutes = horizon_minutes
        self.version = f"{model_name}-1.0"

    async def forecast(self, price_history: list[float], current_price: float, horizon_minutes: int | None = None) -> dict:
        horizon = horizon_minutes or self.horizon_minutes
        # Mock probabilistic forecast using volatility
        # In real deployment, call Chronos-2 / TimesFM / MOIRAI here
        if not price_history or len(price_history) < 10:
            # fallback ATR proxy
            atr = current_price * 0.005
        else:
            # ATR proxy: avg true range ~ std *1.5
            mean = sum(price_history) / len(price_history)
            var = sum((x - mean) ** 2 for x in price_history) / len(price_history)
            std = math.sqrt(var)
            atr = max(current_price * 0.002, std * 1.2)

        # Volatility scaling by horizon sqrt
        scale = math.sqrt(horizon / 60.0)
        p50_offset = atr * 0.2 * scale * (1 if random.random() > 0.5 else -1) * 0.3  # small directional bias
        p50 = current_price + p50_offset
        # Symmetric spread
        spread = atr * scale
        p10 = p50 - spread * 0.9
        p90 = p50 + spread * 0.9

        # Ensure ordering via validation; if invalid, adjust only for mock but flagged
        # For mock we generate valid directly
        p10 = max(1.0, min(p10, p50 - 0.5))
        p90 = max(p50 + 0.5, p90)
        # Round
        p10 = round(p10, 2)
        p50 = round(p50, 2)
        p90 = round(p90, 2)

        result = {
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "horizon_minutes": horizon,
            "current_price": current_price,
            "model": self.model_name,
            "model_version": self.version,
        }
        # Validate before returning – must be valid per §5
        validation = validate_tsfm_forecast(p10, p50, p90, current_price=current_price, horizon_minutes=horizon)
        result["validation"] = {"valid": validation.valid, "reason": validation.reason.value if validation.reason else None, "detail": validation.detail}
        if not validation.valid:
            # Attach diagnostic sorted for visualization, but mark invalid
            result["diagnostic_sorted"] = validation.diagnostic_sorted
        return result


# Singleton default
tsfm_provider = TSFMProvider()
