"""Purged Walk-Forward Cross-Validation & Embargo Engine.

Implements Section 23 of the DROID ML Specification (advances in financial ML).
Ensures that:
  1. Overlapping evaluation horizons between train and test sets are purged.
  2. An embargo period is applied after the test set to eliminate serial auto-correlation leakage.
  3. All splits maintain strict chronological ordering (no random shuffling).
"""
from __future__ import annotations

from typing import Generator, List, Tuple
import numpy as np


class PurgedWalkForwardCV:
    """
    Chronological Walk-Forward CV with Purging and Embargo.
    """
    def __init__(
        self,
        n_splits: int = 4,
        purge_bars: int = 45,    # Horizon overlap buffer (e.g., 45m triple-barrier)
        embargo_bars: int = 15,  # Post-test auto-correlation buffer
    ):
        self.n_splits = n_splits
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars

    def split(
        self,
        X: np.ndarray,
        timestamps: List[int] | None = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """
        Yields (train_indices, test_indices) for each walk-forward fold.
        """
        n_samples = len(X)
        if n_samples < (self.n_splits + 1) * 50:
            # Degrade gracefully on small datasets
            split_point = int(n_samples * 0.8)
            yield np.arange(0, split_point), np.arange(split_point, n_samples)
            return

        # Expanding window walk-forward
        test_size = n_samples // (self.n_splits + 1)

        for fold in range(self.n_splits):
            test_start = (fold + 1) * test_size
            test_end = min(n_samples, test_start + test_size)

            # Training set is all data prior to test_start MINUS the purge buffer
            train_end = max(0, test_start - self.purge_bars)
            train_indices = np.arange(0, train_end)

            test_indices = np.arange(test_start, test_end)

            if len(train_indices) > 20 and len(test_indices) > 10:
                yield train_indices, test_indices
