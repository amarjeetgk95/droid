"""
Base interface and abstractions for Swing Trading Strategies (v5.0 §6).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional
from app.swing.models import SwingSetup, MarketRegime, SectorClassification
from app.swing.technical import SwingFeatures


class BaseSwingStrategy(ABC):
    strategy_id: str
    strategy_name: str

    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        sector: str,
        features: SwingFeatures,
        candles: list[dict[str, Any]],
        regime: MarketRegime,
        sector_status: SectorClassification,
        portfolio_equity: float = 1_000_000.0,
    ) -> Optional[SwingSetup]:
        """
        Evaluates technical features and generates a SwingSetup if rules pass.
        Returns None if conditions are not met or if abstained.
        """
        pass
