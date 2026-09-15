"""
Base interface and abstractions for Options Swing Trading Strategies (v6.0 §6).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from app.swing.models import SwingSetup, MarketRegime
from app.swing.technical import SwingFeatures


class BaseSwingStrategy(ABC):
    strategy_id: str
    strategy_name: str

    @abstractmethod
    def evaluate(
        self,
        underlying: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        portfolio_equity: float = 1_000_000.0,
        spot_price: float = 0.0,
        options_chain: Optional[Any] = None,
        current_iv: float = 0.16,
        iv_percentile: float = 50.0,
    ) -> Optional[SwingSetup]:
        """
        Evaluates technical features on the underlying, runs quantitative contract selection,
        and generates a SwingSetup with four-layer validity.
        Returns None if conditions are not met or if abstained.
        """
        pass

