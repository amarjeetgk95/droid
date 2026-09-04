from app.signals.strategies.base import Strategy, SignalCandidate, StrategyContext
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.strategies.mean_reversion import MeanReversionStrategy
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.gamma_squeeze import GammaSqueezeStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy
from app.signals.strategies.vwap_scalp import VWAPScalpStrategy
from app.signals.strategies.micro_momentum import MicroMomentumStrategy
from app.signals.strategies.ema_ribbon import EMARibbonScalpStrategy
from app.signals.strategies.gamma_spike import GammaSpikeStrategy

INTRADAY_STRATEGIES: dict[str, Strategy] = {
    "BREAKOUT": BreakoutStrategy(),
    "MEAN_REVERSION": MeanReversionStrategy(),
    "TREND_PULLBACK": TrendPullbackStrategy(),
    "GAMMA_SQUEEZE": GammaSqueezeStrategy(),
    "ORB": OpeningRangeBreakoutStrategy(),
}

SCALP_STRATEGIES: dict[str, Strategy] = {
    "VWAP_SCALP": VWAPScalpStrategy(),
    "MICRO_MOMENTUM": MicroMomentumStrategy(),
    "EMA_RIBBON": EMARibbonScalpStrategy(),
    "GAMMA_SPIKE": GammaSpikeStrategy(),
}

STRATEGY_REGISTRY: dict[str, Strategy] = {
    **INTRADAY_STRATEGIES,
    **SCALP_STRATEGIES,
}

SCALP_STRATEGY_NAMES = set(SCALP_STRATEGIES.keys())
INTRADAY_STRATEGY_NAMES = set(INTRADAY_STRATEGIES.keys())

