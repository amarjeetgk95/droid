"""Baseline prediction models for benchmark comparison (§20).

Used by the cheap validation gate to test whether an indicator delivers
statistically meaningful edge beyond trivial or naive strategies.
"""

import random
from typing import List, Dict, Any
from app.research.enums import Direction


class BaselineModel:
    """Base class for validation baselines."""

    def predict(self, past_candles: List[Dict[str, Any]]) -> Direction:
        raise NotImplementedError


class RandomBaseline(BaselineModel):
    """50/50 Bernoulli coin toss baseline."""

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def predict(self, past_candles: List[Dict[str, Any]]) -> Direction:
        return Direction.BULLISH if self._rng.random() >= 0.5 else Direction.BEARISH


class NaiveMomentumBaseline(BaselineModel):
    """Predicts continuation of the most recent candle direction."""

    def predict(self, past_candles: List[Dict[str, Any]]) -> Direction:
        if len(past_candles) < 2:
            return Direction.NEUTRAL
        prev_close = float(past_candles[-2]["close"])
        curr_close = float(past_candles[-1]["close"])
        if curr_close > prev_close:
            return Direction.BULLISH
        elif curr_close < prev_close:
            return Direction.BEARISH
        return Direction.NEUTRAL


class BuyAndHoldBaseline(BaselineModel):
    """Always predicts Bullish."""

    def predict(self, past_candles: List[Dict[str, Any]]) -> Direction:
        return Direction.BULLISH
