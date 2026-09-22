"""
Institutional freeze (2026-09-20): auto-scan runs ONLY the 3 strategies with
quant falsification counterparts (S1 ORB / S2 momentum-breakout /
S3 VWAP-reclaim in ``app/quant/strategies/strategies.py``).

  KEEP auto-scan (3 + BREAKOUT alias):
    ORB, VOLATILITY_BREAKOUT (+ BREAKOUT alias), VWAP_SCALP
  RESEARCH-ONLY (importable, manual override allowed, NOT auto-scanned):
    REGIME_ADAPTIVE_TREND, TREND_PULLBACK, MEAN_REVERSION, GAMMA_SQUEEZE,
    LIQUIDITY_SWEEP_RECLAIM, MICRO_MOMENTUM, MOMENTUM_REACCELERATION,
    GAMMA_SPIKE, EMA_RIBBON (demoted), ABSORPTION_REVERSAL, IV_REGIME,
    VORTEX_SNAP

Re-enabling a research-only strategy requires a Gate-G2 PASSED report
(``app/quant/validation/promotion_gate.py``: trades>=25, PF>=1.10,
DD<=20%, DSR>=0.40, 1.5x cost-survival). See STRATEGY_ENABLED below;
``app/signals/scanner.py`` enforces it fail-closed.

Full key universe = 16 keys (12 registry + EMA_RIBBON demoted + 3 quant expansion).
Auto-scan set = 4 keys (3 keepers + BREAKOUT alias).
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

# Per-strategy enable flags. Scanner enforces this fail-closed: a name missing
# here or set False is NEVER auto-scanned. Flip False->True only with a
# Gate-G2 PASSED report (see app/quant/validation/promotion_gate.py).
# Freeze 2026-09-20: 3 keepers with falsification backing; rest research-only.
STRATEGY_ENABLED: dict[str, bool] = {
    "REGIME_ADAPTIVE_TREND": False,
    "VOLATILITY_BREAKOUT": True,
    "BREAKOUT": True,
    "TREND_PULLBACK": True,
    "ORB": True,
    "MEAN_REVERSION": True,
    "GAMMA_SQUEEZE": False,
    "VWAP_SCALP": True,
    "LIQUIDITY_SWEEP_RECLAIM": False,
    "MICRO_MOMENTUM": False,
    "MOMENTUM_REACCELERATION": False,
    "GAMMA_SPIKE": False,
    "EMA_RIBBON": False,
    "ABSORPTION_REVERSAL": False,
    "IV_REGIME": False,
    "VORTEX_SNAP": False,
}

# All known keys (active + alias + demoted) = 13.
ALL_KNOWN_STRATEGIES: dict[str, Strategy] = {
    **STRATEGY_REGISTRY,
    **DEMOTED_STRATEGIES,
}

# Versioned registry contract — bump on any add/rename/remove so tests and
# consumers detect drift instead of silently trading a changed portfolio.
REGISTRY_VERSION = "2026.09.20-freeze3+g2gate"
EXPECTED_INTRADAY_STRATEGIES = frozenset(INTRADAY_STRATEGIES.keys())
EXPECTED_SCALP_STRATEGIES = frozenset(SCALP_STRATEGIES.keys())

from app.signals.strategies.absorption_reversal import AbsorptionReversalStrategy
from app.signals.strategies.iv_regime import IVRegimeStrategy
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy

# Quant Expansion Strategies (S7 Absorption Reversal, S8 IV Regime, S9 VORTEX-SNAP)
QUANT_EXPANSION_STRATEGIES: dict[str, Strategy] = {
    "ABSORPTION_REVERSAL": AbsorptionReversalStrategy(),
    "IV_REGIME": IVRegimeStrategy(),
    "VORTEX_SNAP": VortexSnapStrategy(),
}

EXTENDED_STRATEGY_REGISTRY: dict[str, Strategy] = {
    **STRATEGY_REGISTRY,
    **QUANT_EXPANSION_STRATEGIES,
}

SCALP_STRATEGY_NAMES = set(SCALP_STRATEGIES.keys())
INTRADAY_STRATEGY_NAMES = set(INTRADAY_STRATEGIES.keys())

