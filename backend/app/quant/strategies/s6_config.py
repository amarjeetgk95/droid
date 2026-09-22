"""S6 Configuration & Parameter Definitions (S6SPEC_v1.3).

Pre-registered, immutable configuration schemas for DROID Signature Strategy S6.
Guarantees frozen parameter integrity and deterministic SHA-256 configuration hashing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict


class S6TimeframeBranch(str, Enum):
    T1_5M_1M = "T1_5M_1M"    # 5m context + 1m structural breakout + 1m execution
    T4_5M_5M = "T4_5M_5M"    # 5m context + 5m structural breakout + 5m execution


class S6Variant(str, Enum):
    S6_A = "S6-A"    # Core expansion continuation
    S6_F = "S6-F"    # Failed-breakout reversal


@dataclass(frozen=True)
class S6RegimeConfig:
    unstable_range_atr: float = 3.0
    adx_trend_min: float = 22.0
    atr_pctile_high: float = 90.0
    atr_pctile_low: float = 10.0
    adx_period: int = 14
    atr_period: int = 14
    ema_fast_period: int = 20
    ema_slow_period: int = 50


@dataclass(frozen=True)
class S6CompressionConfig:
    atr_ratio_max: float = 0.85
    range_ratio_max: float = 3.0
    persistence_bars: int = 3
    armed_lifetime_bars: int = 12
    max_lifetime_bars: int = 36
    invalidation_outside_atr: float = 0.50
    range_lookback_bars: int = 6
    atr_median_lookback_bars: int = 100


@dataclass(frozen=True)
class S6BreakoutConfig:
    min_breakout_distance_atr: float = 0.10
    volume_ratio_min: float = 1.30
    volume_lookback: int = 20
    close_location_min: float = 0.60
    min_room_atr: float = 1.50
    require_directional_close: bool = True


@dataclass(frozen=True)
class S6FailureConfig:
    reentry_distance_atr: float = 0.10
    max_monitoring_bars: int = 5
    stop_buffer_atr: float = 0.25
    stop_cap_atr: float = 2.0
    target_atr: float = 2.0


@dataclass(frozen=True)
class S6ExitConfig:
    k_sl: float = 1.5
    k_tp: float = 2.5
    time_barrier_bars: int = 15
    force_flat_time: str = "15:15"


@dataclass(frozen=True)
class S6SimulationConfig:
    slippage_atr: float = 0.05
    same_bar_tie_break: str = "SL_FIRST"
    adverse_gap_fill: str = "BAR_OPEN"
    favorable_gap_fill: str = "TP_PRICE"


@dataclass(frozen=True)
class S6LimitsConfig:
    entry_from: str = "09:45"
    entry_to: str = "14:30"
    max_trades_per_day: int = 4
    cooldown_bars: int = 10
    max_positions_per_instrument: int = 1
    timezone: str = "Asia/Kolkata"


@dataclass(frozen=True)
class S6Config:
    strategy_id: str = "S6"
    spec_version: str = "S6SPEC_v1.3"
    strategy_version: str = "S6A_v1.0"
    variant: S6Variant = S6Variant.S6_A
    timeframe_branch: S6TimeframeBranch = S6TimeframeBranch.T1_5M_1M
    instrument: str = "NIFTY"
    regime: S6RegimeConfig = field(default_factory=S6RegimeConfig)
    compression: S6CompressionConfig = field(default_factory=S6CompressionConfig)
    breakout: S6BreakoutConfig = field(default_factory=S6BreakoutConfig)
    failure: S6FailureConfig = field(default_factory=S6FailureConfig)
    exit: S6ExitConfig = field(default_factory=S6ExitConfig)
    simulation: S6SimulationConfig = field(default_factory=S6SimulationConfig)
    limits: S6LimitsConfig = field(default_factory=S6LimitsConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "spec_version": self.spec_version,
            "strategy_version": self.strategy_version,
            "variant": self.variant.value,
            "timeframe_branch": self.timeframe_branch.value,
            "instrument": self.instrument,
            "regime": asdict(self.regime),
            "compression": asdict(self.compression),
            "breakout": asdict(self.breakout),
            "failure": asdict(self.failure),
            "exit": asdict(self.exit),
            "simulation": asdict(self.simulation),
            "limits": asdict(self.limits),
        }

    @property
    def parameter_hash(self) -> str:
        data = self.to_dict()
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def create_default_config(
    variant: S6Variant = S6Variant.S6_A,
    timeframe_branch: S6TimeframeBranch = S6TimeframeBranch.T1_5M_1M,
    instrument: str = "NIFTY",
) -> S6Config:
    """Factory to create canonical frozen S6Config instances."""
    version = "S6A_v1.0" if variant == S6Variant.S6_A else "S6F_v1.0"
    return S6Config(
        strategy_id="S6",
        spec_version="S6SPEC_v1.3",
        strategy_version=version,
        variant=variant,
        timeframe_branch=timeframe_branch,
        instrument=instrument,
    )
