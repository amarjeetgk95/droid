"""CSV / report export helpers for the quant falsification module.

Pure formatting over already-computed metrics and trades — no market data
is synthesised here. Callers pass in rows produced by BacktestHarness or
the strategy-matrix endpoint.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Sequence


MATRIX_COLUMNS = [
    "strategy_key",
    "strategy_name",
    "total_trades",
    "win_rate",
    "gross_expectancy_pct",
    "net_expectancy_pct",
    "profit_factor",
    "max_drawdown_pct",
    "annualized_sharpe",
    "deflated_sharpe_ratio",
    "gate_g0_verdict",
    "verdict_reasons",
]

TRADE_COLUMNS = [
    "entry_time",
    "exit_time",
    "strategy_id",
    "direction",
    "gross_pnl_pct",
    "net_pnl_pct",
    "total_cost_pct",
    "exit_reason",
    "bars_held",
]


def _join_reasons(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " | ".join(str(v) for v in value)
    return "" if value is None else str(value)


def matrix_to_csv(rows: Sequence[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=MATRIX_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        flat = dict(row)
        flat["verdict_reasons"] = _join_reasons(row.get("verdict_reasons"))
        writer.writerow({k: flat.get(k, "") for k in MATRIX_COLUMNS})
    return buf.getvalue()


def trades_to_csv(trades: Sequence[dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=TRADE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for trade in trades:
        writer.writerow({k: trade.get(k, "") for k in TRADE_COLUMNS})
    return buf.getvalue()
