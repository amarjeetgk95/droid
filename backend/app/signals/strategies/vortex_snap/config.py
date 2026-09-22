"""
Configuration parameters for VORTEX-SNAP Strategy Engine (§2 Principle 16).

All parameters are dataclasses/Pydantic models with explicit types,
documented defaults, and zero hardcoded magic numbers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class SessionConfig(BaseModel):
    """Trading session configuration (§4)."""
    timezone: str = "Asia/Kolkata"
    market_open_time: str = "09:15"
    opening_range_end: str = "09:45"
    normal_intraday_end: str = "14:45"
    forced_square_off_time: str = "15:15"
    market_close_time: str = "15:30"
    no_trade_windows: List[Tuple[str, str]] = Field(
        default_factory=lambda: [("09:15", "09:20"), ("15:15", "15:30")]
    )


class StructuralLevelConfig(BaseModel):
    """Structural Level Map configuration (§5)."""
    relevance_decay_half_life_points: float = 120.0
    retest_tolerance_pct: float = 0.0018  # 0.18% band for retest validation
    touch_tolerance_pct: float = 0.0012   # 0.12% band for touch
    swing_window_5m: int = 5              # 5 bars on 5m = 25m swing pivots
    max_levels_tracked: int = 25
    broken_retention_bars: int = 30       # Retain broken level for potential reclaim/test


class CompressionConfig(BaseModel):
    """Compression Engine parameters (§6)."""
    atr_short_period: int = 5
    atr_long_period: int = 20
    realized_vol_window: int = 20
    overlap_window: int = 5
    contraction_window: int = 10
    entropy_window: int = 10
    displacement_window: int = 10
    uncompressed_threshold: float = 0.55
    watch_threshold: float = 0.55
    armed_threshold: float = 0.70
    extreme_threshold: float = 0.85


class DirectionalPressureConfig(BaseModel):
    """Directional Pressure Engine parameters (§7)."""
    pressure_window: int = 10
    ema_alpha: float = 0.25
    scale_window: int = 20
    persistence_threshold: int = 3
    epsilon: float = 1e-9


class TranslationRatioConfig(BaseModel):
    """Translation Ratio Engine parameters (§8) - PRIMARY HYPOTHESIS."""
    reference_lookback_bars: int = 5
    volatility_scale_bars: int = 20
    pressure_scale_bars: int = 20
    high_translation_threshold: float = 1.25
    low_translation_threshold: float = 0.45
    high_pressure_threshold: float = 0.60
    epsilon: float = 1e-9


class AbsorptionConfig(BaseModel):
    """Absorption Detector parameters (§9)."""
    min_volume_shock: float = 1.5
    min_pressure_score: float = 0.60
    max_translation_score: float = 0.40
    min_rejection_wick_ratio: float = 0.45
    level_interaction_tolerance_pct: float = 0.0020
    failure_extend_bars: int = 2


class LiquidityVacuumConfig(BaseModel):
    """Liquidity Vacuum Detector parameters (§10)."""
    min_range_expansion: float = 1.45
    min_volume_shock: float = 1.35
    close_location_bull_min: float = 0.70
    close_location_bear_max: float = 0.30
    max_overlap_penalty: float = 0.45
    prior_compression_threshold: float = 0.65


class SnapEnergyConfig(BaseModel):
    """Snap Energy Composite parameters (§11)."""
    min_compression_duration: int = 3
    duration_saturation_bars: int = 15
    consistency_weight: float = 0.35
    energy_explosive_threshold: float = 0.82


class MarketRegimeConfig(BaseModel):
    """Market Regime Engine parameters (§19)."""
    adx_period: int = 14
    trend_adx_threshold: float = 22.0
    efficiency_trend_threshold: float = 0.55
    efficiency_range_threshold: float = 0.30
    volatility_expansion_ratio: float = 1.35
    exhaustion_volume_shock: float = 2.2
    chaotic_entropy_threshold: float = 0.75


class DataConfig(BaseModel):
    """Market data sourcing policy for the engine."""
    require_real_data: bool = False
    strict_mode_env: str = "VORTEX_SNAP_REQUIRE_REAL_DATA"
    synthetic_note: str = "Simulated seed-42 intraday session (no real 1m parquet found). Levels and gauges do NOT reflect live prices."


class InstrumentOverrides(BaseModel):
    """Instrument-specific parameter tuning."""
    relevance_decay_half_life_points: Optional[float] = None
    retest_tolerance_pct: Optional[float] = None
    high_translation_threshold: Optional[float] = None
    low_translation_threshold: Optional[float] = None


class VortexSnapConfig(BaseModel):
    """Master configuration container for VORTEX-SNAP."""
    version: str = "1.0.0"
    session: SessionConfig = Field(default_factory=SessionConfig)
    structural_levels: StructuralLevelConfig = Field(default_factory=StructuralLevelConfig)
    compression: CompressionConfig = Field(default_factory=CompressionConfig)
    pressure: DirectionalPressureConfig = Field(default_factory=DirectionalPressureConfig)
    translation: TranslationRatioConfig = Field(default_factory=TranslationRatioConfig)
    absorption: AbsorptionConfig = Field(default_factory=AbsorptionConfig)
    vacuum: LiquidityVacuumConfig = Field(default_factory=LiquidityVacuumConfig)
    snap_energy: SnapEnergyConfig = Field(default_factory=SnapEnergyConfig)
    regime: MarketRegimeConfig = Field(default_factory=MarketRegimeConfig)
    data: DataConfig = Field(default_factory=DataConfig)

    # Instrument-level overrides (NIFTY, BANKNIFTY, SENSEX)
    instrument_overrides: Dict[str, InstrumentOverrides] = Field(
        default_factory=lambda: {
            "NIFTY": InstrumentOverrides(
                relevance_decay_half_life_points=100.0,
                retest_tolerance_pct=0.0015,
            ),
            "BANKNIFTY": InstrumentOverrides(
                relevance_decay_half_life_points=250.0,
                retest_tolerance_pct=0.0020,
            ),
            "SENSEX": InstrumentOverrides(
                relevance_decay_half_life_points=350.0,
                retest_tolerance_pct=0.0018,
            ),
        }
    )

    # Feature ablation flags (§32) - all True by default
    enable_compression: bool = True
    enable_pressure: bool = True
    enable_translation: bool = True
    enable_vacuum: bool = True
    enable_absorption: bool = True
    enable_snap_energy: bool = True
    enable_structural_levels: bool = True
    enable_regime: bool = True

    @classmethod
    def default(cls) -> VortexSnapConfig:
        return cls()


VortexSnapConfig.model_rebuild()

