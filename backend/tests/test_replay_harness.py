"""Deterministic replay: same bars + seed => identical report; fail-closed gates."""

import math
from datetime import datetime, timedelta, timezone
import pytest

from app.quant.replay.harness import KEEPER_TO_QUANT_KEY, replay_bars

_IST = timezone(timedelta(hours=5, minutes=30))
_BASE = datetime(2026, 1, 2, 9, 15, tzinfo=_IST)


def _bars(n: int = 200) -> list[dict]:
    bars = []
    price = 25000.0
    for i in range(n):
        drift = 2.0 * math.sin(i / 9.0) + (1.5 if i % 40 < 20 else -1.0)
        o = price
        c = o + drift
        bars.append({
            "ts": (_BASE + timedelta(minutes=i)).isoformat(),
            "open": o,
            "high": max(o, c) + 3.0,
            "low": min(o, c) - 3.0,
            "close": c,
            "volume": 1200.0 + (i % 7) * 100.0,
        })
        price = c
    return bars


def test_mapping_covers_keepers_only():
    assert KEEPER_TO_QUANT_KEY == {
        "ORB": "S1",
        "VOLATILITY_BREAKOUT": "S2",
        "BREAKOUT": "S2",
        "VWAP_SCALP": "S3",
    }


def test_replay_deterministic_same_seed():
    bars = _bars()
    r1 = replay_bars(bars, "ORB", seed=7)
    r2 = replay_bars(bars, "ORB", seed=7)
    assert r1["metrics"] == r2["metrics"]
    assert r1["trades"] == r2["trades"]
    assert r1["promotion"]["verdict"] in ("PASSED", "FAILED", "INCONCLUSIVE")
    assert r1["frozen_at"] == r2["frozen_at"]


def test_replay_fail_closed():
    bars = _bars()
    with pytest.raises(ValueError, match="keepers"):
        replay_bars(bars, "GAMMA_SPIKE")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=">=60"):
        replay_bars(_bars(20), "ORB")
    dup = _bars(80)
    dup[5]["ts"] = dup[6]["ts"]
    with pytest.raises(ValueError, match="Duplicate"):
        replay_bars(dup, "ORB")
