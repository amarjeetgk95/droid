"""S7 Configuration & Parameter Definitions (S7SPEC_v1.0).

Pre-registered, immutable configuration schemas for DROID Strategy S7:
Structural Absorption Reversal.
Guarantees frozen parameter integrity and deterministic SHA-256 configuration hashing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class S7LevelConfig:
    """Structural level proximity parameters."""
    proximity_atr: float = 0.5
    level_types: tuple[str, ...] = ("PREV_DAY_HIGH", "PREV_DAY_LOW", "VWAP_UPPER", "VWAP_LOWER")


@dataclass(frozen=True)
class S7AbsorptionConfig:
    """Absorption detection parameters."""
    min_volume_ratio: float = 1.30
    max_price_displacement: float = 0.35
    min_wick_rejection: float = 0.50
    min_approach_bars: int = 2
    rsi_overbought: float = 65.0
    rsi_oversold: float = 35.0


@dataclass(frozen=True)
class S7ExitConfig:
    """Exit barrier parameters for mean-reversion."""
    k_sl: float = 0.5
    k_tp: float = 1.5
    t_max_bars: int = 20
    use_vwap_target: bool = True
    vwap_target_atr_cap: float = 1.5


@dataclass(frozen=True)
class S7LimitsConfig:
    """Session timing and trade count constraints."""
    entry_window_start: str = "09:45"
    entry_window_end: str = "14:30"
    max_trades_per_day: int = 3
    cooldown_bars: int = 10


@dataclass(frozen=True)
class S7SimulationConfig:
    """Simulation execution parameters."""
    slippage_atr: float = 0.05
    tie_break: str = "SL_FIRST"
    adverse_gap: str = "BAR_OPEN"


@dataclass(frozen=True)
class S7Config:
    """Master configuration container for Strategy S7."""
    strategy_id: str = "S7"
    spec_version: str = "S7SPEC_v1.0"
    levels: S7LevelConfig = field(default_factory=S7LevelConfig)
    absorption: S7AbsorptionConfig = field(default_factory=S7AbsorptionConfig)
    exit: S7ExitConfig = field(default_factory=S7ExitConfig)
    limits: S7LimitsConfig = field(default_factory=S7LimitsConfig)
    simulation: S7SimulationConfig = field(default_factory=S7SimulationConfig)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def parameter_hash(self) -> str:
        """Deterministic SHA-256 fingerprint of all strategy hyper-parameters."""
        raw = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def create_s7_default_config(**overrides: Any) -> S7Config:
    """Canonical factory for S7Config with optional section overrides."""
    kwargs: Dict[str, Any] = {}
    if "levels" in overrides:
        kwargs["levels"] = overrides.pop("levels")
    if "absorption" in overrides:
        kwargs["absorption"] = overrides.pop("absorption")
    if "exit" in overrides:
        kwargs["exit"] = overrides.pop("exit")
    if "limits" in overrides:
        kwargs["limits"] = overrides.pop("limits")
    if "simulation" in overrides:
        kwargs["simulation"] = overrides.pop("simulation")
    kwargs.update(overrides)
    return S7Config(**kwargs)
