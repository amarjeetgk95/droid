"""
Research Prediction Auto-Settlement — P1-1 (1H forecast v2.3).

Mirrors ``app.ml.settlement`` but for the research laboratory tables:
reads ``research_predictions`` rows whose outcome is missing (LEFT JOIN
``research_prediction_outcomes``), resolves the realized 60m forward spot
from historical 1m candles, labels with the v2 spec
(``app.ml.targets_v2.label_forward_return_v2``), and appends to
``research_prediction_outcomes`` via ``PredictionService.append_outcome``.

Rules (same as ML settlement — never invent data):
- Horizon-not-elapsed -> wait.
- Missing/non-positive ATR14_1h at T -> skip (``missing-atr-at-t``).
- NSE windows crossing the session close / holidays / specials ->
  skip as INSUFFICIENT_DATA, never bridged (via ``classify_window``).
- No 1m candle covering [T, T+H] -> skip (``no-candle-covering-horizon``).

Candle fetchers and the calendar are injectable so planning is unit-testable
without brokers or a database. ``plan_research_row`` is pure (no I/O);
``settle_due_research`` performs I/O. ``dry_run=True`` plans everything but
writes nothing.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
import uuid

import structlog

from app.ml.sessions import classify_window, is_crypto_symbol, resolve_forward_spot
from app.ml.targets_v2 import INV_LABEL, TARGET_SPEC_VERSION_V2, label_forward_return_v2

logger = structlog.get_logger()

CandleFetcher = Callable[[str, datetime, datetime], Awaitable[list[Any]]]

RESEARCH_DUE_PREFIX_DEFAULT = "trend_forecast_"
RESEARCH_DEFAULT_HORIZON_MINUTES = 60

# forecast_horizon / timeframe text -> minutes. NEXT_DAY has no intraday
# settlement window and always plans as unsupported (skip, never guess).
FORECAST_HORIZON_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}


async def fetch_nse_candles(symbol: str, start: datetime, end: datetime) -> list[Any]:
    """1m NSE candles for [start, end] via the configured broker provider."""
    from app.ml.settlement import fetch_nse_candles as _nse

    return await _nse(symbol, start, end)


async def fetch_crypto_candles(symbol: str, start: datetime, end: datetime) -> list[Any]:
    """1m Binance klines filtered to [start, end]."""
    from app.ml.settlement import fetch_crypto_candles as _crypto

    return await _crypto(symbol, start, end)


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _component_values(row: dict) -> dict:
    import json as _json

    cv = row.get("component_values")
    if isinstance(cv, dict):
        return cv
    if isinstance(cv, str) and cv.strip():
        try:
            parsed = _json.loads(cv)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def extract_atr_at_t(row: dict, snapshot_features: Any | None = None) -> float:
    """Best-effort ATR14_1h at T for a research prediction row.

    Lookup order (first positive finite win):
    1. top-level ``atr_at_t`` / ``atr14_1h`` / ``atr_14`` / ``atr``
    2. ``component_values`` (dict or JSON string) same keys
    3. snapshot ``features`` (dict or JSON string):
       per_timeframe 1h -> features -> quant -> atr_14, then flat fallbacks
    Returns 0.0 when nothing usable is found (caller skips as missing-atr).
    """
    import json as _json

    for key in ("atr_at_t", "atr14_1h", "atr_14", "atr"):
        v = _safe_float(row.get(key))
        if v is not None and v > 0:
            return v
    cv = _component_values(row)
    for key in ("atr_at_t", "atr14_1h", "atr_14", "atr"):
        v = _safe_float(cv.get(key))
        if v is not None and v > 0:
            return v
    feats: Any = snapshot_features
    if feats is None:
        feats = row.get("snapshot_features") or row.get("features")
    if isinstance(feats, str) and feats.strip():
        try:
            feats = _json.loads(feats)
        except Exception:
            feats = None
    if isinstance(feats, dict):
        try:
            per_tf = feats.get("per_timeframe") or {}
            for tf_key in ("1h", "1H", "60m", "60"):
                payload = per_tf.get(tf_key) or {}
                inner = payload.get("features") or {}
                quant = inner.get("quant") or {}
                v = _safe_float(quant.get("atr_14"))
                if v is not None and v > 0:
                    return v
        except Exception:
            pass
        for key in ("atr_14", "atr_at_t", "atr14_1h", "atr"):
            try:
                v = _safe_float(feats.get(key))
            except Exception:
                v = None
            if v is not None and v > 0:
                return v
    return 0.0


def resolve_horizon_minutes(row: dict) -> int | None:
    """Horizon minutes for a research row: explicit override, else text map.

    Returns None for horizons with no intraday settlement window (NEXT_DAY)
    so the planner can skip instead of mislabeling.
    """
    explicit = row.get("horizon_minutes")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            pass
    for key in ("forecast_horizon", "timeframe", "horizon"):
        raw = row.get(key)
        if raw is None:
            continue
        text = getattr(raw, "value", raw)
        if isinstance(text, str) and text.strip().upper() == "NEXT_DAY":
            return None
        if isinstance(text, str) and text.strip() in FORECAST_HORIZON_MINUTES:
            return FORECAST_HORIZON_MINUTES[text.strip()]
    return RESEARCH_DEFAULT_HORIZON_MINUTES


def _spot_at_t(row: dict) -> float:
    for key in ("current_price", "spot_price", "price", "entry_price"):
        v = _safe_float(row.get(key))
        if v is not None:
            return v
    return 0.0


def plan_research_row(
    row: dict,
    candles_1m: list[Any],
    now_utc: datetime,
    calendar: Any | None = None,
) -> dict:
    """Decide the settlement action for one research prediction row.

    Row keys (aliases tolerated): instrument|symbol, timestamp,
    current_price|spot_price, horizon_minutes|forecast_horizon|timeframe,
    atr_at_t|atr14_1h (+ component_values / snapshot_features for ATR).
    Returns {"action": "settle"|"wait"|"skip", ...}. Pure — no I/O.
    """
    symbol = row.get("instrument") or row.get("symbol") or ""
    t = row.get("timestamp")
    if t is None:
        return {"action": "skip", "reason": "missing-timestamp"}
    if not isinstance(t, datetime):
        try:
            t = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except Exception:
            return {"action": "skip", "reason": "missing-timestamp"}
    t = _as_utc(t)
    now = _as_utc(now_utc)

    horizon = resolve_horizon_minutes(row)
    if horizon is None:
        return {"action": "skip", "reason": "unsupported-horizon"}
    try:
        t_plus_h = t + timedelta(minutes=int(horizon))
    except (TypeError, ValueError, OverflowError):
        return {"action": "skip", "reason": "unsupported-horizon"}

    if now < t_plus_h:
        return {"action": "wait", "reason": "horizon-not-elapsed"}

    spot_t = _spot_at_t(row)
    if not spot_t > 0:
        return {"action": "skip", "reason": "missing-spot-at-t"}

    atr = extract_atr_at_t(row)
    if not atr > 0:
        return {"action": "skip", "reason": "missing-atr-at-t"}

    try:
        window = classify_window(symbol, t, int(horizon), calendar=calendar)
    except ValueError:
        return {"action": "skip", "reason": "unsupported-horizon"}
    if not window.get("settleable"):
        return {"action": "skip", "reason": str(window.get("reason") or "unsettled-window")}

    spot_h, reason = resolve_forward_spot(candles_1m, t, window["t_plus_h_utc"])
    if spot_h is None:
        return {"action": "skip", "reason": reason or "no-candle-covering-horizon"}

    try:
        outcome_label = label_forward_return_v2(spot_t, float(spot_h), atr)
    except ValueError as e:
        return {"action": "skip", "reason": f"label-refused:{e}"[:200]}
    return {
        "action": "settle",
        "outcome_spot": float(spot_h),
        "outcome_label": outcome_label,
        "outcome_name": INV_LABEL[outcome_label],
        "target_spec_version": TARGET_SPEC_VERSION_V2,
        "horizon_minutes": int(horizon),
        "atr_at_t": float(atr),
        "t_plus_h_utc": window["t_plus_h_utc"],
    }


def _candle_high_low_close(c: Any) -> tuple[float | None, float | None, float | None]:
    """Extract (high, low, close) from tuple / dict / object candles."""
    if isinstance(c, tuple) and len(c) >= 2:
        close = _safe_float(c[1])
        if close is not None and close > 0:
            return close, close, close
        return None, None, None
    if isinstance(c, dict):
        close = _safe_float(c.get("close"))
        if close is None or not close > 0:
            return None, None, None
        high = _safe_float(c.get("high", close)) or close
        low = _safe_float(c.get("low", close)) or close
        return high, low, close
    close = _safe_float(getattr(c, "close", None))
    if close is None or not close > 0:
        return None, None, None
    high = _safe_float(getattr(c, "high", close)) or close
    low = _safe_float(getattr(c, "low", close)) or close
    return high, low, close


def build_research_outcome(
    row: dict,
    outcome_spot: float,
    outcome_label: int,
    candles_1m: list[Any] | None = None,
    now_utc: datetime | None = None,
) -> Any:
    """Build a ``PredictionOutcome`` for a settled research row.

    ``actual_direction`` comes from the v2 ATR-band label (not the raw sign);
    MFE/MAE + target/stop touches come from 1m high/low when available
    (close-only candles degrade to close-derived excursions, never invented
    highs/lows). ``is_correct`` mirrors ``OutcomeMeasurer``: a NEUTRAL
    prediction is correct only on NEUTRAL; a directional call must match the
    outcome label and not be stopped out (unless the target also hit).
    """
    from app.research.enums import Direction
    from app.research.models import PredictionOutcome

    outcome_name = INV_LABEL[outcome_label]
    actual_dir = Direction(outcome_name)
    entry = float(_spot_at_t(row))
    exit_px = float(outcome_spot)
    move = round(exit_px - entry, 2)
    pct = round((move / entry) * 100.0, 3) if entry > 0 else 0.0

    pred_raw = row.get("direction")
    pred_text = getattr(pred_raw, "value", pred_raw)
    try:
        pred_dir = Direction(str(pred_text))
    except Exception:
        pred_dir = Direction.UNKNOWN

    target_p = _safe_float(row.get("target_price"))
    inval_p = _safe_float(row.get("invalidation_price"))

    mfe = 0.0
    mae = 0.0
    target_hit = False
    stop_hit = False
    time_to_target_sec: float | None = None
    if candles_1m:
        highs: list[float] = []
        lows: list[float] = []
        for c in candles_1m:
            h, lo, _ = _candle_high_low_close(c)
            if h is None or lo is None:
                continue
            highs.append(h)
            lows.append(lo)
        if highs and lows:
            hi, lo = max(highs), min(lows)
            if pred_dir == Direction.BULLISH:
                mfe = round(max(0.0, hi - entry), 2)
                mae = round(max(0.0, entry - lo), 2)
            elif pred_dir == Direction.BEARISH:
                mfe = round(max(0.0, entry - lo), 2)
                mae = round(max(0.0, hi - entry), 2)
            else:
                mfe = 0.0
                mae = round(max(0.0, max(abs(hi - entry), abs(entry - lo))), 2)
            for idx, (h, lo) in enumerate(zip(highs, lows)):
                if target_p is not None and not target_hit and not stop_hit:
                    if pred_dir == Direction.BULLISH and h >= target_p:
                        target_hit = True
                        time_to_target_sec = (idx + 1) * 60.0
                    elif pred_dir == Direction.BEARISH and lo <= target_p:
                        target_hit = True
                        time_to_target_sec = (idx + 1) * 60.0
                if inval_p is not None and not stop_hit:
                    if pred_dir == Direction.BULLISH and lo <= inval_p:
                        stop_hit = True
                    elif pred_dir == Direction.BEARISH and h >= inval_p:
                        stop_hit = True

    if pred_dir == Direction.NEUTRAL:
        is_correct = actual_dir == Direction.NEUTRAL
    elif pred_dir in (Direction.BULLISH, Direction.BEARISH):
        is_correct = (pred_dir == actual_dir) and (not stop_hit or target_hit)
    else:
        is_correct = pred_dir == actual_dir

    return PredictionOutcome(
        outcome_id=f"out_{uuid.uuid4().hex[:12]}",
        prediction_id=str(row.get("prediction_id")),
        actual_direction=actual_dir,
        actual_price_move=move,
        actual_pct_move=pct,
        entry_price=round(entry, 2),
        exit_price=round(exit_px, 2),
        mfe=mfe,
        mae=mae,
        target_hit=target_hit,
        stop_hit=stop_hit,
        time_to_target_sec=time_to_target_sec,
        is_correct=is_correct,
        evaluated_at=_as_utc(now_utc) if now_utc is not None else datetime.now(timezone.utc),
    )


async def _fetch_due_rows(
    session: Any,
    indicator_prefix: str,
    limit: int,
    indicator: str | None = None,
    since_utc: datetime | None = None,
) -> list[dict]:
    """Due research rows (outcome missing) as plain dicts + snapshot features."""
    from sqlalchemy import text

    if indicator:
        stmt = text(
            """
            SELECT p.*, s.features AS snapshot_features
            FROM research_predictions p
            LEFT JOIN research_prediction_outcomes o ON o.prediction_id = p.prediction_id
            LEFT JOIN research_snapshots s ON s.snapshot_id = p.snapshot_id
            WHERE o.prediction_id IS NULL AND p.indicator_id = :ind
            AND (CAST(:since AS timestamptz) IS NULL OR p.timestamp >= CAST(:since AS timestamptz))
            ORDER BY p.timestamp ASC LIMIT :limit
            """
        )
        params: dict[str, Any] = {"ind": indicator, "since": since_utc, "limit": limit}
    else:
        stmt = text(
            """
            SELECT p.*, s.features AS snapshot_features
            FROM research_predictions p
            LEFT JOIN research_prediction_outcomes o ON o.prediction_id = p.prediction_id
            LEFT JOIN research_snapshots s ON s.snapshot_id = p.snapshot_id
            WHERE o.prediction_id IS NULL AND p.indicator_id LIKE :prefix
            AND (CAST(:since AS timestamptz) IS NULL OR p.timestamp >= CAST(:since AS timestamptz))
            ORDER BY p.timestamp ASC LIMIT :limit
            """
        )
        params = {"prefix": f"{indicator_prefix}%", "since": since_utc, "limit": limit}
    result = await session.execute(stmt, params)
    try:
        rows = result.mappings().all()
        return [dict(r) for r in rows]
    except AttributeError:
        # Fallback for minimal fake sessions returning plain row lists.
        rows = result.all() if hasattr(result, "all") else []
        return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def settle_due_research(
    session: Any,
    indicator_prefix: str = RESEARCH_DUE_PREFIX_DEFAULT,
    limit: int = 100,
    now_utc: datetime | None = None,
    nse_fetcher: CandleFetcher | None = None,
    crypto_fetcher: CandleFetcher | None = None,
    fetchers: dict[str, CandleFetcher] | None = None,
    calendar: Any | None = None,
    indicator: str | None = None,
    since_utc: datetime | None = None,
    dry_run: bool = False,
) -> dict:
    """Settle due research predictions. Returns summary counts.

    Only touches rows with no ``research_prediction_outcomes`` entry whose
    horizon has elapsed. Skips never fabricate — skipped rows stay unsettled
    for the next run. With ``dry_run=True`` every settleable row is counted
    under ``would_settle`` and nothing is appended.
    """
    from app.research.predictions import PredictionService

    now = _as_utc(now_utc) if now_utc is not None else datetime.now(timezone.utc)
    if fetchers:
        nse_fetch = fetchers.get("nse") or nse_fetcher or fetch_nse_candles
        crypto_fetch = fetchers.get("crypto") or crypto_fetcher or fetch_crypto_candles
    else:
        nse_fetch = nse_fetcher or fetch_nse_candles
        crypto_fetch = crypto_fetcher or fetch_crypto_candles

    pending = await _fetch_due_rows(session, indicator_prefix, limit, indicator, since_utc)

    settled = 0
    would_settle = 0
    skipped: Counter = Counter()
    errors = 0

    for row in pending:
        try:
            horizon = resolve_horizon_minutes(row)
            if horizon is None:
                skipped["unsupported-horizon"] += 1
                continue
            t = row.get("timestamp")
            if not isinstance(t, datetime):
                try:
                    t = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
                except Exception:
                    skipped["missing-timestamp"] += 1
                    continue
            t = _as_utc(t)
            if now < t + timedelta(minutes=int(horizon)):
                skipped["horizon-not-elapsed"] += 1
                continue
            symbol = row.get("instrument") or row.get("symbol") or ""
            window = classify_window(symbol, t, int(horizon), calendar=calendar)
            if not window.get("settleable"):
                skipped[str(window.get("reason") or "unsettled-window")] += 1
                continue
            fetcher = crypto_fetch if is_crypto_symbol(str(symbol)) else nse_fetch
            candles = await fetcher(
                str(symbol),
                t - timedelta(minutes=2),
                window["t_plus_h_utc"] + timedelta(minutes=2),
            )
            plan = plan_research_row(row, candles, now, calendar=calendar)
            if plan["action"] != "settle":
                skipped[str(plan.get("reason") or plan["action"])] += 1
                continue
            if dry_run:
                would_settle += 1
                continue
            outcome = build_research_outcome(
                row,
                outcome_spot=plan["outcome_spot"],
                outcome_label=plan["outcome_label"],
                candles_1m=candles,
                now_utc=now,
            )
            await PredictionService.append_outcome(outcome, session)
            settled += 1
        except Exception as e:
            errors += 1
            logger.warning("research_settle_row_failed", error=str(e)[:200])

    summary: dict[str, Any] = {
        "settled": settled,
        "skipped": dict(skipped),
        "errors": errors,
        "target_spec_version": TARGET_SPEC_VERSION_V2,
    }
    if dry_run:
        summary["would_settle"] = would_settle
        summary["dry_run"] = True
    logger.info("research_settle_run", **{k: v for k, v in summary.items() if k != "skipped"},
                skipped=summary["skipped"])
    return summary
