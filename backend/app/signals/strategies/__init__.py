from app.signals.strategies.base import Strategy, SignalCandidate, StrategyContext
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.strategies.mean_reversion import MeanReversionStrategy
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.gamma_squeeze import GammaSqueezeStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy

STRATEGY_REGISTRY: dict[str, Strategy] = {
    "BREAKOUT": BreakoutStrategy(),
    "MEAN_REVERSION": MeanReversionStrategy(),
    "TREND_PULLBACK": TrendPullbackStrategy(),
    "GAMMA_SQUEEZE": GammaSqueezeStrategy(),
    "ORB": OpeningRangeBreakoutStrategy(),
}
