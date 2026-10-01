"""Fisher-MACD Confluence Strategy alias.
Points directly to app.signals.strategies.fisher_macd.strategy to ensure clean modularity
and backwards compatibility.
"""
from app.signals.strategies.fisher_macd.strategy import (
    FisherMACDConfluenceStrategy,
    _dynamic_fno_score,
)

__all__ = ["FisherMACDConfluenceStrategy", "_dynamic_fno_score"]
