"""
The 13-key Strategy Portfolio (P1 overhaul, §3, §67).

Active scan portfolio (11 strategies):
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

Compatibility keys (2, not auto-scanned by default):
  - BREAKOUT: pointer to the shared VOLATILITY_BREAKOUT instance (duplicate
    BreakoutStrategy logic retired; single logic lives in
    volatility_breakout.py).
  - EMA_RIBBON: demoted legacy scalp (importable for back-compat, disabled by
    default, NOT in STRATEGY_REGISTRY auto-scan; scalp entry folded into
    TREND_PULLBACK context where applicable).

Full key universe = 13 keys (11 active + BREAKOUT alias + EMA_RIBBON demoted).
STRATEGY_REGISTRY (auto-scan set) = 12 keys (11 active + BREAKOUT alias).
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

# Shared single-logic breakout instance: BREAKOUT is a pointer, not a duplicate.
_SHARED_VOL_BREAKOUT = VolatilityBreakoutStrategy()

# The 6 Official Intraday Desk Strategies (§3)
INTRADAY_STRATEGIES: dict[str, Strategy] = {
    "REGIME_ADAPTIVE_TREND": RegimeAdaptiveTrendStrategy(),
    "VOLATILITY_BREAKOUT": _SHARED_VOL_BREAKOUT,
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

# Complete auto-scan registry: 11 active + BREAKOUT alias (same instance).
STRATEGY_REGISTRY: dict[str, Strategy] = {
    **INTRADAY_STRATEGIES,
    **SCALP_STRATEGIES,
    "BREAKOUT": _SHARED_VOL_BREAKOUT,  # Legacy alias -> VOLATILITY_BREAKOUT (single logic)
}

# Demoted legacy (importable for back-compat, NOT auto-scanned).
DEMOTED_STRATEGIES: dict[str, Strategy] = {
    "EMA_RIBBON": EMARibbonScalpStrategy(),
}
# Back-compat alias for the retired duplicate breakout class (single logic lives
# in VolatilityBreakoutStrategy; BreakoutStrategy delegates to it).
LEGACY_BREAKOUT_CLASS = BreakoutStrategy

# Per-strategy enable flags (P1). Scanner / callers should consult this;
# EMA_RIBBON is disabled by default (demoted).
STRATEGY_ENABLED: dict[str, bool] = {
    "REGIME_ADAPTIVE_TREND": True,
    "VOLATILITY_BREAKOUT": True,
    "BREAKOUT": True,
    "TREND_PULLBACK": True,
    "ORB": True,
    "MEAN_REVERSION": True,
    "GAMMA_SQUEEZE": True,
    "VWAP_SCALP": True,
    "LIQUIDITY_SWEEP_RECLAIM": True,
    "MICRO_MOMENTUM": True,
    "MOMENTUM_REACCELERATION": True,
    "GAMMA_SPIKE": True,
    "EMA_RIBBON": False,
}

# All known keys (active + alias + demoted) = 13.
ALL_KNOWN_STRATEGIES: dict[str, Strategy] = {
    **STRATEGY_REGISTRY,
    **DEMOTED_STRATEGIES,
}

# Versioned registry contract — bump on any add/rename/remove so tests and
# consumers detect drift instead of silently trading a changed portfolio.
REGISTRY_VERSION = "2026.09.17-11+1alias-p2"
EXPECTED_INTRADAY_STRATEGIES = frozenset(INTRADAY_STRATEGIES.keys())
EXPECTED_SCALP_STRATEGIES = frozenset(SCALP_STRATEGIES.keys())

SCALP_STRATEGY_NAMES = set(SCALP_STRATEGIES.keys())
INTRADAY_STRATEGY_NAMES = set(INTRADAY_STRATEGIES.keys())
