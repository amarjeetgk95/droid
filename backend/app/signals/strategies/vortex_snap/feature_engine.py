"""
Unified Feature Orchestrator for VORTEX-SNAP Scalping Engine (§54).

Coordinates all microstructure engines:
- Market Session Model (§4)
- Structural Level Map (§5)
- Compression Engine (§6)
- Directional Pressure Engine (§7)
- Translation Ratio Engine (§8)
- Absorption Detector (§9)
- Liquidity Vacuum Detector (§10)
- Snap Energy Composite (§11)
- Market Regime Engine (§19)

Strictly point-in-time safe, ablatable (§32), with end-to-end latency profiling (§49).
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionResult,
    CompressionZone,
    DirectionalPressureResult,
    AbsorptionResult,
    LiquidityVacuumResult,
    MarketRegime,
    MarketSessionInfo,
    RegimeResult,
    SessionPhase,
    SnapEnergyResult,
    StructuralLevelMapResult,
    TranslationRatioResult,
    TranslationState,
    VortexFeatureSnapshot,
)
from app.signals.strategies.vortex_snap.config import VortexSnapConfig
from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.features.structural_levels import StructuralLevelEngine
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.translation import TranslationRatioEngine
from app.signals.strategies.vortex_snap.features.absorption import AbsorptionDetector
from app.signals.strategies.vortex_snap.features.vacuum import LiquidityVacuumDetector
from app.signals.strategies.vortex_snap.features.snap_energy import SnapEnergyEngine
from app.signals.strategies.vortex_snap.features.regime import MarketRegimeEngine


class VortexFeatureEngine:
    """High-throughput point-in-time feature orchestrator."""

    def __init__(self, config: Optional[VortexSnapConfig] = None) -> None:
        self.config = config or VortexSnapConfig.default()
        self.session_model = MarketSessionModel(self.config.session)
        self.structural_engine = StructuralLevelEngine(self.config.structural_levels)
        self.compression_engine = CompressionEngine(self.config.compression)
        self.pressure_engine = DirectionalPressureEngine(self.config.pressure)
        self.translation_engine = TranslationRatioEngine(self.config.translation)
        self.absorption_detector = AbsorptionDetector(self.config.absorption)
        self.vacuum_detector = LiquidityVacuumDetector(self.config.vacuum)
        self.snap_energy_engine = SnapEnergyEngine(self.config.snap_energy)
        self.regime_engine = MarketRegimeEngine(self.config.regime)

        # Internal state tracking across sequential bars
        self._prior_compression_duration = 0
        self._prior_pressure_persistence = 0
        self._prior_translation_ratio: Optional[float] = None
        self._compression_history: List[float] = []

    def reset_state(self) -> None:
        """Reset internal sequential state (e.g. at session open or new backtest run)."""
        self._prior_compression_duration = 0
        self._prior_pressure_persistence = 0
        self._prior_translation_ratio = None
        self._compression_history.clear()

    def compute_snapshot(
        self,
        instrument: str,
        candles_1m: List[Candle],
        timestamp_ms: Optional[int] = None,
        spot_price: Optional[float] = None,
        pdh: Optional[float] = None,
        pdl: Optional[float] = None,
        pdc: Optional[float] = None,
        cdo: Optional[float] = None,
        orh: Optional[float] = None,
        orl: Optional[float] = None,
        vwap: Optional[float] = None,
        candles_5m: Optional[List[Candle]] = None,
        volume_nodes: Optional[List[Tuple[float, float]]] = None,
        ablation_overrides: Optional[Dict[str, bool]] = None,
    ) -> VortexFeatureSnapshot:
        """Compute full point-in-time feature snapshot for candle T.

        Args:
            instrument: e.g. "NIFTY", "BANKNIFTY", "SENSEX"
            candles_1m: Sequence of closed 1m candles up to and including bar T.
            timestamp_ms: Epoch ms timestamp. If None, derived from last candle.
            spot_price: Current spot price. If None, derived from last candle close.
            pdh, pdl, pdc, cdo, orh, orl, vwap: Reference price levels.
            candles_5m: Optional 5m candles up to bar T.
            volume_nodes: Optional price volume distribution nodes.
            ablation_overrides: Optional component flags to toggle components off (§32).

        Returns:
            VortexFeatureSnapshot with all computed features and timing metrics.
        """
        total_start = time.perf_counter()

        # Resolve timestamp and price
        if not candles_1m:
            raise ValueError("candles_1m cannot be empty for feature computation")

        curr_candle = candles_1m[-1]
        ts = timestamp_ms if timestamp_ms is not None else curr_candle.timestamp
        price = spot_price if spot_price is not None else curr_candle.close

        # Merge ablation flags (§32)
        ablation = {
            "compression": self.config.enable_compression,
            "pressure": self.config.enable_pressure,
            "translation": self.config.enable_translation,
            "vacuum": self.config.enable_vacuum,
            "absorption": self.config.enable_absorption,
            "snap_energy": self.config.enable_snap_energy,
            "structural_levels": self.config.enable_structural_levels,
            "regime": self.config.enable_regime,
        }
        if ablation_overrides:
            ablation.update(ablation_overrides)

        # 1. Market Session Info (§4)
        session_info = self.session_model.evaluate(ts)

        # 2. Structural Level Map (§5)
        if ablation["structural_levels"]:
            levels_res = self.structural_engine.compute(
                candles_1m=candles_1m,
                pdh=pdh,
                pdl=pdl,
                pdc=pdc,
                cdo=cdo,
                orh=orh,
                orl=orl,
                vwap=vwap,
                candles_5m=candles_5m,
                volume_nodes=volume_nodes,
            )
        else:
            levels_res = StructuralLevelMapResult(computation_time_ms=0.0)

        # 3. Compression Engine (§6)
        if ablation["compression"]:
            comp_res = self.compression_engine.compute(
                candles=candles_1m,
                prior_duration=self._prior_compression_duration,
            )
            self._prior_compression_duration = comp_res.duration_bars
            self._compression_history.append(comp_res.compression_score)
            if len(self._compression_history) > 30:
                self._compression_history.pop(0)
        else:
            comp_res = CompressionResult(
                compression_score=0.0,
                zone=CompressionZone.UNCOMPRESSED,
                atr_ratio=1.0,
                realized_vol_percentile=0.5,
                true_range_compression=0.0,
                candle_overlap=0.0,
                range_contraction=0.0,
                directional_entropy=0.5,
                displacement_efficiency=0.5,
                duration_bars=0,
                computation_time_ms=0.0,
            )

        # 4. Directional Pressure Engine (§7)
        if ablation["pressure"]:
            press_res = self.pressure_engine.compute(
                candles=candles_1m,
                prior_persistence=self._prior_pressure_persistence,
            )
            self._prior_pressure_persistence = press_res.pressure_persistence
        else:
            press_res = DirectionalPressureResult(
                net_pressure=0.0,
                pressure_score=0.0,
                pressure_direction=0,
                positive_pressure=0.0,
                negative_pressure=0.0,
                pressure_acceleration=0.0,
                pressure_persistence=0,
                pressure_change=0.0,
                pressure_5bar=0.0,
                pressure_10bar=0.0,
                computation_time_ms=0.0,
            )

        # 5. Translation Ratio Engine (§8)
        if ablation["translation"]:
            trans_res = self.translation_engine.compute(
                candles=candles_1m,
                pressure_result=press_res,
                reference_price=None,
                prior_translation_ratio=self._prior_translation_ratio,
            )
            self._prior_translation_ratio = trans_res.translation_ratio
        else:
            trans_res = TranslationRatioResult(
                translation_ratio=1.0,
                translation_score=0.5,
                translation_state=TranslationState.NEUTRAL,
                normalized_displacement=0.0,
                raw_displacement_points=0.0,
                normalized_pressure=0.0,
                price_direction=0,
                pressure_direction=0,
                direction_aligned=True,
                translation_change=0.0,
                computation_time_ms=0.0,
            )

        # 6. Absorption Detector (§9)
        if ablation["absorption"]:
            abs_res = self.absorption_detector.compute(
                candles=candles_1m,
                pressure=press_res,
                translation=trans_res,
                level_map=levels_res,
            )
        else:
            abs_res = AbsorptionResult(
                absorption_score=0.0,
                is_absorption_suspected=False,
                volume_shock_ratio=1.0,
                rejection_wick_ratio=0.0,
                level_proximity_score=0.0,
                repeated_test_count=0,
                failure_to_extend=False,
                opposing_pressure=False,
                interacted_level=None,
                computation_time_ms=0.0,
            )

        # 7. Liquidity Vacuum Detector (§10)
        if ablation["vacuum"]:
            vac_res = self.vacuum_detector.compute(
                candles=candles_1m,
                compression=comp_res,
                prior_compression_history=self._compression_history,
            )
        else:
            vac_res = LiquidityVacuumResult(
                liquidity_vacuum_score=0.0,
                is_vacuum_detected=False,
                range_expansion=1.0,
                volume_shock=1.0,
                close_location=0.5,
                overlap_penalty=0.0,
                prior_compression_passed=False,
                computation_time_ms=0.0,
            )

        # 8. Snap Energy Composite (§11)
        if ablation["snap_energy"]:
            energy_res = self.snap_energy_engine.compute(
                candles=candles_1m,
                compression=comp_res,
                pressure=press_res,
            )
        else:
            energy_res = SnapEnergyResult(
                snap_energy=0.0,
                compression_duration=0,
                pressure_accumulation=0.0,
                directional_consistency=0.0,
                energy_tier="LOW",
                computation_time_ms=0.0,
            )

        # 9. Market Regime Engine (§19)
        if ablation["regime"]:
            regime_res = self.regime_engine.compute(
                candles_1m=candles_1m,
                compression=comp_res,
                pressure=press_res,
                translation=trans_res,
                candles_5m=candles_5m,
            )
        else:
            regime_res = RegimeResult(
                regime=MarketRegime.UNKNOWN,
                regime_confidence=0.5,
                trend_strength=0.0,
                volatility_state="NORMAL",
                efficiency_ratio=0.5,
                permitted_events=[],
                computation_time_ms=0.0,
            )

        total_latency = (time.perf_counter() - total_start) * 1000.0

        return VortexFeatureSnapshot(
            instrument=instrument,
            timestamp_ms=ts,
            spot_price=round(price, 2),
            session=session_info,
            structural_levels=levels_res,
            compression=comp_res,
            pressure=press_res,
            translation=trans_res,
            absorption=abs_res,
            vacuum=vac_res,
            snap_energy=energy_res,
            regime=regime_res,
            total_latency_ms=round(total_latency, 3),
            ablation_mask=ablation,
        )
