"""DROID — MACD + Fisher-9 Confluence Strategy Backtester CLI.

Allows rapid point-in-time backtesting across customizable Target ATR, Stop ATR,
and candle lookbacks using real historical NIFTY/BANKNIFTY parquet data.

Usage:
    python research/run_backtest.py
    python research/run_backtest.py --symbol NIFTY --target-atr 0.5 --stop-atr 1.0 --bars 5000
    python research/run_backtest.py --symbol BANKNIFTY --target-atr 1.0 --stop-atr 1.5
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import numpy as np

from research.core.fisher import calculate_fisher_point
from research.core.macd import calculate_macd
from research.core.atr import calculate_atr_series
from research.core.event_detector import ResearchEvent
from research.core.outcome_engine import compute_forward_outcomes


def run_confluence_backtest(
    symbol: str = "NIFTY",
    target_atr: float = 0.5,
    stop_atr: float = 1.0,
    max_bars: int = 5000,
    data_path: Path | None = None,
):
    print("=" * 80)
    print(f"DROID FISHER-9 + MACD CONFLUENCE BACKTEST: {symbol.upper()}")
    print("=" * 80)

    # Resolve data path
    if data_path is None or not data_path.exists():
        candidates = [
            Path(f"backend/data/historical/parquet/{symbol.lower()}/5m/candles_v2.parquet"),
            Path(f"backend/data/historical/parquet/{symbol.lower()}/5m/candles_v1.parquet"),
            Path(f"backend/data/historical/parquet/nifty/5m/candles_v2.parquet"),
        ]
        for c in candidates:
            if c.exists():
                data_path = c
                break

    if not data_path or not data_path.exists():
        print(f"Error: Parquet data file not found. Tried paths: {[str(c) for c in candidates]}")
        sys.exit(1)

    print(f"* Data Source: {data_path}")
    df = pd.read_parquet(data_path)
    if len(df) > max_bars:
        df = df.iloc[-max_bars:].reset_index(drop=True)

    print(f"* Bars Loaded: {len(df):,} bars | Window: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"* Setup Rules: MACD (12,26,9) Trend Alignment + Fisher-9 Extreme Pullback Hook")
    print(f"* Barriers   : Target = +{target_atr} ATR | Stop Loss = -{stop_atr} ATR (Pessimistic intra-bar touch)")

    highs = df["high"].tolist()
    lows = df["low"].tolist()
    closes = df["close"].tolist()

    f_pts = calculate_fisher_point(highs, lows, period=9, price_source="HL2")
    m_pts = calculate_macd(closes, fast_period=12, slow_period=26, signal_period=9)
    atr_pts = calculate_atr_series(highs, lows, closes, period=14)

    df["fisher"] = [p.fisher for p in f_pts]
    df["trigger"] = [p.trigger for p in f_pts]
    df["macd"] = [p.macd_line for p in m_pts]
    df["signal"] = [p.signal_line for p in m_pts]
    df["atr"] = [p.atr if hasattr(p, "atr") else p for p in atr_pts]

    events: list[ResearchEvent] = []
    horizon_bars = 12

    for i in range(26, len(df) - horizon_bars):
        f_prev = df["fisher"].iloc[i - 1]
        f_curr = df["fisher"].iloc[i]
        trig_prev = df["trigger"].iloc[i - 1]
        trig_curr = df["trigger"].iloc[i]
        m_curr = df["macd"].iloc[i]
        s_curr = df["signal"].iloc[i]
        atr = df["atr"].iloc[i]

        if atr is None or np.isnan(atr) or atr <= 0:
            continue

        ts_val = str(df["timestamp"].iloc[i]) if "timestamp" in df.columns else f"Bar {i}"

        # Bullish: Macro Trend Bullish + Fisher Oversold Hook
        if m_curr > s_curr and f_prev < -1.0 and f_prev <= trig_prev and f_curr > trig_curr:
            events.append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=ts_val,
                    direction="BULLISH_REVERSAL",
                    stage="CONFLUENCE",
                    price=float(df["close"].iloc[i]),
                    atr=float(atr),
                    fisher=float(f_curr),
                    trigger=float(trig_curr),
                    macd=float(m_curr),
                    macd_signal=float(s_curr),
                    macd_hist=float(m_curr - s_curr),
                )
            )
        # Bearish: Macro Trend Bearish + Fisher Overbought Hook
        elif m_curr < s_curr and f_prev > 1.0 and f_prev >= trig_prev and f_curr < trig_curr:
            events.append(
                ResearchEvent(
                    bar_index=i,
                    timestamp=ts_val,
                    direction="BEARISH_REVERSAL",
                    stage="CONFLUENCE",
                    price=float(df["close"].iloc[i]),
                    atr=float(atr),
                    fisher=float(f_curr),
                    trigger=float(trig_curr),
                    macd=float(m_curr),
                    macd_signal=float(s_curr),
                    macd_hist=float(m_curr - s_curr),
                )
            )

    outcomes = compute_forward_outcomes(
        df,
        events,
        horizon_bars=horizon_bars,
        target_atr_multiple=target_atr,
        stop_atr_multiple=stop_atr,
    )

    wins = sum(1 for o in outcomes if o.success)
    losses = len(outcomes) - wins
    win_rate = (wins / len(outcomes) * 100) if outcomes else 0.0

    gross_profit = wins * target_atr
    gross_loss = losses * stop_atr
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if wins > 0 else 0.0)
    net_atr_gain = gross_profit - gross_loss
    ev_per_trade = (net_atr_gain / len(outcomes)) if outcomes else 0.0

    print("\n" + "-" * 80)
    print("BACKTEST PERFORMANCE SUMMARY")
    print("-" * 80)
    print(f"Total Signals Detected : {len(events)}")
    print(f"Total Completed Trades : {len(outcomes)}")
    print(f"Winning Trades         : {wins}")
    print(f"Losing Trades          : {losses}")
    print(f"Win Rate               : {win_rate:.1f}%")
    print(f"Profit Factor          : {profit_factor:.2f}")
    print(f"Gross Gain             : +{gross_profit:.2f} ATR")
    print(f"Gross Loss             : -{gross_loss:.2f} ATR")
    print(f"Net Gain               : {net_atr_gain:+.2f} ATR")
    print(f"Expected Value (EV)    : {ev_per_trade:+.3f} ATR / trade")
    print("-" * 80)

    # Show recent trades
    print("\nRECENT 10 SAMPLE TRADES:")
    headers = ["Timestamp", "Direction", "Entry", "ATR", "Target", "Stop", "Result", "PnL (Pts)"]
    row_fmt = "{:<20} {:<12} {:<9} {:<7} {:<9} {:<9} {:<8} {:<10}"
    print(row_fmt.format(*headers))
    print("-" * 88)

    for o in outcomes[-10:]:
        ev = o.event
        direction_label = "CALL" if ev.direction == "BULLISH_REVERSAL" else "PUT"
        t_delta = target_atr * ev.atr
        s_delta = stop_atr * ev.atr
        target_p = ev.price + t_delta if direction_label == "CALL" else ev.price - t_delta
        stop_p = ev.price - s_delta if direction_label == "CALL" else ev.price + s_delta
        outcome_label = "WIN" if o.success else "LOSS"
        pnl_pts = (target_atr if o.success else -stop_atr) * ev.atr

        print(row_fmt.format(
            str(ev.timestamp)[:19],
            direction_label,
            f"{ev.price:.1f}",
            f"{ev.atr:.1f}",
            f"{target_p:.1f}",
            f"{stop_p:.1f}",
            outcome_label,
            f"{pnl_pts:+.1f}",
        ))
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="DROID MACD + Fisher-9 Confluence Backtester")
    parser.add_argument("--symbol", type=str, default="NIFTY", help="Symbol to test (NIFTY, BANKNIFTY)")
    parser.add_argument("--target-atr", type=float, default=0.5, help="Target multiplier in ATR units (e.g. 0.5, 1.0, 1.5)")
    parser.add_argument("--stop-atr", type=float, default=1.0, help="Stop loss multiplier in ATR units (e.g. 1.0, 1.5)")
    parser.add_argument("--bars", type=int, default=5000, help="Number of 5-minute candles to evaluate")
    args = parser.parse_args()

    run_confluence_backtest(
        symbol=args.symbol,
        target_atr=args.target_atr,
        stop_atr=args.stop_atr,
        max_bars=args.bars,
    )


if __name__ == "__main__":
    main()
