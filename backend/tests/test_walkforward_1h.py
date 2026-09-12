"""P1-2 walk-forward + purge/embargo harness tests (1H forecast v2.3).

Synthetic DETERMINISTIC 1h candles only for harness mechanics (never for
production reports — the CLI refuses synthetic data). Fast (<5s): ~150 bars,
pure local calendar, no network/DB.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.research.validation.backtest_engine import WalkForwardGate

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

_SLOTS_IST = [(9, 15), (10, 15), (11, 15), (12, 15), (13, 15), (14, 15), (15, 15)]


def _make_1h_candles(n: int = 150, start_date=(2026, 9, 7)):
    """Deterministic hourly 1h bars on NSE trading days.

    7 bars/day at 09:15..15:15 IST. The 15:15 decision window [15:15,16:15]
    crosses the 15:30 close -> classify_window unsettleable, exercising the
    session filter. Prices oscillate deterministically (no randomness).
    """
    y, m, d = start_date
    day = datetime(y, m, d, tzinfo=IST).date()
    out = []
    idx = 0
    # Walk forward day by day until n bars.
    while len(out) < n:
        # Skip weekends (Sep 2026 has no NSE holidays in this window).
        if day.weekday() < 5:
            for hh, mm in _SLOTS_IST:
                if len(out) >= n:
                    break
                ist_dt = datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)
                utc_dt = ist_dt.astimezone(UTC)
                # Oscillating deterministic price: drift + alternating +/-5.
                price = 25000.0 + idx * 0.5 + (5.0 if idx % 2 == 0 else -5.0)
                out.append({
                    "open": round(price - 0.5, 2),
                    "high": round(price + 1.0, 2),
                    "low": round(price - 1.0, 2),
                    "close": round(price, 2),
                    "volume": float(1000 + idx),
                    "timestamp": utc_dt.isoformat(),
                })
                idx += 1
        day = day + timedelta(days=1)
    return out


def _run(**kw):
    candles = _make_1h_candles(kw.pop("n", 150))
    params = dict(instrument="NIFTY 50", warmup=20, stride=1, folds=5,
                  purge_bars=2, embargo_days=1)
    params.update(kw)
    return WalkForwardGate.run_walkforward(candles, None, **params), candles


def test_chronological_order_and_no_shuffle():
    report, _ = _run()
    folds = report["folds"]
    assert len(folds) == 5
    starts = [f["test_start"] for f in folds]
    ends = [f["test_end"] for f in folds]
    # Chronological: strictly increasing blocks, no overlap.
    assert starts == sorted(starts)
    for i in range(len(folds) - 1):
        assert ends[i] < starts[i + 1]
    # No shuffle: each fold's test indices ascending + global concatenation sorted.
    for f in folds:
        assert f["test_indices"] == sorted(f["test_indices"])
    _concat = [t for f in folds for t in f["test_indices"]]
    assert _concat == sorted(_concat)


def test_purge_embargo_respected_no_overlap():
    report, _ = _run(purge_bars=2, embargo_days=1)
    for f in report["folds"]:
        tri = set(f["train_indices"])
        tei = set(f["test_indices"])
        assert not (tri & tei), "train/test overlap (leakage)"
        if tri and tei:
            gap = min(tei) - max(tri)
            assert gap > 2, f"purge violated: gap={gap} <= purge=2"
    assert report["leakage_audit"]["purge_respected"] is True
    assert report["leakage_audit"]["chronological"] is True
    assert report["leakage_audit"]["no_shuffle"] is True


def test_session_filter_drops_cross_close():
    report, _ = _run()
    # 15:15 IST bars cross the close -> must be counted separately.
    assert report["n_unsettleable"] > 0
    reasons = " ".join((report.get("unsettleable_reasons") or {}).keys())
    assert ("crosses-session-close" in reasons or "crosses" in reasons
            or "close" in reasons or "outside" in reasons
            or "non-trading" in reasons), f"unexpected reasons: {reasons}"
    # Dropped from metrics, counted separately (audit identity).
    total_test = sum(len(f["test_indices"]) for f in report["folds"])
    # All test candidates either settle (pooled n) or are unsettleable;
    # forward windows always exist by construction so no other drops.
    assert report["pooled"]["n"] + report["n_unsettleable"] == total_test


def test_metrics_keys_present():
    report, _ = _run()
    pooled = report["pooled"]
    for key in ("n", "hit_rate", "wilson95", "baseline_naive_accuracy",
                "baseline_buyhold_accuracy", "excess_vs_naive", "brier",
                "log_loss", "ece10", "reliability_table", "mfe_mean",
                "mae_mean", "target_hit_rate", "stop_hit_rate", "turnover"):
        assert key in pooled, f"missing pooled key {key}"
    assert len(pooled["reliability_table"]) == 10
    assert pooled["n"] > 0
    lo, hi = pooled["wilson95"]
    assert 0.0 <= lo <= hi <= 100.0
    assert 0.0 <= pooled["brier"] <= 2.0
    assert pooled["log_loss"] >= 0.0
    assert 0.0 <= pooled["ece10"] <= 1.0
    # Per-fold full metrics.
    for f in report["folds"]:
        for key in ("n", "hit_rate", "wilson95", "brier", "log_loss",
                    "ece10", "reliability_table", "mfe_mean", "mae_mean",
                    "target_hit_rate", "stop_hit_rate", "turnover"):
            assert key in f["metrics"], f"fold {f['fold']} missing {key}"
    # Breakdowns present with n + hit-rate + Wilson.
    for scope in ("by_instrument", "by_regime", "by_session", "by_direction"):
        assert scope in report and isinstance(report[scope], dict) and report[scope]
        for _g, m in report[scope].items():
            assert "n" in m and "hit_rate" in m and "wilson95" in m
    assert "NIFTY 50" in report["by_instrument"]


def test_folds_minimum_enforced():
    candles = _make_1h_candles(150)
    with pytest.raises(ValueError):
        WalkForwardGate.run_walkforward(candles, None, folds=3)
