"""Minimal deterministic replay harness (Phase 1).

Answers "did I break the trading path?" in one command by replaying RECORDED
bars through the SAME quant primitives live promotion uses:

  bars -> CausalFeatureEngine -> BaselineStrategyEngine (S1/S2/S3) ->
  TripleBarrierLabelEngine -> costs -> BacktestMetrics -> promotion_gate

Determinism contract:
- Caller supplies bars (list of {ts,open,high,low,close,volume}); harness sorts
  by ts and never reads beyond bar t when emitting at t (causal; enforced by
  the underlying feature/strategy engines operating on closed bars only).
- Caller supplies seed; harness seeds random+numpy before the run and restores
  numpy state afterwards so suite order cannot leak.
- No wall-clock in the decision path: frozen_at is stamped on the REPORT only,
  never used for bars/labels/costs. No uuid in metrics.
- Live keeper names map to quant keys: ORB->S1, VOLATILITY_BREAKOUT/BREAKOUT->S2,
  VWAP_SCALP->S3. Research-only names raise (fail-closed): replay the keepers,
  backtest the rest offline via scripts.

This is the seed of the full feed->signal->risk->execution replay: today it
covers strategy+label+cost determinism (the layer where backtest vs live
diverged); execution replay (paper fills from chain marks) attaches next.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)

KEEPER_TO_QUANT_KEY: dict[str, str] = {
    "ORB": "S1",
    "VOLATILITY_BREAKOUT": "S2",
    "BREAKOUT": "S2",
    "VWAP_SCALP": "S3",
}

ReplayStrategy = Literal["ORB", "VOLATILITY_BREAKOUT", "BREAKOUT", "VWAP_SCALP"]


def _bars_to_frame(bars: list[dict[str, Any]]):
    """Validate + sort recorded bars into the polars frame the harness eats."""
    import polars as pl

    if not bars or len(bars) < 60:
        raise ValueError(f"Replay needs >=60 recorded bars, got {len(bars) if bars else 0}.")
    required = ("ts", "open", "high", "low", "close", "volume")
    for i, b in enumerate(bars):
        missing = [k for k in required if k not in b]
        if missing:
            raise ValueError(f"Bar {i} missing {missing}: fail-closed, no synthetic fill.")
    ordered = sorted(bars, key=lambda b: str(b["ts"]))
    ts_list = [str(b["ts"]) for b in ordered]
    if len(set(ts_list)) != len(ts_list):
        raise ValueError("Duplicate bar timestamps: replay must be a strict series.")
    try:
        ts_parsed = [b["ts"] if hasattr(b["ts"], "isoformat") and not isinstance(b["ts"], str)
                     else datetime.fromisoformat(str(b["ts"])) for b in ordered]
    except ValueError as e:
        raise ValueError(f"Unparsable bar timestamp: {e}. Supply ISO-8601.") from e
    return pl.DataFrame({
        "timestamp": ts_parsed,
        "open": [float(b["open"]) for b in ordered],
        "high": [float(b["high"]) for b in ordered],
        "low": [float(b["low"]) for b in ordered],
        "close": [float(b["close"]) for b in ordered],
        "volume": [float(b["volume"]) for b in ordered],
    })


def replay_bars(
    bars: list[dict[str, Any]],
    strategy: ReplayStrategy,
    seed: int = 42,
    stress_multiplier: float = 1.0,
    frozen_at: datetime | None = None,
) -> dict[str, Any]:
    """Replay recorded bars deterministically. Returns JSON-able report."""
    import numpy as np

    if strategy not in KEEPER_TO_QUANT_KEY:
        raise ValueError(
            f"Unknown/research-only strategy {strategy!r}: replay covers keepers "
            f"{sorted(KEEPER_TO_QUANT_KEY)} only."
        )
    quant_key = KEEPER_TO_QUANT_KEY[strategy]
    df = _bars_to_frame(bars)

    # Deterministic RNG: seed both stdlib and numpy, restore numpy afterwards.
    np_state = np.random.get_state()
    random.seed(seed)
    np.random.seed(seed)
    try:
        from app.quant.backtest.backtest_harness import BacktestHarness

        harness = BacktestHarness()
        trades, metrics = harness.run_backtest(
            df=df, strategy_key=quant_key, stress_multiplier=stress_multiplier
        )
    finally:
        np.random.set_state(np_state)

    stamped = frozen_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    metrics_dict = metrics.to_dict()
    metrics_dict["strategy_key"] = strategy
    metrics_dict["quant_key"] = quant_key
    metrics_dict["seed"] = seed
    metrics_dict["bars"] = len(bars)
    metrics_dict["stress_multiplier"] = stress_multiplier

    from app.quant.validation.promotion_gate import evaluate_strategy_promotion

    decision = evaluate_strategy_promotion(strategy, {
        "strategy_key": strategy,
        "total_trades": metrics_dict["total_trades"],
        "net_expectancy_pct": metrics_dict["net_expectancy_pct"],
        "profit_factor": metrics_dict["profit_factor"],
        "max_drawdown_pct": metrics_dict["max_drawdown_pct"],
        "deflated_sharpe_ratio": metrics_dict["deflated_sharpe_ratio"],
        "cost_survival_max_multiplier": metrics_dict["cost_survival_max_multiplier"],
    })

    report = {
        "strategy": strategy,
        "quant_key": quant_key,
        "seed": seed,
        "frozen_at": stamped.isoformat(),
        "bars": len(bars),
        "metrics": metrics_dict,
        "promotion": decision.to_dict(),
        "trades": [
            {
                "entry_time": t.entry_time.isoformat() if hasattr(t.entry_time, "isoformat") else str(t.entry_time),
                "exit_time": t.exit_time.isoformat() if hasattr(t.exit_time, "isoformat") else str(t.exit_time),
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "net_pnl_pct": t.net_pnl_pct,
                "exit_reason": t.exit_reason,
            }
            for t in trades[:200]
        ],
        "trades_truncated": max(0, len(trades) - 200),
        "total_trades": len(trades),
    }
    logger.info("replay_complete", strategy=strategy, trades=len(trades),
                verdict=decision.verdict, seed=seed)
    return report
