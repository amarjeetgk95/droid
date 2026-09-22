"""S6 Research MVP CLI Runner (S6SPEC_v1.3).

Executes the registered 2x2 core triage matrix:
- Track A: S6A_T1 (5m context + 1m structural breakout + 1m execution)
- Track B: S6A_T4 (5m context + 5m structural breakout + 5m execution)
- Track C: S6F_T1 (5m context + 1m structural breakout + failure reversal on 1m)
- Track D: S6F_T4 (5m context + 5m structural breakout + failure reversal on 5m)

Modes:
- smoke: Synthetic fixture data for end-to-end software verification
- historical: Historical cleaned futures dataset
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import polars as pl
import structlog

from app.quant.data.provenance import assert_real_dataset
from app.quant.strategies.s6_config import (
    S6Config,
    S6Variant,
    S6TimeframeBranch,
    create_default_config,
)
from app.quant.strategies.s6_events import (
    S6EventEngine,
    resample_to_completed_5m,
    compute_5m_features,
    CompressionEpisode,
    RawBreakoutEvent,
    FailureEvent,
    EntryCandidate,
)
from app.quant.strategies.s6_a import S6AScanner
from app.quant.strategies.s6_f import S6FScanner
from app.quant.execution.s6_simulator import S6ExecutionSimulator, S6Trade
from app.quant.research.s6_metrics import calculate_s6_metrics, S6MetricsReport
from app.quant.research.s6_registry import S6ExperimentRegistry
from scripts.fetch_fyers_history import generate_synthetic_history

logger = structlog.get_logger("s6_runner")


def run_s6_track(
    instrument: str,
    track: str,
    df_1m: pl.DataFrame,
    registry: Optional[S6ExperimentRegistry] = None,
) -> Tuple[S6MetricsReport, List[S6Trade], Path]:
    """Runs a single S6 track on 1m raw market data."""
    # 1. Determine variant and timeframe branch
    track_upper = track.upper()
    if "S6A" in track_upper or "A" in track_upper:
        variant = S6Variant.S6_A
    else:
        variant = S6Variant.S6_F

    if "T4" in track_upper:
        tf_branch = S6TimeframeBranch.T4_5M_5M
        exec_tf = "5m"
    else:
        tf_branch = S6TimeframeBranch.T1_5M_1M
        exec_tf = "1m"

    config = create_default_config(variant=variant, timeframe_branch=tf_branch, instrument=instrument)

    # 2. Causal 5m Resampling & Indicator Computation
    df_5m = resample_to_completed_5m(df_1m)
    df_5m = compute_5m_features(df_5m, config)

    # Execution dataset is 1m for T1, 5m for T4
    df_exec = df_1m if exec_tf == "1m" else df_5m

    # 3. Detect Compression Episodes
    event_engine = S6EventEngine(config)
    episodes = event_engine.detect_compression_episodes(df_5m, instrument=instrument)

    # 4. Detect RAW Breakouts (timeframe-aware: 1m for T1, 5m for T4)
    raw_breakouts = event_engine.detect_raw_breakouts(
        df_exec=df_exec,
        df_5m=df_5m,
        episodes=episodes,
        timeframe=exec_tf,
    )

    failures: List[FailureEvent] = []
    candidates: List[EntryCandidate] = []

    # 5. Scan Candidates depending on S6-A vs S6-F
    if variant == S6Variant.S6_A:
        a_scanner = S6AScanner(config)
        candidates = a_scanner.scan_candidates(raw_breakouts, df_exec=df_exec)
    else:
        # Detect failure events from the SAME raw breakouts
        failures = event_engine.detect_failures(df_exec=df_exec, episodes=episodes, raw_breakouts=raw_breakouts)
        f_scanner = S6FScanner(config)
        atr5_lookup = {bo.event_id: bo.atr5 for bo in raw_breakouts}
        candidates = f_scanner.scan_candidates(failures, atr5_lookup=atr5_lookup, df_exec=df_exec, timeframe=exec_tf)

    # 6. Simulate Execution
    simulator = S6ExecutionSimulator(config)
    trades = simulator.simulate_candidates(candidates, df_exec=df_exec)

    # 7. Compute Metrics
    metrics = calculate_s6_metrics(
        trades=trades,
        total_candidates=len(candidates),
        compression_count=len(episodes),
        breakout_count=len(raw_breakouts),
        failure_count=len(failures),
        instrument=instrument,
        track=track,
        variant=variant.value,
    )

    # 8. Record Artifacts in Registry
    reg = registry or S6ExperimentRegistry()
    dataset_hash = hashlib.sha256(f"{len(df_1m)}_{instrument}_{df_1m['timestamp'].min()}_{df_1m['timestamp'].max()}".encode()).hexdigest()[:16]
    trial_id = reg.generate_trial_id(config=config, track=track, dataset_hash=dataset_hash)
    run_dir = reg.record_run_artifacts(
        trial_id=trial_id,
        config=config,
        track=track,
        dataset_hash=dataset_hash,
        episodes=episodes,
        raw_breakouts=raw_breakouts,
        failures=failures,
        candidates=candidates,
        trades=trades,
        metrics=metrics,
    )

    return metrics, trades, run_dir


def main():
    parser = argparse.ArgumentParser(description="DROID S6 Research MVP Runner")
    parser.add_argument("--instrument", type=str, default="NIFTY", choices=["NIFTY", "BANKNIFTY", "SENSEX", "ALL"])
    parser.add_argument("--track", type=str, default="S6A_T1", choices=["S6A_T1", "S6A_T4", "S6F_T1", "S6F_T4", "ALL"])
    parser.add_argument("--mode", type=str, default="smoke", choices=["smoke", "historical"])
    parser.add_argument("--days", type=int, default=30, help="Days of data for synthetic smoke test")
    parser.add_argument("--base-price", type=float, default=25000.0, help="Base price for synthetic dataset")
    args = parser.parse_args()

    instruments = ["NIFTY", "BANKNIFTY", "SENSEX"] if args.instrument == "ALL" else [args.instrument]
    tracks = ["S6A_T1", "S6A_T4", "S6F_T1", "S6F_T4"] if args.track == "ALL" else [args.track]

    print("\n" + "=" * 80)
    print(" DROID S6 RESEARCH MVP — 2x2 CORE TRIAGE BATTERY")
    print(" Spec: S6SPEC_v1.3 | Mode: " + args.mode.upper() + " | Status: RESEARCH ONLY")
    print("=" * 80)

    registry = S6ExperimentRegistry()

    for inst in instruments:
        base_p = 80000.0 if "SENSEX" in inst else (50000.0 if "BANK" in inst else 25000.0)
        
        if args.mode == "smoke":
            print(f"\n[+] Generating {args.days}-day synthetic smoke fixture for {inst}...")
            df_1m = generate_synthetic_history(symbol=inst, days=args.days, base_price=base_p)
        else:
            # Look for clean local parquet in known DROID data locations
            candidate_paths = [
                Path(f"data/datasets/{inst.upper()}_1m.parquet"),
                Path(f"data/clean/{inst.lower()}_1m.parquet"),
                Path(f"data/raw/{inst.lower()}/1m.parquet"),
            ]
            p = next((path for path in candidate_paths if path.exists()), None)
            if p:
                # A parquet is not evidence of a market. Refuse a fixture rather
                # than quietly reporting results computed on a simulator.
                report = assert_real_dataset(p, label=f"{inst} 1m research dataset")
                df_1m = pl.read_parquet(p)
                print(
                    f"    Loaded historical parquet: {p} "
                    f"(source={report.source}, sha256={(report.checksum_sha256 or '')[:12]})"
                )
            else:
                # Historical mode must not fabricate history. Smoke mode exists for
                # synthetic runs, so a missing file here is a data problem to surface,
                # not a reason to compute S6 results on generated candles.
                raise FileNotFoundError(
                    f"No 1m dataset found for {inst} in "
                    f"{[str(candidate) for candidate in candidate_paths]}. Refusing to "
                    "substitute synthetic history in historical mode; use --mode smoke "
                    "for synthetic runs."
                )

        print(f"    Loaded {len(df_1m)} 1-minute bars | Start: {df_1m['timestamp'].min()} | End: {df_1m['timestamp'].max()}")

        for trk in tracks:
            print(f"\n--- Running Track: {trk} on {inst} ---")
            metrics, trades, run_dir = run_s6_track(
                instrument=inst,
                track=trk,
                df_1m=df_1m,
                registry=registry,
            )

            print(f"    Compression Episodes : {metrics.compression_episodes}")
            print(f"    Raw Breakouts        : {metrics.raw_breakouts}")
            print(f"    Failures Monitored   : {metrics.failures}")
            print(f"    Candidates Filtered  : {metrics.total_candidates}")
            print(f"    Trades Executed      : {metrics.total_trades}")
            print(f"    Win Rate             : {metrics.win_rate * 100:.2f}% ({metrics.winning_trades}W / {metrics.losing_trades}L)")
            print(f"    Gross Expectancy     : {metrics.gross_expectancy_R:+.4f} R")
            print(f"    Net Expectancy (R)   : {metrics.net_expectancy_R:+.4f} R")
            print(f"    Profit Factor        : {metrics.profit_factor:.2f}")
            print(f"    Max Drawdown (R)     : {metrics.max_drawdown_R:.2f} R")
            print(f"    Average MFE / MAE    : +{metrics.average_MFE_R:.2f}R / -{metrics.average_MAE_R:.2f}R")
            print(f"    Cost / Slippage Drag : {metrics.cost_drag_R:.4f}R / {metrics.slippage_drag_R:.4f}R")
            print(f"    Artifacts Saved To   : {run_dir}")

    print("\n" + "=" * 80)
    print(" S6 RESEARCH MVP TRIAGE COMPLETED (Factual Observation Only — No Winner Chosen)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
