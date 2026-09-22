"""
Machine Learning Feature Vector Builder & Dataset Generator (§26).

Extracts a 22-dimensional normalized microstructure and contextual feature vector:
- 12 Microstructure factors (compression, pressure, translation, absorption, vacuum, snap energy)
- 10 Context & Macro factors (level relevance, distance, regime, vwap distance, session timing)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from app.signals.strategies.vortex_snap.types import (
    Candle,
    EventType,
    LevelType,
    MarketRegime,
    StructuralLevel,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.session import MarketSessionInfo


FEATURE_NAMES = [
    "compression_score",
    "compression_duration_norm",
    "realized_vol_percentile",
    "atr_ratio",
    "pressure_score",
    "pressure_persistence_norm",
    "pressure_acceleration",
    "translation_ratio",
    "absorption_score",
    "rejection_wick_ratio",
    "liquidity_vacuum_score",
    "snap_energy",
    "level_distance_pct",
    "level_relevance",
    "level_touch_count_norm",
    "level_type_id",
    "regime_id",
    "minutes_from_open_norm",
    "day_of_week_norm",
    "vwap_distance_pct",
    "direction",
    "event_type_id",
]

LEVEL_TYPE_MAP: Dict[LevelType, int] = {
    LevelType.PDH: 0,
    LevelType.PDL: 1,
    LevelType.PDC: 2,
    LevelType.CDO: 3,
    LevelType.ORH: 4,
    LevelType.ORL: 5,
    LevelType.SESSION_HIGH: 6,
    LevelType.SESSION_LOW: 7,
    LevelType.SWING_HIGH_5M: 8,
    LevelType.SWING_LOW_5M: 9,
}

REGIME_MAP: Dict[MarketRegime, int] = {
    MarketRegime.TREND: 0,
    MarketRegime.TRENDING_VOLATILITY: 1,
    MarketRegime.RANGE: 2,
    MarketRegime.EXPANSION: 3,
    MarketRegime.EXHAUSTION: 4,
    MarketRegime.CHAOTIC: 5,
    MarketRegime.UNKNOWN: 6,
}

EVENT_TYPE_MAP: Dict[EventType, int] = {
    EventType.CONTINUATION: 0,
    EventType.ABSORPTION: 1,
    EventType.VACUUM_TRAP: 2,
}


@dataclass
class MLFeatureVector:
    """Explicitly typed feature container."""
    features: Dict[str, float]

    def to_array(self) -> np.ndarray:
        return np.array([self.features.get(name, 0.0) for name in FEATURE_NAMES], dtype=np.float32)

    def to_dict(self) -> Dict[str, float]:
        return {k: round(v, 4) for k, v in self.features.items()}


def extract_features(
    snapshot: VortexFeatureSnapshot,
    current_candle: Candle,
    session_info: MarketSessionInfo,
    interacted_level: Optional[StructuralLevel] = None,
    event_type: EventType = EventType.CONTINUATION,
    direction: int = 1,
) -> MLFeatureVector:
    """Extracts the 22-dimensional feature vector from point-in-time state."""
    # 1. Microstructure features
    comp = snapshot.compression
    press = snapshot.pressure
    trans = snapshot.translation
    absorp = snapshot.absorption
    vac = snapshot.vacuum
    snap = snapshot.snap_energy

    comp_score = float(comp.compression_score)
    comp_dur_norm = min(float(comp.duration_bars) / 30.0, 1.0)
    rv_pct = float(comp.realized_vol_percentile)
    atr_rat = min(float(comp.atr_ratio), 3.0)

    p_score = float(press.pressure_score)
    # Persistence is signed (negative = bearish streak). Model needs magnitude.
    p_pers_norm = min(abs(float(press.pressure_persistence)) / 10.0, 1.0)
    # Prefer scale-normalized acceleration; fall back to legacy raw value.
    _raw_acc = float(getattr(press, "pressure_acceleration_norm", press.pressure_acceleration))
    p_acc = max(-2.0, min(_raw_acc, 2.0))

    t_ratio = min(float(trans.translation_ratio), 10.0)
    abs_score = float(absorp.absorption_score)
    rej_wick = float(absorp.rejection_wick_ratio)
    vac_score = float(vac.liquidity_vacuum_score)
    snap_eng = float(snap.snap_energy)

    # 2. Context & Macro features
    lvl_dist_pct = float(interacted_level.distance_pct) if interacted_level else 0.0
    lvl_rel = float(interacted_level.relevance_score) if interacted_level else 0.0
    lvl_touches_norm = min(float(interacted_level.touch_count) / 10.0, 1.0) if interacted_level else 0.0
    lvl_type_id = float(LEVEL_TYPE_MAP.get(interacted_level.level_type, 0)) if interacted_level else 0.0

    regime_id = float(REGIME_MAP.get(snapshot.regime.regime, 4))
    mins_open_norm = min(max(float(session_info.minutes_from_open) / 375.0, 0.0), 1.0)
    dow_norm = min(max(float(session_info.day_of_week) / 4.0, 0.0), 1.0)

    # VWAP distance pct
    vwap_val = snapshot.structural_levels.levels[0].price if snapshot.structural_levels.levels else current_candle.close
    # find VWAP level if exists
    for lvl in snapshot.structural_levels.levels:
        if lvl.level_type == LevelType.CDO:  # reference
            vwap_val = lvl.price
            break
    vwap_dist = abs(current_candle.close - vwap_val) / max(vwap_val, 1.0)

    f_dict: Dict[str, float] = {
        "compression_score": comp_score,
        "compression_duration_norm": comp_dur_norm,
        "realized_vol_percentile": rv_pct,
        "atr_ratio": atr_rat,
        "pressure_score": p_score,
        "pressure_persistence_norm": p_pers_norm,
        "pressure_acceleration": p_acc,
        "translation_ratio": t_ratio,
        "absorption_score": abs_score,
        "rejection_wick_ratio": rej_wick,
        "liquidity_vacuum_score": vac_score,
        "snap_energy": snap_eng,
        "level_distance_pct": lvl_dist_pct,
        "level_relevance": lvl_rel,
        "level_touch_count_norm": lvl_touches_norm,
        "level_type_id": lvl_type_id,
        "regime_id": regime_id,
        "minutes_from_open_norm": mins_open_norm,
        "day_of_week_norm": dow_norm,
        "vwap_distance_pct": vwap_dist,
        "direction": float(direction),
        "event_type_id": float(EVENT_TYPE_MAP.get(event_type, 0)),
    }

    return MLFeatureVector(features=f_dict)
