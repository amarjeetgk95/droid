"""Parse a request payload into validated backtest settings.

Shared by the API and by the optimizer / walk-forward / comparison layers so
every entry point interprets the same JSON identically. Bad values raise
``ValueError`` with a precise message; the API turns that into a 422 rather than
running with a default the user did not choose.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.indicator_research.backtesting.costs import cost_model_from
from app.indicator_research.backtesting.models import (
    BacktestSettings,
    ExecutionSettings,
    ExitSettings,
)
from app.indicator_research.enums import EntryFill, SizeMode, StopMode


def _number(payload: Mapping[str, Any], key: str, default: float) -> float:
    if key not in payload or payload[key] is None:
        return default
    try:
        return float(payload[key])
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' must be a number, got {payload[key]!r}") from None


def _flag(payload: Mapping[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


#: Recognised keys, so a typo fails loudly instead of silently defaulting.
_ROOT_KEYS = {"execution", "exits", "costs"}
_EXECUTION_KEYS = {
    "entry_fill",
    "size_mode",
    "initial_capital",
    "allocation_pct",
    "fixed_units",
    "leverage",
}
_EXIT_KEYS = {
    "stop_mode",
    "stop_value",
    "target_mode",
    "target_value",
    "max_bars_held",
    "exit_on_opposite",
    "allow_long",
    "allow_short",
    "exit_at_session_close",
}


def _reject_unknown(payload: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(
            f"Unknown setting(s) in {where}: {unknown}. Accepted: {sorted(allowed)}"
        )


def settings_from_payload(payload: Mapping[str, Any] | None) -> BacktestSettings:
    """Build :class:`BacktestSettings` from a partial JSON object."""
    root = dict(payload or {})
    _reject_unknown(root, _ROOT_KEYS, "settings")
    execution_raw = dict(root.get("execution") or {})
    exits_raw = dict(root.get("exits") or {})
    _reject_unknown(execution_raw, _EXECUTION_KEYS, "settings.execution")
    _reject_unknown(exits_raw, _EXIT_KEYS, "settings.exits")

    entry_fill = str(execution_raw.get("entry_fill") or EntryFill.NEXT_OPEN.value)
    if entry_fill not in (EntryFill.NEXT_OPEN.value, EntryFill.SIGNAL_CLOSE.value):
        raise ValueError(
            f"entry_fill must be '{EntryFill.NEXT_OPEN.value}' or "
            f"'{EntryFill.SIGNAL_CLOSE.value}', got {entry_fill!r}"
        )
    size_mode = str(execution_raw.get("size_mode") or SizeMode.FIXED_FRACTION.value)
    if size_mode not in {m.value for m in SizeMode}:
        raise ValueError(f"Unknown size_mode {size_mode!r}")

    execution = ExecutionSettings(
        entry_fill=entry_fill,
        size_mode=size_mode,
        initial_capital=_number(execution_raw, "initial_capital", 1_000_000.0),
        allocation_pct=_number(execution_raw, "allocation_pct", 1.0),
        fixed_units=_number(execution_raw, "fixed_units", 1.0),
        leverage=_number(execution_raw, "leverage", 1.0),
    )

    stop_mode = str(exits_raw.get("stop_mode") or StopMode.NONE.value)
    target_mode = str(exits_raw.get("target_mode") or StopMode.NONE.value)
    for label, mode in (("stop_mode", stop_mode), ("target_mode", target_mode)):
        if mode not in {m.value for m in StopMode}:
            raise ValueError(f"Unknown {label} {mode!r}")

    max_bars = exits_raw.get("max_bars_held")
    max_bars_held: int | None = None
    if max_bars not in (None, "", 0, "0"):
        try:
            max_bars_held = int(max_bars)
        except (TypeError, ValueError):
            raise ValueError(f"max_bars_held must be an integer, got {max_bars!r}") from None
        if max_bars_held < 1:
            raise ValueError("max_bars_held must be at least 1 bar")

    exits = ExitSettings(
        stop_mode=stop_mode,
        stop_value=_number(exits_raw, "stop_value", 0.0),
        target_mode=target_mode,
        target_value=_number(exits_raw, "target_value", 0.0),
        max_bars_held=max_bars_held,
        exit_on_opposite=_flag(exits_raw, "exit_on_opposite", True),
        allow_long=_flag(exits_raw, "allow_long", True),
        allow_short=_flag(exits_raw, "allow_short", True),
        exit_at_session_close=_flag(exits_raw, "exit_at_session_close", False),
    )

    return BacktestSettings(
        execution=execution, exits=exits, costs=cost_model_from(root.get("costs"))
    )


__all__ = ["settings_from_payload"]
