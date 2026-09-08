"""
The 11-Strategy Portfolio (§3, §67).
Scalp Desk (5):
  S1: VWAP_SCALP
  S2: LIQUIDITY_SWEEP_RECLAIM
  S3: MICRO_MOMENTUM
  S4: MOMENTUM_REACCELERATION
  S5: GAMMA_SPIKE

Intraday Desk (6):
  I1: REGIME_ADAPTIVE_TREND
  I2: VOLATILITY_BREAKOUT
  I3: TREND_PULLBACK
  I4: ORB
  I5: MEAN_REVERSION
  I6: GAMMA_SQUEEZE
"""
from app.signals.strategies.base import Strategy, SignalCandidate, StrategyContext
from app.signals.strategies.breakout import BreakoutStrategy
from app.signals.strategies.volatility_breakout import VolatilityBreakoutStrategy
from app.signals.strategies.mean_reversion import MeanReversionStrategy
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.regime_trend import RegimeAdaptiveTrendStrategy
from app.signals.strategies.gamma_squeeze import GammaSqueezeStrategy
from app.signals.strategies.orb import OpeningRangeBreakoutStrategy
from app.signals.strategies.vwap_scalp import VWAPScalpStrategy
from app.signals.strategies.liquidity_sweep import LiquiditySweepReclaimStrategy
from app.signals.strategies.micro_momentum import MicroMomentumStrategy
from app.signals.strategies.momentum_reacceleration import MomentumReaccelerationStrategy
from app.signals.strategies.ema_ribbon import EMARibbonScalpStrategy
from app.signals.strategies.gamma_spike import GammaSpikeStrategy

# The 6 Official Intraday Desk Strategies (§3)
INTRADAY_STRATEGIES: dict[str, Strategy] = {
    "REGIME_ADAPTIVE_TREND": RegimeAdaptiveTrendStrategy(),
    "VOLATILITY_BREAKOUT": VolatilityBreakoutStrategy(),
    "TREND_PULLBACK": TrendPullbackStrategy(),
    "ORB": OpeningRangeBreakoutStrategy(),
    "MEAN_REVERSION": MeanReversionStrategy(),
    "GAMMA_SQUEEZE": GammaSqueezeStrategy(),
}

# The 5 Official Scalp Desk Strategies (§3)
SCALP_STRATEGIES: dict[str, Strategy] = {
    "VWAP_SCALP": VWAPScalpStrategy(),
    "LIQUIDITY_SWEEP_RECLAIM": LiquiditySweepReclaimStrategy(),
    "MICRO_MOMENTUM": MicroMomentumStrategy(),
    "MOMENTUM_REACCELERATION": MomentumReaccelerationStrategy(),
    "GAMMA_SPIKE": GammaSpikeStrategy(),
}

# Complete Registry with backward compatibility aliases
STRATEGY_REGISTRY: dict[str, Strategy] = {
    **INTRADAY_STRATEGIES,
    **SCALP_STRATEGIES,
    "BREAKOUT": BreakoutStrategy(),            # Legacy alias to VOLATILITY_BREAKOUT
    "EMA_RIBBON": EMARibbonScalpStrategy(),    # Legacy strategy alias (logic also in features/ema_features.py)
}

SCALP_STRATEGY_NAMES = set(SCALP_STRATEGIES.keys())
INTRADAY_STRATEGY_NAMES = set(INTRADAY_STRATEGIES.keys())
