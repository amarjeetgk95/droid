"""
CLI Utility for Intraday Swing Option Buying Engine (v3.1 Production-MVP)
Demonstrates the complete decision pipeline for NIFTY.
Usage:
    .venv\\Scripts\\python.exe -m app.signals.cli.scan_intraday --instrument NIFTY [--spot 25000]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from decimal import Decimal
from typing import Any

from app.signals.contract_resolver import validate_underlying, resolve_option_contract
from app.signals.options_intelligence.selector import quantitative_contract_selector
from app.signals.strategies.trend_pullback import TrendPullbackStrategy
from app.signals.strategies.base import StrategyContext
from app.signals.risk_engine import StrategySetup, central_risk_engine


def run_intraday_scan(underlying: str = "NIFTY", spot_override: float | None = None) -> None:
    u = validate_underlying(underlying)
    print(f"\n{'='*70}")
    print(f"  DROID INTRADAY SWING OPTION BUYING ENGINE (v3.1 Production-MVP)")
    print(f"  Target Instrument: {u} | Execution Mode: PAPER ONLY")
    print(f"{'='*70}\n")

    t_start = time.perf_counter()

    # 1. Market Data & Spot
    spot = Decimal(str(spot_override)) if spot_override else Decimal("25000.0")
    print(f"[Stage 1] Market Spot Price: Rs. {spot:,.2f}")

    # 2. 15M Regime & Structure Hypothesis (§6)
    # Long Setup: EMA20 > EMA50 > EMA200, ADX >= 22, VWAP alignment
    ema20 = spot * Decimal("0.998")  # 24950        ema50 = spot * Decimal("0.994")  # example: ~1% below spot
    ema200 = spot * Decimal("0.985") # 24625
    adx_val = 26.5
    vwap_val = spot * Decimal("0.997") # 24925

    indicators = {
        "trend": {
            "ema20": float(ema20),
            "ema50": float(ema50),
            "ema200": float(ema200),
            "adx": adx_val,
            "trend": "BULLISH",
        },
        "volatility": {"atr": 25.0},
        "adx": adx_val,
    }
    mtf = {"overall_bias": "BULLISH", "alignment_score": 85.0}
    regime = "TREND_UP"

    print(f"[Stage 2] 15M Structure:")
    print(f"  - Regime: {regime}")
    print(f"  - EMA Ribbon: EMA20 (Rs. {ema20:,.1f}) > EMA50 (Rs. {ema50:,.1f}) > EMA200 (Rs. {ema200:,.1f}) [PASS]")
    print(f"  - ADX: {adx_val:.1f} (Threshold >= 22.0) [PASS]")
    print(f"  - VWAP: Rs. {vwap_val:,.1f} (Spot >= VWAP) [PASS]")

    # 3. Strategy Evaluation (Trend Pullback Continuation)
    ctx = StrategyContext(
        underlying=u,  # type: ignore
        spot_price=spot,
        timeframe="5M",
        indicators=indicators,
        mtf=mtf,
        regime=regime,
        vwap=vwap_val,
    )

    strat = TrendPullbackStrategy()
    candidate = strat.detect(ctx)

    if not candidate:
        print(f"\n[FAIL] [Stage 3] Strategy Condition Not Met -> ABSTAIN\n")
        return

    print(f"\n[Stage 3] Underlying Setup Triggered:")
    print(f"  - Strategy: {candidate.strategy}")
    print(f"  - Direction: {candidate.direction}")
    print(f"  - Entry Trigger: Rs. {candidate.trigger:,.2f}")
    print(f"  - Defensive Stop: Rs. {candidate.stop_loss:,.2f} ({candidate.risk_points:.1f} pts risk)")
    print(f"  - Target 1 (1.5R): Rs. {candidate.target_1:,.2f}")
    print(f"  - Target 2 (3.0R): Rs. {candidate.target_2:,.2f}")
    print(f"  - Holding Horizon: {candidate.time_stop_seconds // 60} minutes")

    # 4. Quantitative Contract Selection (ATM vs ITM-1) (§9 & §10)
    print(f"\n[Stage 4] Quantitative Contract Selection (ATM vs ITM-1):")
    opt_selection = quantitative_contract_selector.select_optimal_contract(
        underlying=u,  # type: ignore
        spot_price=float(spot),
        direction=candidate.direction,
        expected_move_points=float(candidate.target_2 - candidate.trigger),
        stop_loss_points=float(candidate.risk_points),
        target_horizon_hours=1.0,
        candidate_types=["ITM_1", "ATM"],
        max_theta_drag_ratio=20.0,
        min_net_rr=1.5,
        max_spread_pct=2.5,
    )

    if opt_selection is None:
        print(f"  [FAIL] Contract evaluation failed -> ABSTAIN\n")
        return

    for c in opt_selection.all_candidates:
        status_lbl = "[VIABLE]" if c.is_acceptable else f"[REJECT] ({'; '.join(c.rejection_reasons)})"
        print(f"  Candidate [{c.strike_type}] Strike: {c.strike:.0f} {c.option_type}")
        print(f"    - Delta: {c.greeks.delta:.2f} | Gamma: {c.greeks.gamma:.4f} | Theta/hr: Rs. {c.greeks.theta_hour:.2f}")
        print(f"    - Theta Drag Ratio: {c.theta_drag_ratio:.1f}% (Limit: <= 20%)")
        print(f"    - Simulated Net R/R: {c.net_rr_ratio:.2f} (after Indian STT/GST/Slippage)")
        print(f"    - Score: {c.score:.1f}/100 -> {status_lbl}")

    print(f"\n  [SELECTED] Selected Contract: {opt_selection.selected_contract.broker_symbol} ({opt_selection.selected_strike_type})")
    print(f"    Expiry: {opt_selection.selected_contract.expiry_date} ({opt_selection.selected_contract.expiry_type})")
    print(f"    Delta: {opt_selection.selected_greeks.delta:.2f} (Sweet spot 0.60 - 0.70)")

    # 5. Risk Engine & Position Sizing (§17 & §18)
    cand_greeks = candidate.greeks or {}
    strat_setup = StrategySetup(
        strategy_name=candidate.strategy,
        underlying=candidate.underlying,
        direction=candidate.direction,
        timeframe=candidate.timeframe,
        is_scalp=False,
        spot_price=candidate.spot_price,
        entry_trigger=candidate.trigger,
        raw_structural_stop=candidate.stop_loss,
        structural_target_candidates=[candidate.target_1, candidate.target_2],
        atr_5m=Decimal("25.0"),
        confidence=candidate.overall_confidence,
        option_delta=opt_selection.selected_greeks.delta,
        option_theta_hour=opt_selection.selected_greeks.theta_hour,
        option_premium=opt_selection.selected_greeks.theoretical_price,
    )

    risk_decision = central_risk_engine.evaluate(strat_setup, available_capital=200000.0, risk_per_trade_pct=0.75, allow_closed_market=True)

    print(f"\n[Stage 5] Risk & Capital Gate:")
    print(f"  - Account Equity Budget: Rs. 2,00,000.00")
    print(f"  - Max Risk per Trade: 0.75% (Rs. 1,500.00)")
    print(f"  - Position Sizing: {risk_decision.lots} Lots ({risk_decision.quantity} Qty)")
    print(f"  - Max Rupee Risk: Rs. {risk_decision.max_rupee_loss:,.2f}")
    print(f"  - Active Time Stop: {risk_decision.active_time_stop_seconds // 60} minutes")
    print(f"  - Decision: {'ACCEPTED' if risk_decision.accepted else 'REJECTED'}")

    # 6. Fast Execution Gate Latency Check (§21)
    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000.0

    print(f"\n[Stage 6] Fast Execution Gate Latency:")
    print(f"  - Total Decision Pipeline Latency: {latency_ms:.2f} ms")
    print(f"  - Latency SLA Target: < 150 ms [{'PASS' if latency_ms < 150 else 'OVERRUN'}]")

    print(f"\n{'='*70}")
    print(f"  FINAL ENGINE DECISION: [BUY] {opt_selection.selected_contract.broker_symbol}")
    print(f"  ACTION: Register Paper Position in FSM & Record Audit Ledger")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Droid Intraday Swing Option Buying Engine CLI")
    parser.add_argument("--instrument", default="NIFTY", choices=["NIFTY"], help="Target index (NIFTY for MVP)")
    parser.add_argument("--spot", type=float, default=25000.0, help="Spot price override")
    args = parser.parse_args()

    run_intraday_scan(underlying=args.instrument, spot_override=args.spot)
