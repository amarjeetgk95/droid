"""Event-driven, strictly sequential backtesting engine (§9, §10, §11).

Design rules, in priority order:

1. **No bar may observe a later bar.** The loop advances one bar at a time and
   every decision reads only data at or before the current index.
2. **A signal confirmed by a close is filled at the next open** unless the
   caller explicitly selects ``signal_close``. Filling at the close that
   produced the signal is the single most common way a backtest invents money;
   it stays available, but it is opt-in and the result records the choice.
3. **Ambiguity is resolved pessimistically.** When a bar's range contains both
   the stop and the target, the stop is assumed to have been hit first. When a
   bar gaps through the stop, the fill is the open — worse than the stop — not
   the stop itself.
4. **Costs are charged explicitly.** ``gross_pnl`` is measured at reference
   (unslipped) prices so signal quality is visible on its own; slippage and fees
   are then subtracted in ``costs`` to produce ``net_pnl``.
5. **Signals are data.** Rules are validated JSON, evaluated per bar, and can
   never reference a future bar because no operator exists that can.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

import structlog

from app.indicator_research.backtesting.costs import CostModel
from app.indicator_research.backtesting.metrics import compute_metrics, group_metrics
from app.indicator_research.backtesting.models import (
    BacktestResult,
    BacktestSettings,
    EquityPoint,
    Trade,
)
from app.indicator_research.backtesting.validation import validate_backtest
from app.indicator_research.enums import EntryFill, PositionSide, SizeMode, StopMode
from app.indicator_research.indicators.helpers import PRICE_COLUMNS, ohlcv_features
from app.indicator_research.signals.rules import (
    RuleError,
    describe_rule,
    evaluate_series,
    normalize_rule,
)

logger = structlog.get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

#: Price columns always available to rules, sourced directly from candles.
_PRICE_COLUMNS = PRICE_COLUMNS

#: Intraday session close used by ``exit_at_session_close`` (IST).
_SESSION_CLOSE_BUFFER = (15, 20)

#: Minimum bars used to classify a regime at entry.
_REGIME_LOOKBACK = 50


def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _timestamp(candle: Mapping[str, Any]) -> str | None:
    raw = candle.get("timestamp")
    if isinstance(raw, datetime):
        return raw.isoformat()
    if raw is None:
        return None
    return str(raw)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ist(value: Any) -> datetime | None:
    dt = _parse_ts(value)
    if dt is None:
        return None
    try:
        return dt.astimezone(IST)
    except Exception:  # pragma: no cover - tz database missing
        return None


def time_bucket(value: Any) -> str:
    """IST session bucket for a timestamp.

    Buckets are defined on the NSE regular session so an order-flow or
    liquidity story can be attached to a trade without pretending the
    definition is universal.
    """
    dt = _ist(value)
    if dt is None:
        return "UNKNOWN"
    minutes = dt.hour * 60 + dt.minute
    if minutes < 9 * 60 + 15:
        return "PRE_OPEN"
    if minutes < 10 * 60 + 15:
        return "OPEN"
    if minutes < 12 * 60:
        return "MORNING"
    if minutes < 13 * 60 + 30:
        return "MIDDAY"
    if minutes < 14 * 60 + 45:
        return "AFTERNOON"
    if minutes <= 15 * 60 + 30:
        return "CLOSE"
    return "POST_CLOSE"


def holding_bucket(bars: int) -> str:
    if bars <= 3:
        return "1-3 bars"
    if bars <= 10:
        return "4-10 bars"
    if bars <= 30:
        return "11-30 bars"
    if bars <= 100:
        return "31-100 bars"
    return "100+ bars"


def classify_regime(
    candles: Sequence[Mapping[str, Any]], index: int, lookback: int = _REGIME_LOOKBACK
) -> str:
    """Causal regime label from the Kaufman efficiency ratio.

    ``efficiency = |net move| / sum(|bar moves|)`` — 1.0 is a perfect trend, ~0
    is pure chop. This is used instead of an indicator reading because it does
    not depend on any indicator's warm-up or scale, and it is computed from bars
    ``[index-lookback+1 .. index]`` only.

    The label is a bookkeeping convenience for slicing results. It is *not* an
    input to the strategy, and the thresholds are stated rather than learned.
    """
    start = max(0, index - lookback + 1)
    if index - start + 1 < 10:
        return "UNKNOWN"
    closes = [_finite(candles[i].get("close")) for i in range(start, index + 1)]
    if any(c is None for c in closes):
        return "UNKNOWN"
    values = [float(c) for c in closes]  # type: ignore[arg-type]
    net = abs(values[-1] - values[0])
    path = sum(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
    if path <= 0:
        return "UNKNOWN"
    efficiency = net / path
    if efficiency < 0.3:
        return "RANGE"
    return "TREND_UP" if values[-1] > values[0] else "TREND_DOWN"


class BacktestEngine:
    """Sequential backtester over precomputed features and JSON rules."""

    def __init__(self, costs: CostModel | None = None) -> None:
        self._costs = costs

    # ------------------------------------------------------------------ #
    def run(
        self,
        *,
        candles: Sequence[Mapping[str, Any]],
        features: Mapping[str, Sequence[Any]] | None = None,
        long_rule: Mapping[str, Any] | None = None,
        short_rule: Mapping[str, Any] | None = None,
        settings: BacktestSettings | None = None,
        instrument: str = "",
        timeframe: str = "",
        indicator_id: str | None = None,
        indicator_version: str | None = None,
        params: Mapping[str, Any] | None = None,
        output_names: Sequence[str] | None = None,
        warmup_bars: int = 0,
        requested_start: str | None = None,
        requested_end: str | None = None,
        run_indicator_causality_check: bool = True,
        indicator: Any = None,
    ) -> BacktestResult:
        """Run one backtest.

        ``indicator`` is optional and only used to re-verify causality on
        truncated prefixes. Passing it enables the strongest validation; the
        engine still enforces sequential access without it.
        """
        settings = settings or BacktestSettings()
        result = BacktestResult(
            ok=False,
            instrument=instrument,
            timeframe=timeframe,
            requested_start=requested_start,
            requested_end=requested_end,
            indicator_id=indicator_id,
            indicator_version=indicator_version,
            params=dict(params or {}),
            output_names=list(output_names or []),
            settings=settings.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        if not candles:
            result.error = (
                "No candles were supplied for the requested instrument, timeframe "
                "and date range."
            )
            return result

        length = len(candles)
        result.bars = length
        result.data_start = _timestamp(candles[0])
        result.data_end = _timestamp(candles[-1])

        # ── features ─────────────────────────────────────────────────────
        base_features = self._price_features(candles)
        extra = {name: list(values) for name, values in (features or {}).items()}
        clash = sorted(set(extra) & set(_PRICE_COLUMNS))
        if clash:
            result.error = (
                f"Indicator output name(s) {clash} collide with price columns; "
                "rename them in the indicator metadata."
            )
            return result
        for name, values in extra.items():
            if len(values) != length:
                result.error = (
                    f"Feature '{name}' has length {len(values)} but the candle "
                    f"series has {length}; features must be index-aligned."
                )
                return result
        all_features: dict[str, Sequence[Any]] = {**base_features, **extra}
        available = tuple(sorted(all_features))

        # ── settings validation ──────────────────────────────────────────
        execution = settings.execution
        exits = settings.exits
        costs = self._costs or settings.costs

        if execution.entry_fill not in (EntryFill.NEXT_OPEN.value, EntryFill.SIGNAL_CLOSE.value):
            result.error = (
                f"entry_fill must be '{EntryFill.NEXT_OPEN.value}' or "
                f"'{EntryFill.SIGNAL_CLOSE.value}', got {execution.entry_fill!r}"
            )
            return result
        if exits.stop_mode not in {m.value for m in StopMode}:
            result.error = f"Unknown stop_mode {exits.stop_mode!r}"
            return result
        if exits.target_mode not in {m.value for m in StopMode}:
            result.error = f"Unknown target_mode {exits.target_mode!r}"
            return result
        if exits.stop_mode == StopMode.ATR.value or exits.target_mode == StopMode.ATR.value:
            if "atr" not in all_features:
                result.error = (
                    "ATR-based stops need an ATR output. Add the 'atr' indicator to "
                    "the feature set, or use percent/points stops."
                )
                return result
        if execution.size_mode not in {m.value for m in SizeMode}:
            result.error = f"Unknown size_mode {execution.size_mode!r}"
            return result
        if execution.initial_capital <= 0:
            result.error = "initial_capital must be positive"
            return result
        if not (0 < execution.allocation_pct <= 1):
            result.error = "allocation_pct must be between 0 (exclusive) and 1"
            return result
        if exits.max_bars_held is not None and exits.max_bars_held < 1:
            result.error = "max_bars_held must be at least 1 bar"
            return result

        # ── rules ────────────────────────────────────────────────────────
        try:
            long_norm = normalize_rule(long_rule)
            short_norm = normalize_rule(short_rule)
        except RuleError as e:
            result.error = f"Invalid signal rule: {e}"
            return result

        try:
            long_signals = evaluate_series(long_norm, all_features, length)
            short_signals = evaluate_series(short_norm, all_features, length)
        except RuleError as e:
            # A rule naming a feature that was never supplied must fail loudly:
            # evaluating it as "never true" would look like a valid, quiet result.
            result.error = f"Invalid signal rule: {e}"
            return result
        warmup = max(0, int(warmup_bars or 0))
        for i in range(min(warmup, length)):
            long_signals[i] = False
            short_signals[i] = False
        if not exits.allow_long:
            long_signals = [False] * length
        if not exits.allow_short:
            short_signals = [False] * length

        result.signal_rule_summary = {
            "long": describe_rule(long_norm),
            "short": describe_rule(short_norm),
        }

        if not any(long_signals) and not any(short_signals):
            # Shape the response like every other run so callers never have to
            # special-case a missing key.
            result.signals = {"long": [], "short": []}
            result.assumptions = self._assumptions(execution, exits, costs)
            result.validation = {
                "no_lookahead": True,
                "repaint_free": True,
                "badge": "✓ NO LOOKAHEAD",
                "issues": ["No signal fired in this date range."],
            }
            result.metrics = compute_metrics(
                [], [], initial_capital=execution.initial_capital, timeframe=timeframe, total_bars=length
            )
            result.cost_summary = self._cost_summary(costs, [])
            result.ok = True
            return result

        # ── sequential simulation ────────────────────────────────────────
        simulation = self._simulate(
            candles=candles,
            all_features=all_features,
            long_signals=long_signals,
            short_signals=short_signals,
            execution=execution,
            exits=exits,
            costs=costs,
            instrument=instrument,
        )

        trades: list[Trade] = simulation["trades"]
        equity_curve: list[EquityPoint] = simulation["equity_curve"]

        result.trades = trades
        result.equity_curve = equity_curve
        result.signals = {
            "long": [i for i, v in enumerate(long_signals) if v],
            "short": [i for i, v in enumerate(short_signals) if v],
        }
        result.metrics = compute_metrics(
            trades,
            equity_curve,
            initial_capital=execution.initial_capital,
            timeframe=timeframe,
            total_bars=length,
        )
        result.by_regime = group_metrics(trades, "regime", {})
        result.by_time_of_day = group_metrics(trades, "time_bucket", {})
        result.by_side = group_metrics(trades, "side", {})
        result.cost_summary = self._cost_summary(costs, trades)
        result.assumptions = self._assumptions(execution, exits, costs)

        result.validation = validate_backtest(
            candles=candles,
            features=all_features,
            long_rule=long_norm,
            short_rule=short_norm,
            long_signals=long_signals,
            short_signals=short_signals,
            trades=trades,
            settings=settings,
            warmup_bars=warmup,
            indicator=indicator if run_indicator_causality_check else None,
            indicator_params=dict(params or {}),
        )
        result.ok = True
        return result

    # ------------------------------------------------------------------ #
    # Simulation
    # ------------------------------------------------------------------ #
    def _simulate(
        self,
        *,
        candles: Sequence[Mapping[str, Any]],
        all_features: Mapping[str, Sequence[Any]],
        long_signals: Sequence[bool],
        short_signals: Sequence[bool],
        execution: Any,
        exits: Any,
        costs: CostModel,
        instrument: str,
    ) -> dict[str, Any]:
        n = len(candles)
        atr_column = all_features.get("atr")
        next_open = execution.entry_fill == EntryFill.NEXT_OPEN.value

        equity = float(execution.initial_capital)
        peak = equity
        position: dict[str, Any] | None = None
        pending_entry: tuple[int, str] | None = None
        pending_exit: tuple[int, str] | None = None

        trades: list[Trade] = []
        equity_curve: list[EquityPoint] = []

        for i in range(n):
            candle = candles[i]
            o = _finite(candle.get("open"))
            h = _finite(candle.get("high"))
            lo = _finite(candle.get("low"))
            c = _finite(candle.get("close"))
            bar_complete = None not in (o, h, lo, c)
            bar_ist = _ist(candle.get("timestamp"))
            time_str = _timestamp(candle)
            exited_this_bar = False
            trade_closed: Trade | None = None

            # (0) An opposite-signal exit queued at the previous close fills now.
            if position is not None and pending_exit is not None and pending_exit[0] == i - 1:
                if bar_complete:
                    trade_closed = self._close(
                        position, i, time_str, o, pending_exit[1], costs
                    )
                if trade_closed is not None:
                    equity = trade_closed.equity_after
                    trades.append(trade_closed)
                    position = None
                    exited_this_bar = True
                pending_exit = None

            # (1) A queued next-open entry fills at this bar's open, before the
            #     bar's own range is examined — so its stop can trigger intraday.
            if position is None and pending_entry is not None and pending_entry[0] == i - 1:
                if bar_complete and entry_allowed(pending_entry[1], exits):
                    position = self._open(
                        side=pending_entry[1],
                        signal_index=pending_entry[0],
                        signal_time=_timestamp(candles[pending_entry[0]]),
                        entry_index=i,
                        entry_time=time_str,
                        reference_price=o,
                        costs=costs,
                        equity=equity,
                        execution=execution,
                        exits=exits,
                        atr_value=atr_column[i] if atr_column is not None else None,
                        regime=classify_regime(candles, i),
                    )
                pending_entry = None

            # (2) Price-based exits on the current bar.
            if position is not None and bar_complete:
                exit_price, reason = self._exit_trigger(
                    position, i, o, h, lo, c, exits, bar_ist
                )
                if exit_price is not None:
                    trade_closed = self._close(
                        position, i, time_str, exit_price, reason, costs
                    )
                    equity = trade_closed.equity_after
                    trades.append(trade_closed)
                    position = None
                    exited_this_bar = True

            # (3) New signals, read at this bar's close.
            if position is None and not exited_this_bar and bar_complete:
                side = None
                if long_signals[i] and exits.allow_long:
                    side = PositionSide.LONG.value
                elif short_signals[i] and exits.allow_short:
                    side = PositionSide.SHORT.value
                if side is not None:
                    if next_open:
                        # Filled at the next bar's open. If this is the final
                        # bar there is no next bar, so the signal never fills.
                        if i + 1 < n:
                            pending_entry = (i, side)
                    else:
                        pending_entry = None
                        position = self._open(
                            side=side,
                            signal_index=i,
                            signal_time=time_str,
                            entry_index=i,
                            entry_time=time_str,
                            reference_price=c,
                            costs=costs,
                            equity=equity,
                            execution=execution,
                            exits=exits,
                            atr_value=atr_column[i] if atr_column is not None else None,
                            entry_basis="close",
                            regime=classify_regime(candles, i),
                        )

            # (4) Opposite-signal exit intent, acted on at the next open.
            if (
                position is not None
                and not exited_this_bar
                and exits.exit_on_opposite
                and i > position["entry_index"]
                and bar_complete
            ):
                opposite = (
                    short_signals[i]
                    if position["side"] == PositionSide.LONG.value
                    else long_signals[i]
                )
                if opposite and pending_exit is None:
                    pending_exit = (i, "opposite_signal")

            # (5) Excursions. A close-based entry must not count the bar it was
            #     filled on: that bar's high/low happened before the entry.
            if (
                position is not None
                and not exited_this_bar
                and bar_complete
                and not (
                    position.get("entry_basis") == "close" and i == position["entry_index"]
                )
            ):
                reference = position["entry_reference"]
                if position["side"] == PositionSide.LONG.value:
                    position["mfe"] = max(position["mfe"], h - reference)
                    position["mae"] = max(position["mae"], reference - lo)
                else:
                    position["mfe"] = max(position["mfe"], reference - lo)
                    position["mae"] = max(position["mae"], h - reference)

            # (6) Mark to market.
            equity_now = equity
            if position is not None and c is not None:
                direction = 1.0 if position["side"] == PositionSide.LONG.value else -1.0
                equity_now = equity + (c - position["entry_price"]) * position["quantity"] * direction
            peak = max(peak, equity_now)
            dd_pct = 0.0 if peak <= 0 else 100.0 * (peak - equity_now) / peak
            equity_curve.append(
                EquityPoint(
                    index=i,
                    time=time_str,
                    equity=round(equity_now, 4),
                    drawdown_pct=round(dd_pct, 6),
                    in_position=position is not None,
                )
            )

        # ── force-close anything still open at the last bar ──────────────
        if position is not None:
            last = n - 1
            last_close = _finite(candles[last].get("close"))
            if last_close is not None:
                trade_closed = self._close(
                    position, last, _timestamp(candles[last]), last_close, "end_of_data", costs
                )
                trades.append(trade_closed)
                if equity_curve:
                    final = equity_curve[-1]
                    final.equity = round(trade_closed.equity_after, 4)
                    if peak > 0:
                        final.drawdown_pct = round(
                            100.0 * (peak - final.equity) / peak, 6
                        )
                    final.in_position = False

        for index, trade in enumerate(trades, start=1):
            trade.trade_id = index
        return {"trades": trades, "equity_curve": equity_curve}

    # ------------------------------------------------------------------ #
    # Position lifecycle
    # ------------------------------------------------------------------ #
    def _open(
        self,
        *,
        side: str,
        signal_index: int,
        signal_time: str | None,
        entry_index: int,
        entry_time: str | None,
        reference_price: float,
        costs: CostModel,
        equity: float,
        execution: Any,
        exits: Any,
        atr_value: Any,
        entry_basis: str = "open",
        regime: str | None = None,
    ) -> dict[str, Any]:
        entry_side = "buy" if side == PositionSide.LONG.value else "sell"
        fill = costs.fill_price(reference_price, entry_side)
        if execution.size_mode == SizeMode.FIXED_UNITS.value:
            quantity = float(execution.fixed_units)
        else:
            notional = equity * float(execution.allocation_pct) * float(execution.leverage)
            quantity = notional / fill if fill > 0 else 0.0

        atr_float = _finite(atr_value)
        direction = 1.0 if side == PositionSide.LONG.value else -1.0
        stop = self._level(exits.stop_mode, exits.stop_value, fill, atr_float, direction, is_stop=True)
        target = self._level(
            exits.target_mode, exits.target_value, fill, atr_float, direction, is_stop=False
        )

        return {
            "side": side,
            "signal_index": signal_index,
            "signal_time": signal_time,
            "entry_index": entry_index,
            "entry_time": entry_time,
            "entry_reference": reference_price,
            "entry_price": fill,
            "entry_basis": entry_basis,
            "quantity": quantity,
            "stop": stop,
            "target": target,
            "mfe": 0.0,
            "mae": 0.0,
            "equity_before": equity,
            "regime": regime,
        }

    @staticmethod
    def _level(
        mode: str,
        value: float,
        fill: float,
        atr_value: float | None,
        direction: float,
        *,
        is_stop: bool,
    ) -> float | None:
        """Absolute stop / target price, or ``None`` when disabled."""
        if mode == StopMode.NONE.value or value <= 0:
            return None
        if mode == StopMode.PERCENT.value:
            distance = fill * value / 100.0
        elif mode == StopMode.POINTS.value:
            distance = value
        elif mode == StopMode.ATR.value:
            if atr_value is None:
                return None
            distance = atr_value * value
        else:  # pragma: no cover - validated by the caller
            return None
        if is_stop:
            return fill - distance if direction > 0 else fill + distance
        return fill + distance if direction > 0 else fill - distance

    def _exit_trigger(
        self,
        position: Mapping[str, Any],
        index: int,
        open_price: float,
        high: float,
        low: float,
        close: float,
        exits: Any,
        bar_ist: datetime | None = None,
    ) -> tuple[float | None, str]:
        """Price at which the position must exit on this bar, and why.

        Order matters and is deliberate: gap first (the open is the only price
        available), then stop before target (pessimistic intrabar assumption),
        then the time stop.
        """
        long_side = position["side"] == PositionSide.LONG.value
        stop = position.get("stop")
        target = position.get("target")

        if stop is not None:
            if long_side and open_price <= stop:
                return open_price, "stop_loss"
            if not long_side and open_price >= stop:
                return open_price, "stop_loss"
        if target is not None:
            if long_side and open_price >= target:
                return open_price, "take_profit"
            if not long_side and open_price <= target:
                return open_price, "take_profit"

        if stop is not None:
            if long_side and low <= stop:
                return stop, "stop_loss"
            if not long_side and high >= stop:
                return stop, "stop_loss"
        if target is not None:
            if long_side and high >= target:
                return target, "take_profit"
            if not long_side and low <= target:
                return target, "take_profit"

        max_bars = exits.max_bars_held
        if max_bars is not None and index - position["entry_index"] >= int(max_bars):
            return close, "max_bars"

        if exits.exit_at_session_close and bar_ist is not None:
            minutes = bar_ist.hour * 60 + bar_ist.minute
            cutoff = _SESSION_CLOSE_BUFFER[0] * 60 + _SESSION_CLOSE_BUFFER[1]
            if minutes >= cutoff:
                return close, "session_close"
        return None, ""

    def _close(
        self,
        position: Mapping[str, Any],
        index: int,
        time_str: str | None,
        reference_price: float,
        reason: str,
        costs: CostModel,
    ) -> Trade:
        side = position["side"]
        long_side = side == PositionSide.LONG.value
        exit_side = "sell" if long_side else "buy"
        fill = costs.fill_price(reference_price, exit_side)
        quantity = position["quantity"]
        direction = 1.0 if long_side else -1.0

        entry_reference = position["entry_reference"]
        entry_price = position["entry_price"]
        entry_notional = entry_price * quantity
        exit_notional = fill * quantity

        # Gross P&L is measured at reference prices so signal quality is not
        # entangled with execution assumptions; slippage is then charged as a
        # cost rather than silently embedded in the fill.
        gross = (reference_price - entry_reference) * quantity * direction
        slippage_per_unit = abs(entry_price - entry_reference) + abs(fill - reference_price)
        slippage_cost = slippage_per_unit * quantity
        fees = costs.fee_amount(entry_notional, "buy") + costs.fee_amount(exit_notional, "sell")
        total_costs = slippage_cost + fees
        net = gross - total_costs
        equity_after = position["equity_before"] + net
        return_pct = (
            100.0 * net / position["equity_before"] if position["equity_before"] else 0.0
        )

        bars_held = max(0, index - position["entry_index"])
        mae = max(0.0, position["mae"])
        mfe = max(0.0, position["mfe"])
        return Trade(
            trade_id=0,
            side=side,
            signal_index=position["signal_index"],
            signal_time=position["signal_time"],
            entry_index=position["entry_index"],
            entry_time=position["entry_time"],
            entry_price=round(entry_price, 6),
            entry_reference_price=round(entry_reference, 6),
            exit_index=index,
            exit_time=time_str,
            exit_price=round(fill, 6),
            exit_reference_price=round(reference_price, 6),
            exit_reason=reason,
            quantity=round(quantity, 8),
            entry_notional=round(entry_notional, 4),
            exit_notional=round(exit_notional, 4),
            bars_held=bars_held,
            gross_pnl=round(gross, 4),
            costs=round(total_costs, 4),
            net_pnl=round(net, 4),
            return_pct=round(return_pct, 6),
            mae=round(mae, 6),
            mfe=round(mfe, 6),
            mae_pct=round(100.0 * mae / entry_reference, 4) if entry_reference else 0.0,
            mfe_pct=round(100.0 * mfe / entry_reference, 4) if entry_reference else 0.0,
            stop_price=position.get("stop"),
            target_price=position.get("target"),
            equity_before=round(position["equity_before"], 4),
            equity_after=round(equity_after, 4),
            regime=position.get("regime"),
            time_bucket=time_bucket(position.get("entry_time")),
            holding_bucket=holding_bucket(bars_held),
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _price_features(
        candles: Sequence[Mapping[str, Any]],
    ) -> dict[str, list[float | None]]:
        return ohlcv_features(candles)

    @staticmethod
    def _cost_summary(costs: CostModel, trades: Sequence[Trade]) -> dict[str, Any]:
        total_costs = sum(t.costs for t in trades)
        gross = sum(t.gross_pnl for t in trades)
        net = sum(t.net_pnl for t in trades)
        return {
            "cost_model": costs.to_dict(),
            "total_costs": round(total_costs, 4),
            "cost_per_trade": round(total_costs / len(trades), 4) if trades else 0.0,
            "gross_pnl_total": round(gross, 4),
            "net_pnl_total": round(net, 4),
            "cost_as_pct_of_gross": (
                round(100.0 * total_costs / abs(gross), 4) if gross else None
            ),
            "note": (
                "Gross P&L is measured at reference (unslipped) prices; slippage is "
                "charged as a cost so signal quality and execution drag stay separable."
            ),
        }

    @staticmethod
    def _assumptions(execution: Any, exits: Any, costs: CostModel) -> list[str]:
        assumptions = [
            (
                "Signals are read at the close of the bar that produced them and "
                "filled at the next bar's open."
                if execution.entry_fill == EntryFill.NEXT_OPEN.value
                else (
                    "Signals and fills both occur at the signal bar's close. This is "
                    "an optimistic fill model: it assumes the close that generated the "
                    "signal was still available to trade."
                )
            ),
            (
                "When a bar's range contains both the stop and the target, the stop is "
                "assumed to have been hit first (pessimistic intrabar ordering)."
            ),
            (
                "A gap through the stop or target fills at the bar's open, which can be "
                "worse than the stop price."
            ),
            (
                f"Costs: {costs.buy_bps():.2f} bps buy / {costs.sell_bps():.2f} bps sell "
                f"({costs.version}). Slippage is charged on both sides."
            ),
            (
                "Position sizing: "
                + (
                    f"{execution.allocation_pct:.0%} of current equity per trade at "
                    f"{execution.leverage:g}x leverage, fractional units."
                    if execution.size_mode == SizeMode.FIXED_FRACTION.value
                    else f"{execution.fixed_units:g} fixed units per trade."
                )
            ),
            (
                "No partial fills, no liquidity limit and no margin call are modelled; "
                "the equity curve assumes every order filled in full."
            ),
            (
                "Signals are suppressed for the indicator's warm-up window, so no trade "
                "is taken on an undefined reading."
            ),
            (
                "Regime labels come from the Kaufman efficiency ratio over the trailing "
                "50 bars (< 0.3 = range). They describe the entry context; they are not "
                "a strategy input."
            ),
        ]
        if exits.stop_mode == StopMode.ATR.value or exits.target_mode == StopMode.ATR.value:
            assumptions.append(
                "ATR-based levels are set from the ATR value at the entry bar, then held "
                "fixed for the life of the trade (no trailing stop)."
            )
        if exits.max_bars_held is None:
            assumptions.append(
                "No time stop: a position stays open until it hits its stop, its target, "
                "an opposite signal, or the end of the data."
            )
        if not exits.exit_at_session_close:
            assumptions.append(
                "Positions are not forced flat at the session close, so a trade can span "
                "overnight (relevant for intraday timeframes)."
            )
        return assumptions


def entry_allowed(side: str, exits: Any) -> bool:
    if side == PositionSide.LONG.value:
        return bool(exits.allow_long)
    return bool(exits.allow_short)


__all__ = ["BacktestEngine", "classify_regime", "holding_bucket", "time_bucket"]
