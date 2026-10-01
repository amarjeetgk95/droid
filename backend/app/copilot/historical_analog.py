"""Historical Analog Engine adapter (spec Â§12).

Wraps the existing DROID 8-D PCA analogue engine
(`app.copilot.analogue.historical_analogue.HistoricalAnalogueEngine`) over the
immutable parquet datasets managed by `DatasetManager`. It reuses the same
causal feature engine, triple-barrier labeller and exclusion window as the
former analogues research endpoint, so there is exactly one analogue
implementation in DROID.

Guarantees:
  * candidate bars are strictly BEFORE the query bar (no look-ahead),
  * a Â±60 minute temporal exclusion window removes the query's own move,
  * when datasets/analogues are unavailable the result is explicitly
    `available: false` â€” never a fabricated count.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.copilot.enums import ANALOG_ENGINE_VERSION
from app.copilot.models import HistoricalContext

logger = structlog.get_logger()

MIN_ANALOGS = 15
#: Similarity floor for a neighbour to count as an analogue.
SIMILARITY_THRESHOLD = 0.82
ANALOG_TIMEOUT_SECONDS = 25.0
CAUSAL_GUARD = (
    "Causal only: candidate bars precede the query timestamp, with a Â±60 minute exclusion window around it."
)

UNAVAILABLE_MESSAGE = (
    "Historical analogs unavailable for this analysis â€” no validated DROID history covers this instrument/horizon."
)


class HistoricalAnalogEngine:
    """Copilot-facing adapter around DROID's historical analogue engine."""

    def __init__(self, timeframe: str = "5m", k_neighbors: int = 15, exclusion_minutes: int = 60) -> None:
        self.timeframe = timeframe
        self.k_neighbors = k_neighbors
        self.exclusion_minutes = exclusion_minutes

    async def query(self, symbol: str, horizon: str, direction: int = 1) -> HistoricalContext:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._query_sync, symbol, horizon, direction),
                timeout=ANALOG_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("copilot_analog_timeout", symbol=symbol)
            return self._unavailable("Historical analogue search exceeded its time budget.")
        except Exception as exc:  # history is optional evidence, never fatal
            logger.info("copilot_analog_unavailable", symbol=symbol, error=str(exc)[:200])
            return self._unavailable(UNAVAILABLE_MESSAGE)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _unavailable(message: str) -> HistoricalContext:
        return HistoricalContext(
            available=False,
            analog_count=0,
            similarity_threshold=SIMILARITY_THRESHOLD,
            message=message,
            lookahead_guard=CAUSAL_GUARD,
            engine_version=ANALOG_ENGINE_VERSION,
        )

    def _load_frame(self, symbol: str) -> Any | None:
        from app.market_core.data.dataset_manager import DatasetManager

        manager = DatasetManager()
        if not manager.exists(symbol, "1m"):
            return None
        raw, _meta = manager.load_dataset(symbol, "1m")
        if raw is None or len(raw) == 0:
            return None
        if self.timeframe != "1m":
            return manager.resample_candles(raw, target_timeframe=self.timeframe)
        return raw


    def _query_sync(self, symbol: str, horizon: str, direction: int) -> HistoricalContext:
        from app.copilot.analogue.feature_engine import CausalFeatureEngine
        from app.copilot.analogue.historical_analogue import HistoricalAnalogueEngine as _PWEngine
        from app.copilot.analogue.label_engine import TripleBarrierLabelEngine
        from app.copilot.analogue.baseline_strategies import BaselineStrategyEngine

        frame = self._load_frame(symbol)
        if frame is None:
            return self._unavailable(
                f"Historical analogs unavailable for this analysis â€” no {symbol} dataset in the DROID warehouse."
            )

        features = CausalFeatureEngine().compute_features(frame)
        query_idx = len(features) - 1
        if query_idx < MIN_ANALOGS:
            return self._unavailable("Historical analogs unavailable â€” dataset is shorter than the minimum sample.")

        strategy = BaselineStrategyEngine(trend_aligned=True)
        candidates = strategy.scan_s1_orb(features) + strategy.scan_s2_momentum(features)
        # No look-ahead: only bars strictly before the query bar are eligible.
        candidates = [c for c in candidates if c.bar_index < query_idx]
        if len(candidates) < MIN_ANALOGS:
            return self._unavailable(UNAVAILABLE_MESSAGE)

        labeller = TripleBarrierLabelEngine(t_max_bars=10, k_tp=2.0, k_sl=1.0)
        outcomes = labeller.label_candidates(
            features,
            [c.bar_index for c in candidates],
            [c.direction for c in candidates],
        )
        net_returns = [o.gross_return - 0.00133 for o in outcomes]

        engine = _PWEngine(
            n_components=8,
            k_neighbors=self.k_neighbors,
            exclusion_window_minutes=self.exclusion_minutes,
        )
        engine.build_index(features, candidates, outcomes, net_returns)
        context = engine.find_analogues(
            df_feat=features,
            query_bar_idx=query_idx,
            query_time=features["timestamp"][query_idx],
            query_direction=direction,
            k=self.k_neighbors,
        )
        return self._to_context(context)

    @staticmethod
    def _to_context(context: Any) -> HistoricalContext:
        neighbours = list(getattr(context, "top_neighbors", []) or [])
        kept = [n for n in neighbours if getattr(n, "similarity", 0.0) >= SIMILARITY_THRESHOLD]
        if not kept:
            return HistoricalAnalogEngine._unavailable(
                "Historical analogs unavailable for this analysis â€” no historical regime met the "
                f"{SIMILARITY_THRESHOLD:.2f} similarity threshold."
            )

        positive = sum(1 for n in kept if n.net_return > 0)
        negative = sum(1 for n in kept if n.net_return < 0)
        neutral = len(kept) - positive - negative
        returns = sorted(n.net_return for n in kept)
        median = (
            returns[len(returns) // 2]
            if len(returns) % 2
            else (returns[len(returns) // 2 - 1] + returns[len(returns) // 2]) / 2
        )
        mean = sum(returns) / len(returns)
        return HistoricalContext(
            available=True,
            analog_count=len(kept),
            similarity_threshold=SIMILARITY_THRESHOLD,
            forward_outcome={"positive": positive, "neutral": neutral, "negative": negative},
            median_return=round(median * 100.0, 4),
            mean_return=round(mean * 100.0, 4),
            win_rate=round(positive / len(kept), 4),
            dispersion=round(float(getattr(context, "analogue_dispersion", 0.0) or 0.0) * 100.0, 4),
            direction_agreement=round(float(getattr(context, "regime_similarity_score", 0.0) or 0.0) / 100.0, 4),
            message=(
                f"{len(kept)} leakage-free historical analogues matched at â‰¥{SIMILARITY_THRESHOLD:.2f} similarity "
                f"(exclusion window Â±{self.exclusion_minutes} min)."
            ),
            lookahead_guard=CAUSAL_GUARD,
            engine_version=ANALOG_ENGINE_VERSION,
        )


historical_analog_engine = HistoricalAnalogEngine()
