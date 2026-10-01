"""Shared dataclasses for the backtesting layer.

Kept separate from ``engine`` so ``metrics`` and ``validation`` can import the
types without importing the engine (and creating an import cycle).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.indicator_research.backtesting.costs import REFERENCE_COSTS_V1, CostModel
from app.indicator_research.enums import EntryFill, SizeMode, StopMode

SignalSide = Literal["LONG", "SHORT"]


@dataclass
class Trade:
    """One completed round trip, with excursion and cost detail."""

    trade_id: int
    side: str
    signal_index: int
    signal_time: str | None
    entry_index: int
    entry_time: str | None
    entry_price: float
    entry_reference_price: float
    exit_index: int | None = None
    exit_time: str | None = None
    exit_price: float | None = None
    exit_reference_price: float | None = None
    exit_reason: str | None = None
    quantity: float = 0.0
    entry_notional: float = 0.0
    exit_notional: float = 0.0
    bars_held: int = 0
    gross_pnl: float = 0.0
    costs: float = 0.0
    net_pnl: float = 0.0
    return_pct: float = 0.0
    mae: float = 0.0
    mfe: float = 0.0
    mae_pct: float = 0.0
    mfe_pct: float = 0.0
    stop_price: float | None = None
    target_price: float | None = None
    equity_before: float = 0.0
    equity_after: float = 0.0
    regime: str | None = None
    time_bucket: str | None = None
    holding_bucket: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExitSettings:
    """Stop / target / time-stop configuration.

    ``stop_mode``/``target_mode`` of ``atr`` require an ``atr`` feature to be
    present; the engine refuses to run rather than silently substituting zero.
    """

    stop_mode: str = StopMode.NONE.value
    stop_value: float = 0.0
    target_mode: str = StopMode.NONE.value
    target_value: float = 0.0
    max_bars_held: int | None = None
    exit_on_opposite: bool = True
    allow_long: bool = True
    allow_short: bool = True
    exit_at_session_close: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionSettings:
    """Fill model and position sizing."""

    entry_fill: str = EntryFill.NEXT_OPEN.value
    size_mode: str = SizeMode.FIXED_FRACTION.value
    initial_capital: float = 1_000_000.0
    allocation_pct: float = 1.0
    fixed_units: float = 1.0
    leverage: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestSettings:
    """Everything the engine needs beyond candles, features and rules."""

    execution: ExecutionSettings = field(default_factory=ExecutionSettings)
    exits: ExitSettings = field(default_factory=ExitSettings)
    costs: CostModel = field(default_factory=lambda: REFERENCE_COSTS_V1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution": self.execution.to_dict(),
            "exits": self.exits.to_dict(),
            "costs": self.costs.to_dict(),
        }


@dataclass
class EquityPoint:
    """One mark-to-market equity observation."""

    index: int
    time: str | None
    equity: float
    drawdown_pct: float
    in_position: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BacktestResult:
    """Complete, self-describing output of one backtest run."""

    ok: bool
    error: str | None = None
    instrument: str = ""
    timeframe: str = ""
    requested_start: str | None = None
    requested_end: str | None = None
    data_start: str | None = None
    data_end: str | None = None
    bars: int = 0
    indicator_id: str | None = None
    indicator_version: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    output_names: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    signal_rule_summary: dict[str, str] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    signals: dict[str, list[int]] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    by_regime: dict[str, Any] = field(default_factory=dict)
    by_time_of_day: dict[str, Any] = field(default_factory=dict)
    by_side: dict[str, Any] = field(default_factory=dict)
    cost_summary: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    generated_at: str | None = None

    def to_dict(
        self,
        *,
        include_trades: bool = True,
        include_equity_curve: bool = True,
        max_equity_points: int = 2000,
    ) -> dict[str, Any]:
        """Serialise, optionally thinning the equity curve for the wire."""
        payload: dict[str, Any] = {
            "ok": self.ok,
            "error": self.error,
            "instrument": self.instrument,
            "timeframe": self.timeframe,
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "data_start": self.data_start,
            "data_end": self.data_end,
            "bars": self.bars,
            "indicator_id": self.indicator_id,
            "indicator_version": self.indicator_version,
            "params": self.params,
            "output_names": self.output_names,
            "settings": self.settings,
            "signal_rule_summary": self.signal_rule_summary,
            "metrics": self.metrics,
            "by_regime": self.by_regime,
            "by_time_of_day": self.by_time_of_day,
            "by_side": self.by_side,
            "cost_summary": self.cost_summary,
            "validation": self.validation,
            "assumptions": self.assumptions,
            "generated_at": self.generated_at,
            "trade_count": len(self.trades),
            "signals": {k: list(v) for k, v in self.signals.items()},
        }
        if include_trades:
            payload["trades"] = [t.to_dict() for t in self.trades]
        if include_equity_curve:
            if max_equity_points > 0 and len(self.equity_curve) > max_equity_points:
                step = max(1, len(self.equity_curve) // max_equity_points)
                thinned = self.equity_curve[::step]
                if thinned and thinned[-1] is not self.equity_curve[-1]:
                    thinned = thinned + [self.equity_curve[-1]]
                payload["equity_curve"] = [p.to_dict() for p in thinned]
                payload["equity_curve_thinned"] = {
                    "original_points": len(self.equity_curve),
                    "returned_points": len(thinned),
                    "step": step,
                }
            else:
                payload["equity_curve"] = [p.to_dict() for p in self.equity_curve]
        return payload


__all__ = [
    "BacktestResult",
    "BacktestSettings",
    "EquityPoint",
    "ExecutionSettings",
    "ExitSettings",
    "Trade",
]
