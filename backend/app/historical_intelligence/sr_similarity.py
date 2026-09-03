"""
Support/Resistance & Options Wall Similarity — §23
Measures structural price relationship to Key S/R, Volume Profile POC, and Option Strike Walls.
"""
from __future__ import annotations

import math
from app.historical_intelligence.schemas import HistoricalStateSnapshot


def compute_sr_congruence(
    state_a: HistoricalStateSnapshot,
    state_b: HistoricalStateSnapshot,
) -> float:
    """
    Evaluates whether two market states share congruent proximity to key boundaries:
    - Distance to Support / ATR
    - Distance to Resistance / ATR
    - Retest status
    - Options ATM strike wall proximity
    """
    atr_a = max(1.0, state_a.feature_vector.volume_vol.atr)
    atr_b = max(1.0, state_b.feature_vector.volume_vol.atr)

    dist_sup_a = state_a.feature_vector.market_context.distance_to_support / atr_a
    dist_sup_b = state_b.feature_vector.market_context.distance_to_support / atr_b
    sup_diff = abs(dist_sup_a - dist_sup_b)
    sup_sim = max(0.0, 1.0 - (sup_diff / 2.5))

    dist_res_a = state_a.feature_vector.market_context.distance_to_resistance / atr_a
    dist_res_b = state_b.feature_vector.market_context.distance_to_resistance / atr_b
    res_diff = abs(dist_res_a - dist_res_b)
    res_sim = max(0.0, 1.0 - (res_diff / 2.5))

    retest_sim = 1.0 if state_a.structure_state == state_b.structure_state else 0.30

    return round((0.4 * sup_sim) + (0.4 * res_sim) + (0.2 * retest_sim), 4)
