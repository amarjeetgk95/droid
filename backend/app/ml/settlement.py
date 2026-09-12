"""
Prediction Auto-Settlement — Phase 1

Settles predictions whose horizon has elapsed by looking up the realized
forward spot from historical 1m candles and labeling with the current
target spec. Session-crossing NSE windows are skipped as INSUFFICIENT_DATA
(never bridged across the close).

Candle fetchers are injectable so the planning logic is unit-testable
without brokers or a database.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import structlog

from app.ml.sessions import classify_window, is_crypto_symbol, resolve_forward_spot
from app.ml.targets import DEFAULT_HORIZON_MINUTES

logger = structlog.get_logger()

CandleFetcher = Callable[[str, datetime, datetime], Awaitable[list[Any]]]


async def fetch_nse_candles(symbol: str, start: datetime, end: datetime) -> list[Any]:
    """1m NSE candles for [start, end] via the configured broker provider."""
    from app.services.market_service import MarketService

    return await MarketService().get_candles(symbol, timeframe="1m", start=start, end=end)


async def fetch_crypto_candles(symbol: str, start: datetime, end: datetime) -> list[Any]:
    """Stub: crypto data source decommissioned."""
    return []


def plan_row(
    row: dict,
    candles: list[Any],
    now_utc: datetime,
    calendar: Any | None = None,
) -> dict:
    """Decide the settlement action for one unsettled prediction row.

    Row keys: symbol, timestamp (datetime), spot_price, horizon_minutes|None,
    atr_at_t|None. Returns {"action": "settle"|"wait"|"skip", ...}.
    Pure — no I/O.
    """
    horizon = row.get("horizon_minutes") or DEFAULT_HORIZON_MINUTES
    t = row["timestamp"]
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    t_plus_h = t + timedelta(minutes=horizon)

    if now_utc < t_plus_h:
        return {"action": "wait", "reason": "horizon-not-elapsed"}

    atr = float(row.get("atr_at_t") or 0.0)
    if atr <= 0:
        return {"action": "skip", "reason": "missing-atr-at-t"}

    window = classify_window(row["symbol"], t, horizon, calendar=calendar)
    if not window["settleable"]:
        return {"action": "skip", "reason": window["reason"]}

    spot, reason = resolve_forward_spot(candles, t, window["t_plus_h_utc"])
    if spot is None:
        return {"action": "skip", "reason": reason}
    return {"action": "settle", "outcome_spot": spot}


async def settle_due(
    session: Any,
    symbol: str | None = None,
    limit: int = 100,
    now_utc: datetime | None = None,
    nse_fetcher: CandleFetcher | None = None,
    crypto_fetcher: CandleFetcher | None = None,
    calendar: Any | None = None,
) -> dict:
    """Settle due predictions. Returns summary counts (settled/skipped/errors).

    Only touches rows with outcome_label IS NULL whose horizon has elapsed.
    Skips never fabricate — skipped rows stay unsettled for the next run.
    """
    from sqlalchemy import select

    from app.models.database import MLPredictionDB
    from app.repositories.ml_repository import MLRepository

    now = now_utc or datetime.now(timezone.utc)
    nse_fetch = nse_fetcher or fetch_nse_candles
    crypto_fetch = crypto_fetcher or fetch_crypto_candles

    stmt = (
        select(MLPredictionDB)
        .where(MLPredictionDB.outcome_label.is_(None))
        .order_by(MLPredictionDB.timestamp.asc())
        .limit(limit)
    )
    if symbol:
        stmt = stmt.where(MLPredictionDB.symbol == symbol.upper())
    pending = list((await session.execute(stmt)).scalars().all())

    settled = 0
    skipped: Counter = Counter()
    errors = 0

    for rec in pending:
        horizon = rec.horizon_minutes or DEFAULT_HORIZON_MINUTES
        t = rec.timestamp
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        if now < t + timedelta(minutes=horizon):
            skipped["horizon-not-elapsed"] += 1
            continue
        try:
            window = classify_window(rec.symbol, t, horizon, calendar=calendar)
            if not window["settleable"]:
                skipped[window["reason"]] += 1
                continue
            fetcher = crypto_fetch if is_crypto_symbol(rec.symbol) else nse_fetch
            candles = await fetcher(
                rec.symbol,
                t - timedelta(minutes=2),
                window["t_plus_h_utc"] + timedelta(minutes=2),
            )
            plan = plan_row(
                {
                    "symbol": rec.symbol,
                    "timestamp": t,
                    "spot_price": rec.spot_price,
                    "horizon_minutes": rec.horizon_minutes,
                    "atr_at_t": rec.atr_at_t,
                },
                candles,
                now,
                calendar=calendar,
            )
            if plan["action"] != "settle":
                skipped[plan["reason"]] += 1
                continue
            await MLRepository.settle_outcome(
                session,
                rec.id,
                outcome_spot=plan["outcome_spot"],
                atr_at_t=float(rec.atr_at_t or 0.0),
                spot_at_t=float(rec.spot_price),
            )
            settled += 1
        except Exception as e:
            errors += 1
            logger.warning("ml_settle_row_failed", error=str(e)[:200])

    summary = {"settled": settled, "skipped": dict(skipped), "errors": errors}
    logger.info("ml_settle_run", **summary)
    return summary
