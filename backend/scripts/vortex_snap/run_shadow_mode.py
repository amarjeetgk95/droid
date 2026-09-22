"""
Live Shadow Mode Runner for VORTEX-SNAP (§45–§47).

Runs the strategy in shadow paper mode:
- Simulates live candle arrival bar-by-bar
- Evaluates full microstructure pipeline (Compression, Pressure, Translation Ratio)
- Drives 16-state FSM transitions
- Enforces ML validator veto checks and probability calibration
- Logs all state changes, candidate signals, and telemetry to console and disk
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.signals.strategies.vortex_snap.config import VortexSnapConfig
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader
from app.signals.strategies.base import StrategyContext


def run_shadow_mode(symbol: str = "SENSEX", max_bars: int = 150):
    print("=" * 75)
    print(f"  VORTEX-SNAP LIVE SHADOW MODE RUNNER (§45-§47)")
    print(f"  Instrument: {symbol} | Mode: SHADOW PAPER EXECUTION")
    print("=" * 75)

    config = VortexSnapConfig()
    strategy = VortexSnapStrategy(config)
    session_model = MarketSessionModel(config.session)
    data_loader = HistoricalDataLoader()

    # Load candles
    try:
        candles = data_loader.load_parquet(instrument=symbol, timeframe="1m")
        if len(candles) > max_bars:
            candles = candles[-max_bars:]
        print(f"Loaded {len(candles)} historical bars for {symbol}.")
    except Exception as e:
        print(f"Parquet load failed ({e}), generating synthetic intraday session...")
        candles = HistoricalDataLoader.generate_synthetic_session(
            date_obj=datetime.now(timezone.utc),
            start_price=80000.0 if "SENSEX" in symbol else 24000.0,
            add_compression_and_breakout=True,
            seed=42,
        )[:max_bars]

    print("\nStarting bar-by-bar shadow simulation...")
    print("-" * 75)
    print(f"{'Time (UTC)':<12} | {'Close':<9} | {'Comp Zone':<10} | {'Pressure':<9} | {'Trans Ratio':<11} | {'FSM State':<12}")
    print("-" * 75)

    signals_emitted = 0
    ml_vetoes = 0

    # Warmup buffer of 35 bars
    for i in range(35, len(candles)):
        current_candle = candles[i]
        history_window = candles[: i + 1]

        # Convert to dict candles
        dict_candles = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in history_window
        ]

        ctx = StrategyContext(
            underlying=symbol,
            spot_price=Decimal(str(round(current_candle.close, 2))),
            timestamp_ms=current_candle.timestamp,
            candles=dict_candles,
            daily_loss_limit_breached=False,
            portfolio_positions=[],
        )

        candidate = strategy.detect(ctx)
        
        # Get live snapshot from feature engine
        snapshot = strategy.feature_engine.compute_snapshot(
            instrument=symbol,
            candles_1m=history_window,
            timestamp_ms=current_candle.timestamp,
            spot_price=current_candle.close,
        )

        comp_zone = snapshot.compression.zone.value
        pressure_str = f"{snapshot.pressure.pressure_score:+.2f}"
        trans_str = f"{snapshot.translation.translation_ratio:.2f}x"
        fsm_state = strategy.fsm.state.value if hasattr(strategy.fsm.state, "value") else str(strategy.fsm.state)
        time_str = datetime.fromtimestamp(current_candle.timestamp / 1000, tz=timezone.utc).strftime("%H:%M:%S")

        # Print periodic or eventful rows
        is_event = candidate is not None or comp_zone in ("ARMED", "EXTREME") or fsm_state != "IDLE"
        if is_event or i % 15 == 0 or i == len(candles) - 1:
            print(f"{time_str:<12} | {current_candle.close:<9.1f} | {comp_zone:<10} | {pressure_str:<9} | {trans_str:<11} | {fsm_state:<12}")

        if candidate:
            signals_emitted += 1
            print(f"  >>> [SIGNAL DETECTED] {candidate.direction} @ INR {float(candidate.trigger):.1f} | SL: INR {float(candidate.stop_loss):.1f} | T1: INR {float(candidate.target_1):.1f} | Conf: {float(candidate.overall_confidence):.2f}")
            print(f"      Rationale: {candidate.rationale}")

    print("-" * 75)
    print("\nShadow Mode Execution Summary:")
    print(f"  Total Bars Evaluated  : {len(candles) - 35}")
    print(f"  Signals Emitted       : {signals_emitted}")
    print(f"  FSM Final State       : {strategy.fsm.state.value}")
    print(f"  ML Validator Active   : {strategy.ml_validator._is_loaded}")
    print("=" * 75)


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SENSEX"
    run_shadow_mode(symbol)
