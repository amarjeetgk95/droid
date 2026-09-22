"""S8 Configuration & Parameter Definitions (S8SPEC_v1.0).

Pre-registered, immutable configuration schemas for DROID Strategy S8:
IV Regime Mispricing (Volatility Regime Trading).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class S8RegimeConfig:
    """Implied vs Realized Volatility regime classification parameters."""
    iv_rv_compression_threshold: float = 0.85   # IV/RV < 0.85 = vol is cheap relative to movement
    iv_rv_expansion_threshold: float = 1.30     # IV/RV > 1.30 = vol is expensive relative to movement
    iv_pct_compression_max: float = 30.0        # IV Percentile < 30 = cheap vol rank
    iv_pct_expansion_min: float = 70.0          # IV Percentile > 70 = expensive vol rank
    vix_crush_threshold: float = 12.0
    vix_spike_threshold: float = 22.0


@dataclass(frozen=True)
class S8DirectionalConfig:
    """Directional bias confirmation filters."""
    min_adx: float = 18.0
    require_ema_alignment: bool = True
    require_ema_slope: bool = True


@dataclass(frozen=True)
class S8ExitConfig:
    """Exit barrier parameters for option buying and spread selling."""
    buy_stop_pct: float = 0.40
    buy_target_pct: float = 0.80
    buy_t_max_bars: int = 30
    sell_stop_spread_pct: float = 0.70
    sell_target_credit_pct: float = 0.50
    k_sl_atr: float = 1.0
    k_tp_atr: float = 2.0


@dataclass(frozen=True)
class S8LimitsConfig:
    """Session windows and frequency limits."""
    regime_a_window_start: str = "09:45"
    regime_a_window_end: str = "11:30"
    regime_b_window_start: str = "11:30"
    regime_b_window_end: str = "14:15"
    max_trades_per_day: int = 2
    cooldown_bars: int = 15


@dataclass(frozen=True)
class S8Config:
    """Master configuration container for Strategy S8."""
    strategy_id: str = "S8"
    spec_version: str = "S8SPEC_v1.0"
    regime: S8RegimeConfig = field(default_factory=S8RegimeConfig)
    directional: S8DirectionalConfig = field(default_factory=S8DirectionalConfig)
    exit: S8ExitConfig = field(default_factory=S8ExitConfig)
    limits: S8LimitsConfig = field(default_factory=S8LimitsConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def parameter_hash(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def create_s8_default_config(**overrides: Any) -> S8Config:
    """Canonical factory for S8Config with optional section overrides."""
    kwargs: Dict[str, Any] = {}
    if "regime" in overrides:
        kwargs["regime"] = overrides.pop("regime")
    if "directional" in overrides:
        kwargs["directional"] = overrides.pop("directional")
    if "exit" in overrides:
        kwargs["exit"] = overrides.pop("exit")
    if "limits" in overrides:
        kwargs["limits"] = overrides.pop("limits")
    kwargs.update(overrides)
    return S8Config(**kwargs)
