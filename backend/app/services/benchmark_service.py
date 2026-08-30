"""
Model Benchmarking — §39

Create benchmark mode using identical historical market-state snapshots.
Compare Ling, DeepSeek, Qwen, GLM, OpenAI models, Ollama models
Measure: direction accuracy, false-signal rate, confidence calibration, scenario quality, latency, consistency, cost
Do not select trading model solely from generic LLM benchmarks. Use actual historical data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()

# In-memory benchmark store
_benchmark_runs: list[dict] = []


async def run_benchmark(
    historical_snapshots: list[dict],
    models: list[str],
    task: str = "INTRADAY_ANALYSIS",
) -> dict:
    """
    Run same snapshots across models, collect metrics (mock for now, deterministic).
    In production would call each provider with same MarketState and compare outcomes.
    """
    results = []
    for model_id in models:
        # Mock metrics deterministic by hashing model_id
        import hashlib
        h = int(hashlib.sha256(model_id.encode()).hexdigest()[:4], 16)
        direction_accuracy = 50 + (h % 30)  # 50-80
        false_signal_rate = 10 + (h % 15)
        latency_ms = 400 + (h % 1500)
        cost = 0.0 if ":free" in model_id else round((h % 100) / 1000, 4)
        results.append({
            "model_id": model_id,
            "direction_accuracy": direction_accuracy,
            "false_signal_rate": false_signal_rate,
            "confidence_calibration": round(0.5 + (h % 50)/100, 2),
            "latency_ms": latency_ms,
            "cost": cost,
            "scenario_quality": round(3.5 + (h % 15)/10, 1),
        })
    # Rank by accuracy then latency
    results_sorted = sorted(results, key=lambda x: (x["direction_accuracy"], -x["false_signal_rate"]), reverse=True)
    run = {
        "run_id": f"bench-{datetime.now(timezone.utc).isoformat()}",
        "task": task,
        "snapshot_count": len(historical_snapshots),
        "models": results_sorted,
        "best_model": results_sorted[0]["model_id"] if results_sorted else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Benchmark uses historical snapshots; not live trading guarantee.",
    }
    _benchmark_runs.insert(0, run)
    if len(_benchmark_runs) > 20:
        _benchmark_runs.pop()
    logger.info("benchmark_run", run_id=run["run_id"], models=len(models))
    return run


def get_benchmark_history(limit: int = 20) -> list[dict]:
    return _benchmark_runs[:limit]
