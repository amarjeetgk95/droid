"""Tests for purged + embargoed walk-forward CV (candidate-level API).

These lock in the two defects that were fixed: ``embargo_bars`` is applied (not
merely stored), and a dataset too small for the requested folds raises instead of
degrading into an unpurged split.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from app.ml.validation.purged_cv import InsufficientDataError, PurgedWalkForwardCV

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


def _splits(cv: PurgedWalkForwardCV, n: int, **kwargs):
    return list(cv.split(np.arange(n), **kwargs))


class TestPurgeAndEmbargo:
    def test_folds_are_chronological_and_disjoint(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=10, embargo_bars=5)
        splits = _splits(cv, 300)
        assert len(splits) == 3
        for train_idx, test_idx in splits:
            assert len(train_idx) > 0 and len(test_idx) > 0
            assert len(set(train_idx).intersection(set(test_idx))) == 0
            assert max(train_idx) < min(test_idx)

    def test_embargo_widens_the_gap_between_train_and_test(self):
        """Regressing this assertion means the embargo was dropped again."""
        purge = 10
        without = _splits(PurgedWalkForwardCV(n_splits=3, purge_bars=purge, embargo_bars=0), 300)
        with_embargo = _splits(
            PurgedWalkForwardCV(n_splits=3, purge_bars=purge, embargo_bars=5), 300
        )

        gap_without = min(without[0][1]) - max(without[0][0])
        gap_with = min(with_embargo[0][1]) - max(with_embargo[0][0])
        assert gap_with - gap_without == 5

    def test_gap_equals_purge_plus_embargo(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=7, embargo_bars=4)
        assert cv.gap_bars == 11
        for train_idx, test_idx in _splits(cv, 400):
            assert min(test_idx) - max(train_idx) - 1 == cv.gap_bars

    def test_purge_width_must_cover_the_label_horizon(self):
        with pytest.raises(ValueError, match="narrower than the label horizon"):
            PurgedWalkForwardCV(n_splits=3, purge_bars=2, embargo_bars=1, horizon_bars=5)
        # Adequate purge is accepted.
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=5, embargo_bars=0, horizon_bars=5)
        assert cv.horizon_bars == 5

    def test_for_horizon_is_correct_by_construction(self):
        cv = PurgedWalkForwardCV.for_horizon(10, n_splits=3)
        assert cv.purge_bars == 10
        assert cv.embargo_bars == 10
        assert cv.gap_bars == 20

    def test_negative_parameters_rejected(self):
        with pytest.raises(ValueError):
            PurgedWalkForwardCV(n_splits=0)
        with pytest.raises(ValueError):
            PurgedWalkForwardCV(purge_bars=-1)


class TestSmallDatasetsNeverDegradeSilently:
    def test_undersized_dataset_raises(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=10, embargo_bars=5)
        with pytest.raises(InsufficientDataError):
            _splits(cv, 100)

    def test_opt_in_single_split_is_still_purged_and_embargoed(self):
        cv = PurgedWalkForwardCV(
            n_splits=3, purge_bars=10, embargo_bars=5, allow_single_split=True
        )
        splits = _splits(cv, 100)
        assert len(splits) == 1
        train_idx, test_idx = splits[0]
        assert min(test_idx) - max(train_idx) - 1 == cv.gap_bars

    def test_opt_in_does_not_waive_purging(self):
        cv = PurgedWalkForwardCV(
            n_splits=3, purge_bars=200, embargo_bars=200, allow_single_split=True
        )
        with pytest.raises(InsufficientDataError):
            _splits(cv, 100)

    def test_gap_larger_than_history_raises(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=100, embargo_bars=100)
        with pytest.raises(InsufficientDataError):
            _splits(cv, 300)


class TestLabelWindowPurge:
    """Exact purge by label-window overlap, rather than a bar-count guess."""

    def _timestamps(self, n: int) -> list[datetime]:
        base = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
        return [base + timedelta(minutes=i) for i in range(n)]

    def test_no_training_label_reaches_into_the_test_block(self):
        horizon = 5
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=horizon, embargo_bars=0)
        ts = self._timestamps(400)
        label_end = [t + timedelta(minutes=horizon) for t in ts]

        for train_idx, test_idx in cv.split(np.arange(400), ts, label_end):
            eval_start = ts[test_idx[0]]
            for idx in train_idx:
                assert label_end[idx] < eval_start

    def test_label_purge_removes_samples_the_bar_gap_would_have_missed(self):
        """With no bar-count gap, exact label overlap still protects the boundary."""
        horizon = 5
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=0, embargo_bars=0)
        ts = self._timestamps(400)
        label_end = [t + timedelta(minutes=horizon) for t in ts]

        without = _splits(cv, 400)
        with_labels = list(cv.split(np.arange(400), ts, label_end))
        assert cv.last_purged_by_label == horizon * len(with_labels)
        assert len(with_labels[0][0]) == len(without[0][0]) - horizon

    def test_bar_gap_alone_suffices_when_purge_covers_the_horizon(self):
        """purge_bars == horizon already removes the overlapping labels."""
        horizon = 5
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=horizon, embargo_bars=0)
        ts = self._timestamps(400)
        label_end = [t + timedelta(minutes=horizon) for t in ts]

        splits = list(cv.split(np.arange(400), ts, label_end))
        assert splits
        assert cv.last_purged_by_label == 0
        for train_idx, test_idx in splits:
            eval_start = ts[test_idx[0]]
            assert all(label_end[i] < eval_start for i in train_idx)

    def test_incomparable_metadata_raises(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=5, embargo_bars=0)
        ts = [str(i) for i in range(400)]
        with pytest.raises(ValueError, match="mutually comparable"):
            _splits(cv, 400, timestamps=ts, label_end_times=list(range(400)))


class TestMetadata:
    def test_describe_exposes_versions_for_reports(self):
        cv = PurgedWalkForwardCV(n_splits=3, purge_bars=5, embargo_bars=5, horizon_bars=5)
        described = cv.describe()
        assert described["purge_bars"] == 5
        assert described["embargo_bars"] == 5
        assert described["gap_bars"] == 10
        assert described["deprecated"] is True
