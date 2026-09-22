"""Purged Walk-Forward Cross-Validation & Embargo Engine (candidate-level API).

.. deprecated::
    Prefer :class:`app.quant.validation.purged_wfo.PurgedWalkForwardSplitter`
    for new work — it is the canonical splitter, purges against real label end
    times, and reports per-fold purge counts. This class is retained because
    ``scripts/train_breakout.py`` and ``scripts/train_trade_outcome.py`` use its
    index-based ``split(X)`` contract.

Why this module was rewritten (2026-09-22)
-----------------------------------------
Two defects made it unsafe to build research on top of:

1. ``embargo_bars`` was accepted and **never applied**. It was assigned in
   ``__init__`` and referenced nowhere else, while the module docstring claimed
   "an embargo period is applied after the test set". The claim was true of the
   documentation and false of the code.
2. When ``n_samples < (n_splits + 1) * 50`` the splitter silently fell through
   to a single 80/20 split with **no purge and no embargo**, described in a
   comment as "degrade gracefully on small datasets".

Both are the same failure shape: a degraded path that returns a plausible answer
instead of failing. A train/test split is exactly where an unpurged boundary
looks like a strong result. Neither path may remain silent, so:

* purge and embargo are now both applied, as a single explicit ``gap_bars``;
* a dataset too small for the requested folds raises ``InsufficientDataError``
  rather than downgrading. An explicit ``allow_single_split=True`` opt-in keeps
  the small-dataset case available, and even then the single split is purged and
  embargoed;
* passing ``horizon_bars`` makes purge width auditable against the label
  horizon it is meant to cover;
* passing ``timestamps`` and ``label_end_times`` purges by real label-window
  overlap instead of by bar count, which is the only exact test.
"""
from __future__ import annotations

import warnings
from typing import Any, Generator, List, Optional, Sequence, Tuple

import numpy as np

#: Per-fold sample heuristic used to decide whether the requested fold count is
#: affordable. Preserved from the original implementation so existing callers
#: keep their fold counts.
_MIN_FOLD_SAMPLES = 50


class InsufficientDataError(RuntimeError):
    """Too few samples for purged walk-forward at the requested purge and embargo."""


class PurgedWalkForwardCV:
    """Chronological walk-forward CV with purging and embargo.

    Splits are strictly chronological and non-shuffled. For each fold the
    training set ends ``purge_bars + embargo_bars`` bars before the test block
    begins:

    * **purge** — training samples whose label horizon would reach into the test
      period are removed (an overlapping label is future information);
    * **embargo** — an additional buffer, because consecutive bars are serially
      correlated even when labels do not formally overlap.
    """

    def __init__(
        self,
        n_splits: int = 4,
        purge_bars: int = 45,
        embargo_bars: int = 15,
        horizon_bars: Optional[int] = None,
        allow_single_split: bool = False,
    ) -> None:
        warnings.warn(
            "app.ml.validation.purged_cv.PurgedWalkForwardCV is deprecated; "
            "prefer app.quant.validation.purged_wfo.PurgedWalkForwardSplitter, "
            "which purges against real label end times.",
            DeprecationWarning,
            stacklevel=2,
        )

        if int(n_splits) < 1:
            raise ValueError(f"n_splits must be >= 1, got {n_splits}")
        if int(purge_bars) < 0:
            raise ValueError(f"purge_bars must be >= 0, got {purge_bars}")
        if int(embargo_bars) < 0:
            raise ValueError(f"embargo_bars must be >= 0, got {embargo_bars}")

        self.n_splits = int(n_splits)
        self.purge_bars = int(purge_bars)
        self.embargo_bars = int(embargo_bars)
        self.horizon_bars = None if horizon_bars is None else int(horizon_bars)
        self.allow_single_split = bool(allow_single_split)

        if self.horizon_bars is not None and self.purge_bars < self.horizon_bars:
            raise ValueError(
                f"purge_bars ({self.purge_bars}) is narrower than the label horizon "
                f"({self.horizon_bars}); overlapping labels would reach into the "
                "test period. Set purge_bars >= horizon_bars."
            )

        #: Bars removed between the end of training and the start of the test block.
        self.gap_bars = self.purge_bars + self.embargo_bars

        #: Folds dropped for being too small in the most recent ``split`` call.
        self.last_skipped_folds: int = 0

        #: Training samples purged by label-overlap in the most recent call.
        self.last_purged_by_label: int = 0

    @classmethod
    def for_horizon(
        cls,
        horizon_bars: int,
        n_splits: int = 4,
        embargo_bars: Optional[int] = None,
        allow_single_split: bool = False,
    ) -> "PurgedWalkForwardCV":
        """Correct-by-construction splitter for a label horizon.

        Purge width becomes the horizon and embargo defaults to the horizon, so
        the overlap rule cannot be forgotten at the call site.
        """
        horizon = int(horizon_bars)
        return cls(
            n_splits=n_splits,
            purge_bars=horizon,
            embargo_bars=horizon if embargo_bars is None else embargo_bars,
            horizon_bars=horizon,
            allow_single_split=allow_single_split,
        )

    def describe(self) -> dict[str, Any]:
        """Split configuration for experiment reports and version metadata."""
        return {
            "splitter": "app.ml.validation.purged_cv.PurgedWalkForwardCV",
            "deprecated": True,
            "n_splits": self.n_splits,
            "purge_bars": self.purge_bars,
            "embargo_bars": self.embargo_bars,
            "gap_bars": self.gap_bars,
            "horizon_bars": self.horizon_bars,
            "allow_single_split": self.allow_single_split,
        }

    def _required_samples(self) -> int:
        return (self.n_splits + 1) * _MIN_FOLD_SAMPLES

    def split(
        self,
        X: np.ndarray,
        timestamps: Optional[Sequence[Any]] = None,
        label_end_times: Optional[Sequence[Any]] = None,
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """Yield ``(train_indices, test_indices)`` per chronological fold.

        When ``timestamps`` and ``label_end_times`` are both supplied, training
        samples whose label window reaches the test block are purged by exact
        overlap and then the embargo gap is applied on top. Otherwise the purge
        is the bar-count approximation ``gap_bars``.
        """
        n_samples = len(X)
        self.last_skipped_folds = 0
        self.last_purged_by_label = 0

        if n_samples < self._required_samples():
            if not self.allow_single_split:
                raise InsufficientDataError(
                    f"Purged walk-forward needs >= {self._required_samples()} samples "
                    f"for {self.n_splits} folds (purge={self.purge_bars}, "
                    f"embargo={self.embargo_bars}), got {n_samples}. Refusing to "
                    "downgrade to an unpurged split — supply more data, or pass "
                    "allow_single_split=True to accept one purged+embargoed split."
                )
            yield from self._single_split(n_samples, timestamps, label_end_times)
            return

        test_size = n_samples // (self.n_splits + 1)
        if test_size < 1:
            raise InsufficientDataError(
                f"Fold size resolves to {test_size} samples for {n_samples} samples "
                f"and {self.n_splits} folds."
            )

        for fold in range(self.n_splits):
            test_start = (fold + 1) * test_size
            test_end = min(n_samples, test_start + test_size)

            train_end = test_start - self.gap_bars
            if train_end < 1:
                raise InsufficientDataError(
                    f"Fold {fold}: gap of {self.gap_bars} bars "
                    f"(purge={self.purge_bars} + embargo={self.embargo_bars}) leaves no "
                    f"training data before test_start={test_start}. Reduce the gap or "
                    "supply more history."
                )

            train_indices = self._purge(
                np.arange(0, train_end), test_start, timestamps, label_end_times
            )
            test_indices = np.arange(test_start, test_end)

            if len(train_indices) > 20 and len(test_indices) > 10:
                yield train_indices, test_indices
            else:
                self.last_skipped_folds += 1

    def _single_split(
        self,
        n_samples: int,
        timestamps: Optional[Sequence[Any]],
        label_end_times: Optional[Sequence[Any]],
    ) -> Generator[Tuple[np.ndarray, np.ndarray], None, None]:
        """One purged and embargoed split, for explicitly opted-in small datasets."""
        split_point = int(n_samples * 0.8)
        train_end = split_point - self.gap_bars
        if train_end < 1 or (n_samples - split_point) < 1:
            raise InsufficientDataError(
                f"Cannot form a single purged+embargoed split from {n_samples} samples "
                f"with a {self.gap_bars}-bar gap (split_point={split_point}). "
                "allow_single_split does not waive purging."
            )
        train_indices = self._purge(
            np.arange(0, train_end), split_point, timestamps, label_end_times
        )
        yield train_indices, np.arange(split_point, n_samples)

    def _purge(
        self,
        train_indices: np.ndarray,
        test_start: int,
        timestamps: Optional[Sequence[Any]],
        label_end_times: Optional[Sequence[Any]],
    ) -> np.ndarray:
        """Drop training samples whose label window reaches the test block."""
        if timestamps is None or label_end_times is None or len(train_indices) == 0:
            return train_indices

        if test_start >= len(timestamps):
            raise ValueError(
                f"test_start ({test_start}) exceeds the timestamps supplied "
                f"({len(timestamps)})."
            )
        eval_start = timestamps[test_start]

        kept: List[int] = []
        try:
            for idx in train_indices:
                if label_end_times[idx] < eval_start:
                    kept.append(int(idx))
        except TypeError as exc:
            raise ValueError(
                "timestamps and label_end_times must be mutually comparable "
                f"(same type and units): {exc}"
            ) from exc

        self.last_purged_by_label += int(len(train_indices) - len(kept))
        return np.asarray(kept, dtype=int)
