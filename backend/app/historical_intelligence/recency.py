"""
Recency Weighting & Fresh Analogue Layer — §§18, 19
Fuses long-term historical analogues with fresh recent-window analogues.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone


def compute_recency_weight(
    query_ts: datetime,
    historical_ts: datetime,
    half_life_days: float = 180.0,
    min_weight: float = 0.50,
) -> float:
    """
    Computes an exponential temporal weight (§18) while guaranteeing a floor (min_weight)
    so that highly relevant historical analogues from past eras are preserved.
    """
    q_utc = query_ts.astimezone(timezone.utc) if query_ts.tzinfo else query_ts.replace(tzinfo=timezone.utc)
    h_utc = historical_ts.astimezone(timezone.utc) if historical_ts.tzinfo else historical_ts.replace(tzinfo=timezone.utc)

    delta_days = max(0.0, (q_utc - h_utc).total_seconds() / 86400.0)

    # Exponential decay: w = e^(-lambda * days)
    decay_lambda = math.log(2.0) / max(1.0, half_life_days)
    raw_w = math.exp(-decay_lambda * delta_days)

    # Scale between min_weight and 1.0
    return round(min_weight + (1.0 - min_weight) * raw_w, 4)


def is_in_fresh_window(
    query_ts: datetime,
    historical_ts: datetime,
    fresh_window_days: int = 10,
) -> bool:
    """Checks if a historical analogue belongs to the recent-window analogue layer (§19)."""
    q_utc = query_ts.astimezone(timezone.utc) if query_ts.tzinfo else query_ts.replace(tzinfo=timezone.utc)
    h_utc = historical_ts.astimezone(timezone.utc) if historical_ts.tzinfo else historical_ts.replace(tzinfo=timezone.utc)

    delta_days = (q_utc - h_utc).total_seconds() / 86400.0
    return 0.0 <= delta_days <= float(fresh_window_days)
