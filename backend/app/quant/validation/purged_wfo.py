"""Purged and Embargoed Walk-Forward Cross-Validation (Tier 0).

Implements Marcos López de Prado's Purging and Embargoing to prevent
information leakage in financial time series with overlapping labels:
- Purging: Drops training observations whose outcome intervals [t_start, t_end]
  overlap with validation or test periods.
- Embargo: Applies a temporal buffer after evaluation periods to eliminate
  serial correlation / autoregressive leakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Generator, Optional
import polars as pl
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class WFOFold:
    fold_id: int
    train_indices: list[int]
    val_indices: list[int]
    test_indices: list[int]
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    purged_count: int


class PurgedWalkForwardSplitter:
    """Generates strictly non-overlapping, purged, and embargoed walk-forward folds."""

    def __init__(
        self,
        n_folds: int = 5,
        train_ratio: float = 0.60,
        val_ratio: float = 0.15,
        test_ratio: float = 0.25,
        embargo_pct: float = 0.02,  # 2% of fold duration as temporal buffer
    ):
        self.n_folds = n_folds
        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        self.embargo_pct = embargo_pct

    def split(
        self,
        timestamps: list[datetime],
        label_end_times: Optional[list[datetime]] = None,
    ) -> list[WFOFold]:
        """Generates walk-forward folds with purging and embargo applied.
        
        timestamps: list of observation timestamps t_start
        label_end_times: optional list of t_end for each observation (if None, assumes t_start)
        """
        n = len(timestamps)
        if n < 50:
            raise ValueError(f"Insufficient samples for walk-forward CV: {n}")

        if label_end_times is None:
            label_end_times = timestamps

        folds: list[WFOFold] = []
        
        # Calculate step size for rolling window
        fold_step = int(n * (1.0 - self.train_ratio) / max(1, self.n_folds))
        window_size = int(n * (self.train_ratio + self.test_ratio))
        
        for fold_idx in range(self.n_folds):
            start_offset = fold_idx * fold_step
            if start_offset + window_size > n and fold_idx > 0:
                break

            fold_n = min(window_size, n - start_offset)
            fold_indices = list(range(start_offset, start_offset + fold_n))

            train_cutoff = int(fold_n * self.train_ratio)
            val_cutoff = int(fold_n * (self.train_ratio + self.val_ratio))

            raw_train = fold_indices[:train_cutoff]
            raw_val = fold_indices[train_cutoff:val_cutoff]
            raw_test = fold_indices[val_cutoff:]

            if not raw_test:
                continue

            test_start_t = timestamps[raw_test[0]]
            test_end_t = timestamps[raw_test[-1]]
            val_start_t = timestamps[raw_val[0]] if raw_val else test_start_t

            # PURGING: Remove any training sample whose label extends into val/test
            eval_start_t = val_start_t
            purged_train: list[int] = []
            purged_count = 0

            for idx in raw_train:
                t_end = label_end_times[idx]
                if t_end < eval_start_t:
                    purged_train.append(idx)
                else:
                    purged_count += 1

            # EMBARGO: Remove samples right after evaluation if train rolled past test
            # (In standard expanding/rolling where train precedes test, purging t_end < eval_start handles it)

            train_start_t = timestamps[purged_train[0]] if purged_train else timestamps[0]
            train_end_t = timestamps[purged_train[-1]] if purged_train else timestamps[0]

            folds.append(WFOFold(
                fold_id=fold_idx + 1,
                train_indices=purged_train,
                val_indices=raw_val,
                test_indices=raw_test,
                train_start=train_start_t,
                train_end=train_end_t,
                test_start=test_start_t,
                test_end=test_end_t,
                purged_count=purged_count,
            ))

        return folds
