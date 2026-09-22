"""Unit tests for PurgedWalkForwardSplitter (Tier 0)."""

import pytest
from datetime import datetime, timezone, timedelta

from app.quant.validation.purged_wfo import PurgedWalkForwardSplitter


class TestPurgedWalkForwardSplitter:

    def test_purging_overlapping_labels(self):
        """Training observations whose outcome window extends into the evaluation window must be purged."""
        splitter = PurgedWalkForwardSplitter(n_folds=2, train_ratio=0.5, val_ratio=0.2, test_ratio=0.3)

        base_time = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)
        n = 100
        timestamps = [base_time + timedelta(minutes=i) for i in range(n)]

        # Each observation has a 15-minute forward outcome window: [t, t + 15m]
        label_end_times = [t + timedelta(minutes=15) for t in timestamps]

        folds = splitter.split(timestamps, label_end_times)
        assert len(folds) >= 1

        for fold in folds:
            assert fold.purged_count > 0, "Purging should have eliminated overlapping samples at boundary"
            
            val_start = timestamps[fold.val_indices[0]]
            
            # Assert NO sample in purged train set has a label ending after val_start
            for train_idx in fold.train_indices:
                sample_end = label_end_times[train_idx]
                assert sample_end < val_start, (
                    f"LEAKAGE in fold {fold.fold_id}: Train sample {train_idx} ends at {sample_end} "
                    f"which overlaps evaluation start {val_start}"
                )
