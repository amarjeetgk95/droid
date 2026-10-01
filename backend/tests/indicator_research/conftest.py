"""Shared fixtures for Indicator Research tests."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl
import pytest

from app.indicator_research.indicators.helpers import ohlcv_features


@pytest.fixture(autouse=True)
def _isolated_experiments(tmp_path, monkeypatch):
    """Never let a test write into the developer's real experiment directory."""
    target = tmp_path / "experiments"
    monkeypatch.setenv("INDICATOR_RESEARCH_EXPERIMENTS_DIR", str(target))
    return target


def build_candles(
    rows: list[tuple[float, float, float, float]],
    *,
    start: datetime | None = None,
    step_minutes: int = 5,
    volume_base: float = 1000.0,
) -> list[dict[str, Any]]:
    """Turn ``(open, high, low, close)`` tuples into engine-shaped candles."""
    origin = start or datetime(2026, 1, 5, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    out: list[dict[str, Any]] = []
    for i, (o, h, lo, c) in enumerate(rows):
        vol = volume_base + i
        out.append(
            {
                "timestamp": (origin + timedelta(minutes=step_minutes * i)).isoformat(),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": vol,
                "buy_volume": vol * 0.52,
                "sell_volume": vol * 0.48,
                "bid_price": c - 0.05,
                "ask_price": c + 0.05,
                "bid_qty": 500.0,
                "ask_qty": 450.0,
            }
        )
    return out


def synthetic_candles(
    count: int = 400,
    *,
    amplitude: float = 1.1,
    period: float = 9.0,
    drift: float = 0.03,
    step_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Deterministic cyclical series — reproducible, no randomness."""
    rows: list[tuple[float, float, float, float]] = []
    price = 100.0
    for i in range(count):
        price = price + math.sin(i / period) * amplitude + drift
        rows.append((price - 0.1, price + 0.6, price - 0.6, price))
    return build_candles(rows, step_minutes=step_minutes)


@pytest.fixture
def candles() -> list[dict[str, Any]]:
    return synthetic_candles()


@pytest.fixture
def price_columns() -> tuple[str, ...]:
    return tuple(ohlcv_features([]).keys())


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    """Write a real parquet dataset and point the repository at it.

    Uses the production storage layout so the data adapter is exercised for
    real rather than stubbed.
    """
    from app.historical_data.storage.parquet_repository import parquet_repo

    base = tmp_path / "historical" / "parquet"
    monkeypatch.setattr(parquet_repo, "base_dir", base, raising=True)

    # An oscillating series, not a straight line: rules that depend on turning
    # points (Fisher, RSI, Supertrend) must actually fire, otherwise every
    # downstream assertion would pass vacuously on zero trades.
    rows = synthetic_candles(400)
    frame = pl.DataFrame(
        {
            "timestamp": [datetime.fromisoformat(r["timestamp"]) for r in rows],
            "open": [r["open"] for r in rows],
            "high": [r["high"] for r in rows],
            "low": [r["low"] for r in rows],
            "close": [r["close"] for r in rows],
            "volume": [r["volume"] for r in rows],
        }
    )
    target = base / "nifty" / "5m"
    target.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(target / "candles_v1.parquet")
    return {"symbol": "NIFTY", "timeframe": "5m", "bars": 400}


@pytest.fixture
def empty_store(tmp_path, monkeypatch):
    """Point the canonical store at an empty directory.

    Makes the "no dataset" behaviour deterministic instead of depending on
    whether the developer happens to have real history on disk.
    """
    from app.historical_data.storage.parquet_repository import parquet_repo

    base = tmp_path / "empty-store"
    base.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(parquet_repo, "base_dir", base, raising=True)
    return base


@pytest.fixture
def client():
    """Router-only app: no market services, no broker, no lifespan side effects."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.indicator_research.api import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)
