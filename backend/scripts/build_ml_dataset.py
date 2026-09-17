"""Candidate Replay Engine & ML Dataset Builder.

Implements Section 6, Section 7, and Section 13 of the DROID ML Specification.
Replays DROID strategy detection over historical/reconstructed candle data,
extracts Point-in-Time Feature V3 snapshots at the signal bar, computes
triple-barrier labels (T1 vs SL vs Timeout) and MFE/MAE, and exports to Parquet.
"""
from __future__ import annotations

import argparse
import json
import os
import math
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from app.ml.features.feature_extractor_v3 import extract_features_v3
from app.ml.features.schema import FEATURE_NAMES_V3, FEATURE_SCHEMA_V3
from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.strategies.trend_pullback import TrendPullbackStrategy

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ml_datasets")
os.makedirs(DATA_DIR, exist_ok=True)


def simulate_synthetic_market_session(
    start_price: float = 25000.0,
    n_candles: int = 375,
    drift: float = 0.0001,
    volatility: float = 0.0012,
    base_ts_ms: int = 1710000000000,
) -> List[Dict[str, Any]]:
    """
    Generates a realistic 1-minute candle series for testing and baseline dataset construction.
    Tagged with DATA_FIDELITY = SYNTHETIC.
    """
    candles = []
    curr = start_price
    ts = base_ts_ms

    import random
    rng = random.Random(42)

    for i in range(n_candles):
        shock = rng.gauss(drift, volatility)
        op = curr
        cl = op * (1.0 + shock)
        intra_hi = max(op, cl) * (1.0 + abs(rng.gauss(0, volatility * 0.5)))
        intra_lo = min(op, cl) * (1.0 - abs(rng.gauss(0, volatility * 0.5)))
        vol = int(rng.uniform(1000, 25000))

        candles.append({
            "timestamp_ms": ts,
            "open": round(op, 2),
            "high": round(intra_hi, 2),
            "low": round(intra_lo, 2),
            "close": round(cl, 2),
            "volume": vol,
        })
        curr = cl
        ts += 60000  # 1 minute

    return candles


def evaluate_triple_barrier(
    entry_price: float,
    target_1: float,
    stop_loss: float,
    direction: str,
    future_candles: List[Dict[str, Any]],
    timeout_bars: int = 45,
) -> Tuple[int, float, float, int]:
    """
    Evaluates path-dependent outcome over subsequent bars:
        Returns: (label, mfe_r, mae_r, bars_to_exit)
        label: 2 = TARGET_FIRST, 0 = STOP_FIRST, 1 = TIMEOUT
    """
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        risk = entry_price * 0.002

    max_fav = 0.0
    max_adv = 0.0
    is_call = "CALL" in direction

    for bar_idx, bar in enumerate(future_candles[:timeout_bars]):
        high = float(bar["high"])
        low = float(bar["low"])

        if is_call:
            fav = max(0.0, high - entry_price)
            adv = max(0.0, entry_price - low)
            max_fav = max(max_fav, fav)
            max_adv = max(max_adv, adv)

            # Check stop loss hit first
            if low <= stop_loss:
                return 0, max_fav / risk, max_adv / risk, bar_idx + 1
            # Check target hit
            if high >= target_1:
                return 2, max_fav / risk, max_adv / risk, bar_idx + 1
        else:
            fav = max(0.0, entry_price - low)
            adv = max(0.0, high - entry_price)
            max_fav = max(max_fav, fav)
            max_adv = max(max_adv, adv)

            if high >= stop_loss:
                return 0, max_fav / risk, max_adv / risk, bar_idx + 1
            if low <= target_1:
                return 2, max_fav / risk, max_adv / risk, bar_idx + 1

    return 1, max_fav / risk, max_adv / risk, len(future_candles[:timeout_bars])


def build_dataset_from_candles(
    instrument: str,
    candles: List[Dict[str, Any]],
    data_fidelity: str = "SYNTHETIC",
) -> pd.DataFrame:
    """
    Replays strategy candidate generation across candles and extracts
    Feature V3 rows + Triple Barrier outcomes.
    """
    strategy = TrendPullbackStrategy()
    records = []

    # Need at least 50 bars of history to compute moving averages and indicators
    for i in range(50, len(candles) - 45):
        hist = candles[:i]
        curr = candles[i]
        future = candles[i + 1:]

        ts = curr["timestamp_ms"]
        close_p = Decimal(str(curr["close"]))

        # Build rolling EMAs
        closes = [float(c["close"]) for c in hist]
        ema20 = sum(closes[-20:]) / 20.0
        ema50 = sum(closes[-50:]) / 50.0

        ctx = StrategyContext(
            underlying=instrument,  # type: ignore
            spot_price=close_p,
            timeframe="5M",
            indicators={
                "trend": {
                    "ema20": ema20,
                    "ema50": ema50,
                    "ema200": ema50 * 0.99,
                    "adx": 26.0,
                },
                "vwap": ema50 * 0.995,
                "supertrend_direction": "BULLISH" if ema20 > ema50 else "BEARISH",
            },
            regime="TREND_UP" if ema20 > ema50 else "TREND_DOWN",
        )

        cand = strategy.detect(ctx)
        if cand:
            # We have a candidate! Extract point-in-time Feature Vector V3
            f_vec = extract_features_v3(
                instrument=instrument,
                feature_timestamp_ms=ts,
                candles_1m=hist + [curr],
                indicators={
                    "vwap": float(ctx.indicators.get("vwap", 0)),
                    "ema20": ema20,
                    "ema50": ema50,
                    "ema200": ema50 * 0.99,
                    "adx_14": 26.0,
                    "supertrend_direction": ctx.indicators.get("supertrend_direction", "NEUTRAL"),
                },
            )

            # Evaluate Triple-Barrier outcome
            label, mfe_r, mae_r, bars = evaluate_triple_barrier(
                entry_price=float(cand.spot_price),
                target_1=float(cand.target_1),
                stop_loss=float(cand.stop_loss),
                direction=cand.direction,
                future_candles=future,
            )

            # Target direction label for H=15m
            future_close_15m = float(future[min(14, len(future) - 1)]["close"])
            dir_ret = (future_close_15m - float(cand.spot_price)) / float(cand.spot_price)
            dir_label = 2 if dir_ret > 0.0015 else (0 if dir_ret < -0.0015 else 1)

            rec = {
                "candidate_id": str(uuid.uuid4()),
                "instrument": instrument,
                "strategy": cand.strategy,
                "direction": cand.direction,
                "timestamp_ms": ts,
                "data_fidelity": data_fidelity,
                "spot_price": float(cand.spot_price),
                "trigger": float(cand.trigger),
                "stop_loss": float(cand.stop_loss),
                "target_1": float(cand.target_1),
                "label_triple_barrier": label,  # 0=SL, 1=Timeout, 2=T1
                "label_direction_15m": dir_label,  # 0=Bearish, 1=Neutral, 2=Bullish
                "mfe_r": round(mfe_r, 3),
                "mae_r": round(mae_r, 3),
                "bars_to_exit": bars,
            }
            # Append all 28 features
            for feat_name, feat_val in f_vec.feature_dict.items():
                rec[f"f_{feat_name}"] = feat_val

            records.append(rec)

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description="Build DROID ML candidate replay dataset")
    parser.add_argument("--instrument", default="NIFTY", help="Underlying instrument symbol")
    parser.add_argument("--days", type=int, default=10, help="Number of simulated trading days")
    parser.add_argument("--output", default=os.path.join(DATA_DIR, "candidates_v3.parquet"), help="Output parquet path")
    args = parser.parse_args()

    print(f"Generating candidate replay dataset for {args.instrument} ({args.days} sessions)...")
    all_dfs = []
    base_ts = 1710000000000

    for day in range(args.days):
        day_candles = simulate_synthetic_market_session(
            start_price=24800.0 + (day * 30.0),
            n_candles=375,
            drift=0.00005 if day % 2 == 0 else -0.00005,
            volatility=0.0010 + (day % 3) * 0.0002,
            base_ts_ms=base_ts + (day * 86400000),
        )
        df_day = build_dataset_from_candles(args.instrument, day_candles, data_fidelity="SYNTHETIC")
        if not df_day.empty:
            all_dfs.append(df_day)

    if not all_dfs:
        print("No candidates detected across sessions.")
        return

    full_df = pd.concat(all_dfs, ignore_index=True)
    table = pa.Table.from_pandas(full_df)
    pq.write_table(table, args.output)
    print(f"Dataset successfully created: {args.output}")
    print(f"Total candidate rows: {len(full_df)}")
    print(f"Triple-barrier label distribution:\n{full_df['label_triple_barrier'].value_counts(normalize=True)}")


if __name__ == "__main__":
    main()
