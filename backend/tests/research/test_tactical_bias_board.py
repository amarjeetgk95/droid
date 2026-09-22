"""Tests for the single-snapshot tactical board (GET /tactical-bias/board).

Regression cover for the board-vs-tape drift: five independent
/tactical-bias/{horizon} runs resolve five different spots (each card reads
its own horizon's last candle close at its own fetch instant, plus
per-horizon cache ages). The board must resolve ONE shared MTF snapshot and
ONE anchor price, and stamp every card with the same generated_at.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.research import trend_forecast as tf_mod
from app.research.trend_forecast import (
    BOARD_HORIZONS,
    _MTFCandles,
    TacticalHorizonEngine,
)

ANCHOR = 74931.20
LAST_CLOSES = {
    "1m": 74920.0,
    "5m": 74925.0,
    "15m": 74930.0,
    "30m": 74935.0,
    "1h": 74940.0,
    "4h": 74910.0,
    "1D": 74800.0,
}
COUNTS = {"1m": 500, "5m": 200, "15m": 80, "30m": 60, "1h": 60, "4h": 20, "1D": 10}
STEPS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1D": 1440}

client = TestClient(app)


def _ramp(last_close: float, count: int, step_min: int):
    base = datetime(2026, 9, 21, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    out = []
    for i in range(count):
        price = last_close - (count - 1 - i) * 2.0
        out.append(
            {
                "open": price - 1.0,
                "high": price + 2.0,
                "low": price - 2.0,
                "close": price,
                "volume": 1000.0 + i * 10.0,
                "timestamp": (base + timedelta(minutes=step_min * i)).isoformat(),
            }
        )
    return out


def _canned_mtf() -> _MTFCandles:
    return _MTFCandles(
        {tf: _ramp(LAST_CLOSES[tf], COUNTS[tf], STEPS[tf]) for tf in LAST_CLOSES},
        resampled_tfs=[],
        cache_hit=False,
    )


@pytest.fixture
def board_market_service():
    ms = MagicMock()
    ms.get_quote = AsyncMock(
        return_value=SimpleNamespace(
            ltp=ANCHOR,
            status="LIVE",
            timestamp=datetime.now(timezone.utc),
        )
    )
    return ms


@pytest.fixture
def board_ml_predictor():
    mp = MagicMock()
    response = MagicMock()
    response.bullish_pct = 60.0
    response.bearish_pct = 20.0
    response.neutral_pct = 20.0
    response.predicted_bias = "BULLISH"
    response.trend_strength = 65.0
    response.confidence_score = 75.0
    response.model_source = "heuristic_ensemble"
    response.calibrated = False
    mp.predict_probabilities = AsyncMock(return_value=response)
    return mp


@pytest.fixture
def hermetic_engine(board_market_service, board_ml_predictor, monkeypatch):
    engine = TacticalHorizonEngine(
        market_service=board_market_service,
        ml_predictor=board_ml_predictor,
    )
    monkeypatch.setattr(
        engine,
        "_get_options_context",
        AsyncMock(return_value=({"available": True, "data_quality": "LIVE"}, False)),
    )
    return engine


async def test_anchor_overrides_primary_close(hermetic_engine, monkeypatch):
    """Injected anchor wins; without it the horizon reads its own last close."""
    canned = _canned_mtf()
    fetch = AsyncMock(return_value=canned)
    monkeypatch.setattr(hermetic_engine, "fetch_multi_timeframe_candles", fetch)

    anchored = await hermetic_engine.forecast(
        "SENSEX", "5m", record=False, session=None,
        mtf_candles=canned, anchor_price=ANCHOR,
    )
    assert anchored["current_price"] == pytest.approx(ANCHOR)
    for key in ("target_price", "invalidation_price"):
        assert anchored[key] is not None
        assert abs(anchored[key] - ANCHOR) / ANCHOR < 0.05

    control = await hermetic_engine.forecast(
        "SENSEX", "5m", record=False, session=None, mtf_candles=canned,
    )
    assert control["current_price"] == pytest.approx(LAST_CLOSES["5m"])
    assert control["current_price"] != pytest.approx(ANCHOR)


async def test_board_shares_one_snapshot_and_anchor(hermetic_engine, monkeypatch):
    """All five horizons: same candles (one fetch), same anchor, same stamp."""
    canned = _canned_mtf()
    fetch = AsyncMock(return_value=canned)
    monkeypatch.setattr(hermetic_engine, "fetch_multi_timeframe_candles", fetch)

    board = await hermetic_engine.forecast_board("SENSEX", record=False)

    assert fetch.await_count == 1
    assert board["anchor_price"] == pytest.approx(ANCHOR)
    assert board["anchor_source"] == "quote:LIVE"
    assert board["errors"] == {}
    assert sorted(board["horizons"].keys()) == sorted(BOARD_HORIZONS)
    stamps = set()
    for horizon, card in board["horizons"].items():
        assert card["current_price"] == pytest.approx(ANCHOR), horizon
        stamps.add(card["generated_at"])
    assert len(stamps) == 1
    assert board["generated_at"] in stamps


async def test_board_anchor_falls_back_to_1m_close(hermetic_engine, monkeypatch):
    """Dead quote path degrades to the freshest candle, never a fabrication."""
    hermetic_engine.market_service.get_quote = AsyncMock(
        side_effect=RuntimeError("feed down")
    )
    canned = _canned_mtf()
    monkeypatch.setattr(
        hermetic_engine, "fetch_multi_timeframe_candles", AsyncMock(return_value=canned)
    )

    board = await hermetic_engine.forecast_board("SENSEX", record=False)

    assert board["anchor_price"] == pytest.approx(LAST_CLOSES["1m"])
    assert board["anchor_source"] == "1m-close"
    for card in board["horizons"].values():
        assert card["current_price"] == pytest.approx(LAST_CLOSES["1m"])


def test_board_endpoint_serves_single_snapshot(monkeypatch):
    """GET /tactical-bias/board: route order, shape, shared stamp, SWR hit."""
    gen = datetime.now(timezone.utc).isoformat()

    async def _fake_board(**kwargs):
        assert kwargs.get("record") is False
        return {
            "instrument": "BOARDTEST",
            "generated_at": gen,
            "anchor_price": ANCHOR,
            "anchor_source": "quote:LIVE",
            "anchor_ts": gen,
            "persisted": False,
            "horizons": {
                h: {"current_price": ANCHOR, "generated_at": gen, "direction": "BULLISH"}
                for h in BOARD_HORIZONS
            },
            "errors": {},
        }

    monkeypatch.setattr(
        tf_mod.tactical_horizon_engine, "forecast_board", _fake_board
    )

    r1 = client.get(
        "/api/v1/research/tactical-bias/board?instrument=BOARDTEST&record=false"
    )
    assert r1.status_code == 200, r1.text
    body = r1.json()
    assert body["anchor_price"] == pytest.approx(ANCHOR)
    assert body["cache_age_s"] == pytest.approx(0.0)
    assert body["stale"] is False
    assert sorted(body["horizons"].keys()) == sorted(BOARD_HORIZONS)
    assert {c["generated_at"] for c in body["horizons"].values()} == {gen}

    # Second hit is served from the board SWR cache (not a rerun).
    r2 = client.get(
        "/api/v1/research/tactical-bias/board?instrument=BOARDTEST&record=false"
    )
    assert r2.status_code == 200
    assert r2.json()["cache_age_s"] > 0
