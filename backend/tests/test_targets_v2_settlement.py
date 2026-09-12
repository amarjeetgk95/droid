"""P1-1 tests: v2 target spec + research settlement. Pure — no network.

Covers: v2 label boundaries (±band, zero/NaN ATR raises), v1-math parity,
cross-close / holiday / special skips via a fake calendar, the forward-spot
picker, plan_research_row settle/wait/skip, and settle_due_research dry-run
with a fake session + fake fetchers.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.ml.sessions import resolve_forward_spot
from app.ml.targets import label_forward_return
from app.ml.targets_v2 import (
    ATR_LEN,
    NEUTRAL_BAND_ATR_V2,
    TARGET_SPEC_VERSION_V1,
    TARGET_SPEC_VERSION_V2,
    TARGET_SPEC_VERSIONS,
    describe_target_v2,
    label_forward_return_v2,
)
from app.research.settlement import plan_research_row, settle_due_research
from app.services.calendar_service import TradingSessionInfo

IST = ZoneInfo("Asia/Kolkata")
WED = datetime(2026, 9, 9).date()  # regular Wednesday
WED_10AM_IST = datetime(2026, 9, 9, 10, 0, tzinfo=IST)
WED_1430_IST = datetime(2026, 9, 9, 14, 30, tzinfo=IST)


class FakeCalendar:
    """Minimal calendar double exposing get_session_info(date)."""

    def __init__(self, *, trading=True, special=False, holiday_name=None):
        self._trading = trading
        self._special = special
        self._holiday = holiday_name

    def get_session_info(self, day):
        mkt_open = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST)
        mkt_close = datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST)
        if not self._trading:
            return TradingSessionInfo(
                is_trading_day=False, is_holiday=True, is_weekend=False,
                holiday_name=self._holiday or "Fake Holiday",
                is_special_session=False, market_open=None, market_close=None,
            )
        return TradingSessionInfo(
            is_trading_day=True, is_holiday=False, is_weekend=False,
            holiday_name=None, is_special_session=self._special,
            market_open=mkt_open, market_close=mkt_close,
        )


def _regular_calendar():
    return FakeCalendar(trading=True, special=False)


def _row(**overrides):
    base = {
        "prediction_id": "pred_test_01",
        "indicator_id": "trend_forecast_1h",
        "instrument": "NIFTY 50",
        "timeframe": "1h",
        "timestamp": WED_10AM_IST.astimezone(timezone.utc),
        "current_price": 100.0,
        "direction": "BULLISH",
        "forecast_horizon": "1h",
        "horizon_candles": 1,
        "target_price": 101.8,
        "invalidation_price": 98.9,
        "atr_at_t": 2.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# v2 spec
# ---------------------------------------------------------------------------

def test_v2_spec_version_and_constants():
    assert TARGET_SPEC_VERSION_V2 == "v2-atr-em-session"
    assert NEUTRAL_BAND_ATR_V2 == 0.25
    assert ATR_LEN == 14
    assert TARGET_SPEC_VERSION_V1 == "v1-atr-band"
    assert set(TARGET_SPEC_VERSIONS) == {"v1-atr-band", "v2-atr-em-session"}


def test_v2_label_boundaries_match_v1_math():
    # spot 100, atr 2 -> band = 0.25*2/100 = 0.005
    assert label_forward_return_v2(100.0, 101.0, 2.0) == 2
    assert label_forward_return_v2(100.0, 99.0, 2.0) == 0
    assert label_forward_return_v2(100.0, 100.2, 2.0) == 1
    assert label_forward_return_v2(100.0, 100.0, 2.0) == 1
    # exact ±band touches stay NEUTRAL (strict inequalities)
    assert label_forward_return_v2(100.0, 100.5, 2.0) == 1
    assert label_forward_return_v2(100.0, 99.5, 2.0) == 1
    assert label_forward_return_v2(100.0, 100.51, 2.0) == 2
    assert label_forward_return_v2(100.0, 99.49, 2.0) == 0
    # parity with v1 on identical inputs
    for spot_h in (98.0, 99.49, 99.5, 100.0, 100.2, 100.5, 100.51, 102.0):
        assert label_forward_return_v2(100.0, spot_h, 2.0) == label_forward_return(100.0, spot_h, 2.0)


def test_v2_label_refuses_missing_data():
    for bad in (0.0, -1.0, float("nan"), None):
        with pytest.raises(ValueError):
            label_forward_return_v2(100.0, 101.0, bad)
    with pytest.raises(ValueError):
        label_forward_return_v2(0.0, 101.0, 2.0)
    with pytest.raises(ValueError):
        label_forward_return_v2(100.0, 0.0, 2.0)


def test_describe_target_v2_notes_em_risk_only_and_session():
    d = describe_target_v2()
    assert d["target_spec_version"] == "v2-atr-em-session"
    assert d["horizon_minutes"] == 60
    assert "atr_14" in d["atr_source"]
    assert "risk-only" in d["em_note"]
    assert "same-regular-session" in d["session_note"]


# ---------------------------------------------------------------------------
# forward-spot picker (shared sessions helper)
# ---------------------------------------------------------------------------

def test_resolve_forward_spot_picks_last_in_window():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)
    h = t + timedelta(minutes=60)
    candles = [
        (t - timedelta(minutes=5), 100.0),
        (t, 100.0),
        (t + timedelta(minutes=30), 101.0),
        (t + timedelta(minutes=59), 100.2),
        (t + timedelta(minutes=90), 999.0),  # after H: never used
    ]
    spot, reason = resolve_forward_spot(candles, t, h)
    assert spot == 100.2 and reason == ""


def test_resolve_forward_spot_insufficient():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)
    spot, reason = resolve_forward_spot([], t, t + timedelta(minutes=60))
    assert spot is None and reason == "no-candle-covering-horizon"


# ---------------------------------------------------------------------------
# plan_research_row
# ---------------------------------------------------------------------------

def test_plan_waits_for_horizon():
    t = WED_10AM_IST.astimezone(timezone.utc)
    plan = plan_research_row(_row(timestamp=t), [], t + timedelta(minutes=30),
                             calendar=_regular_calendar())
    assert plan["action"] == "wait"
    assert plan["reason"] == "horizon-not-elapsed"


def test_plan_skips_missing_atr():
    t = WED_10AM_IST.astimezone(timezone.utc)
    plan = plan_research_row(_row(timestamp=t, atr_at_t=0.0), [], t + timedelta(minutes=90),
                             calendar=_regular_calendar())
    assert plan == {"action": "skip", "reason": "missing-atr-at-t"}


def test_plan_skips_cross_close():
    t = WED_1430_IST.astimezone(timezone.utc)  # 14:30 IST + 60m hits 15:30 close
    plan = plan_research_row(_row(timestamp=t), [], t + timedelta(minutes=90),
                             calendar=_regular_calendar())
    assert plan == {"action": "skip", "reason": "crosses-session-close"}


def test_plan_skips_holiday_and_special():
    t = WED_10AM_IST.astimezone(timezone.utc)
    now = t + timedelta(minutes=90)
    holiday = plan_research_row(_row(timestamp=t), [], now,
                                calendar=FakeCalendar(trading=False, holiday_name="Diwali"))
    assert holiday["action"] == "skip"
    assert "non-trading-day" in holiday["reason"]
    special = plan_research_row(_row(timestamp=t), [], now,
                                calendar=FakeCalendar(trading=True, special=True))
    assert special == {"action": "skip", "reason": "special-session-involved"}


def test_plan_settles_nse_same_session_neutral():
    t = WED_10AM_IST.astimezone(timezone.utc)
    now = t + timedelta(minutes=90)
    candles = [(t + timedelta(minutes=m), px) for m, px in ((0, 100.0), (30, 101.0), (59, 100.2))]
    plan = plan_research_row(_row(timestamp=t), candles, now, calendar=_regular_calendar())
    assert plan["action"] == "settle"
    assert plan["outcome_spot"] == 100.2
    assert plan["outcome_label"] == 1  # +0.2% inside the ±0.5% band
    assert plan["outcome_name"] == "NEUTRAL"
    assert plan["target_spec_version"] == "v2-atr-em-session"


def test_plan_settles_crypto_bullish():
    t = datetime(2026, 9, 9, 4, 0, tzinfo=timezone.utc)
    now = t + timedelta(minutes=90)
    row = _row(instrument="BTCUSDT", timestamp=t, current_price=90000.0, atr_at_t=200.0)
    candles = [(t + timedelta(minutes=m), 90000.0 + m) for m in (0, 30, 59)]
    plan = plan_research_row(row, candles, now, calendar=_regular_calendar())
    assert plan["action"] == "settle"
    assert plan["outcome_spot"] == 90059.0
    assert plan["outcome_label"] == 2
    assert plan["outcome_name"] == "BULLISH"


def test_plan_skips_without_covering_candle():
    t = WED_10AM_IST.astimezone(timezone.utc)
    plan = plan_research_row(_row(timestamp=t), [], t + timedelta(minutes=90),
                             calendar=_regular_calendar())
    assert plan == {"action": "skip", "reason": "no-candle-covering-horizon"}


# ---------------------------------------------------------------------------
# settle_due_research dry-run with fake session + fake fetchers
# ---------------------------------------------------------------------------

class _FakeMappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return _FakeMappings(self._rows)


class FakeSession:
    """Minimal async session double: execute() yields canned due rows."""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt, params=None):
        return _FakeResult(self._rows)

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_settle_due_research_dry_run():
    now = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
    t_settle = now - timedelta(minutes=120)
    settle_candles = [(t_settle + timedelta(minutes=m), 90000.0 + m) for m in (0, 30, 59)]

    async def fake_crypto(symbol, start, end):
        return [c for c in settle_candles if start <= c[0] <= end]

    async def fake_nse(symbol, start, end):
        return []

    rows = [
        _row(prediction_id="pred_dry_settle", instrument="BTCUSDT",
             timestamp=t_settle, current_price=90000.0, atr_at_t=200.0),
        _row(prediction_id="pred_dry_wait", instrument="BTCUSDT",
             timestamp=now - timedelta(minutes=10), current_price=90000.0, atr_at_t=200.0),
        _row(prediction_id="pred_dry_noatr", instrument="BTCUSDT",
             timestamp=t_settle, current_price=90000.0, atr_at_t=0.0),
    ]
    with patch("app.research.predictions.PredictionService.append_outcome",
               new=AsyncMock()) as append_mock:
        summary = await settle_due_research(
            FakeSession(rows),
            indicator_prefix="trend_forecast_",
            limit=10,
            now_utc=now,
            nse_fetcher=fake_nse,
            crypto_fetcher=fake_crypto,
            calendar=_regular_calendar(),
            dry_run=True,
        )
    assert summary["dry_run"] is True
    assert summary["settled"] == 0
    assert summary["would_settle"] == 1
    assert summary["skipped"].get("horizon-not-elapsed") == 1
    assert summary["skipped"].get("missing-atr-at-t") == 1
    assert summary["errors"] == 0
    assert summary["target_spec_version"] == "v2-atr-em-session"
    append_mock.assert_not_called()


@pytest.mark.asyncio
async def test_settle_due_research_commit_appends_outcome():
    now = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
    t_settle = now - timedelta(minutes=120)
    settle_candles = [(t_settle + timedelta(minutes=m), 90000.0 + m) for m in (0, 30, 59)]

    async def fake_crypto(symbol, start, end):
        return [c for c in settle_candles if start <= c[0] <= end]

    rows = [_row(prediction_id="pred_commit_01", instrument="BTCUSDT",
                 timestamp=t_settle, current_price=90000.0, atr_at_t=200.0)]
    with patch("app.research.predictions.PredictionService.append_outcome",
               new=AsyncMock(return_value="out_abc")) as append_mock:
        summary = await settle_due_research(
            FakeSession(rows),
            limit=10,
            now_utc=now,
            crypto_fetcher=fake_crypto,
            nse_fetcher=AsyncMock(return_value=[]),
            calendar=_regular_calendar(),
            dry_run=False,
        )
    assert summary["settled"] == 1
    assert summary["errors"] == 0
    assert append_mock.await_count == 1
    outcome = append_mock.await_args.args[0]
    assert outcome.prediction_id == "pred_commit_01"
    assert outcome.actual_direction.value == "BULLISH"
    assert outcome.exit_price == 90059.0


def test_forecast_v2_contract_exposes_v2_spec():
    """P1-1 wiring: the 1h-v2 contract settles under v2-atr-em-session."""
    from app.research.trend_forecast import TrendForecast1H, validate_forecast_v2

    fc = TrendForecast1H.__new__(TrendForecast1H)
    result = fc.ensemble_forecast(
        mtf_features={
            "instrument": "NIFTY 50",
            "per_timeframe": {"1h": {"features": {
                "quant": {"supertrend_dir": "BULLISH", "rsi_14": 60.0, "atr_14": 50.0},
                "regime": "TRENDING_UP", "session": "EARLY"}}},
            "alignment": {"overall_bias": "BULLISH", "alignment_score": 60.0},
        },
        indicator_outputs=[],
        ml_forecast=None,
        options_ctx={"pcr_oi": 1.0},
        current_price=25000.0,
        horizon="1h",
    )
    assert result["forecast_version"] == "1h-v2"
    assert result["target_spec_version"] == "v2-atr-em-session"
    # v1 ensemble keys intact for frontend compat
    assert result["direction"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert set(result["layer_scores"]) == {"mtf_alignment", "indicators", "ml", "options", "structure"}
    assert validate_forecast_v2(result, record=False) == []
