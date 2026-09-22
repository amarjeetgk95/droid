"""Quantitative Research & Validation Engine API Endpoints (Tier 4).

Exposes:
- Dataset inspection (local Parquet datasets, quality scores, row counts)
- Gate G0: Baseline Strategy Falsification backtesting
- Gate G1: Purged Walk-Forward ML Ablation study & diversity telemetry
- Tier 2: 8D PCA Historical Analogue regime query
- Tier 3: Synthetic Options Execution simulation & statutory cost analysis
"""

from __future__ import annotations

import json
from pathlib import Path
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Literal
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import structlog

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.quant.data.dataset_manager import DatasetManager
from app.quant.backtest.backtest_harness import BacktestHarness
from app.quant.validation.gate_g1_evaluator import GateG1Evaluator
from app.quant.validation.gate_g2_evaluator import GateG2Evaluator
from app.quant.historical.historical_analogue import HistoricalAnalogueEngine
from app.quant.backtest.options_simulator import OptionsExecutionSimulator, simulate_vertical_spread
from app.quant.features.feature_engine import CausalFeatureEngine
from app.quant.research.s6_runner import run_s6_track
from app.quant.research.s6_registry import S6ExperimentRegistry
from app.quant.research.export import matrix_to_csv, trades_to_csv

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/quant", tags=["Quantitative Engine"])
_PROVIDER = "droid_quant_engine"


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------
class S6RunRequest(BaseModel):
    instrument: str = Field(default="SENSEX", description="Instrument: SENSEX or NIFTY")
    track: str = Field(default="ALL", description="S6A_T1, S6A_T4, S6F_T1, S6F_T4, or ALL")
    mode: str = Field(default="historical", description="historical or smoke")


class G0RunRequest(BaseModel):
    symbol: str = Field(default="sensex", description="Underlying asset symbol")
    timeframe: str = Field(default="15m", description="Bar resolution: 1m, 5m, 15m")
    strategy_key: str = Field(default="ALL", description="S1, S2, S3, S4, S5, S7, S8, S4+S8, ALL, or R")
    trend_aligned: bool = Field(default=True, description="Enable regime and trend pre-gating")
    k_tp: float = Field(default=2.0, description="Take profit multiplier")
    k_sl: float = Field(default=1.0, description="Stop loss multiplier")
    t_max_bars: int = Field(default=12, description="Max holding bars")
    stress_multiplier: float = Field(default=1.0, description="Cost stress multiplier (1.0x to 2.0x)")


class G1RunRequest(BaseModel):
    symbol: str = Field(default="sensex", description="Underlying asset symbol")
    timeframe: str = Field(default="15m", description="Bar resolution: 1m, 5m, 15m")
    strategy_key: str = Field(default="ALL", description="S1, S2, S3, S4, or ALL")
    n_folds: int = Field(default=5, description="Purged WFO fold count")
    confidence_threshold: float = Field(default=0.38, description="Ensemble qualification probability threshold")
    max_disagreement: float = Field(default=0.30, description="Max allowed model disagreement")
    k_tp: float = Field(default=2.0, description="Take profit multiplier")
    k_sl: float = Field(default=1.0, description="Stop loss multiplier")


class G2RunRequest(BaseModel):
    symbol: str = Field(default="sensex", description="Underlying asset symbol")
    timeframe: str = Field(default="15m", description="Bar resolution: 1m, 5m, 15m")
    strategy_key: str = Field(default="ALL", description="S1, S2, S3, S4, S5, S7, S8, S4+S8, or ALL")
    k_tp: float = Field(default=2.0, description="Take profit multiplier")
    k_sl: float = Field(default=1.0, description="Stop loss multiplier")
    t_max_bars: int = Field(default=12, description="Max holding bars")
    trend_aligned: bool = Field(default=True, description="Enable regime and trend pre-gating")
    session_filter: bool = Field(default=False, description="Enable institutional session liquidity window filter")


class AnalogueQueryRequest(BaseModel):
    symbol: str = Field(default="sensex", description="Underlying asset symbol")
    timeframe: str = Field(default="15m", description="Bar resolution: 1m, 5m, 15m")
    bar_index: int = Field(default=-1, description="Bar index to query analogues for (-1 for latest)")
    direction: int = Field(default=1, description="Query direction (+1 long, -1 short)")
    k_neighbors: int = Field(default=10, description="Number of nearest historical regimes to retrieve")


class OptionsSimulateRequest(BaseModel):
    symbol: str = Field(default="SENSEX", description="Underlying asset symbol")
    direction: int = Field(default=1, description="+1 Long Call (CE), -1 Long Put (PE)")
    spot_entry: float = Field(default=80000.0, description="Underlying spot at entry")
    spot_exit: float = Field(default=80300.0, description="Underlying spot at exit")
    bars_held: int = Field(default=4, description="Holding duration in bars")
    days_to_expiry: float = Field(default=3.0, description="Days to weekly contract expiry")
    custom_iv: Optional[float] = Field(default=0.14, description="Implied Volatility (e.g. 0.14)")
    stress_multiplier: float = Field(default=1.0, description="Cost stress multiplier")


class OptionsSpreadSimulationRequest(BaseModel):
    symbol: str = Field(default="SENSEX", description="Underlying asset symbol (e.g. SENSEX, NIFTY)")
    direction: str = Field(default="LONG", description="Spread direction: 'LONG' (Bull Call) or 'SHORT' (Bear Put)")
    spot_entry: float = Field(default=80000.0, description="Underlying spot at entry")
    spot_exit: float = Field(default=80300.0, description="Underlying spot at exit")
    holding_bars: int = Field(default=4, description="Holding duration in bars")
    bar_minutes: int = Field(default=15, description="Bar duration in minutes (e.g. 5, 15)")
    iv: float = Field(default=0.14, description="Implied Volatility (e.g. 0.14 for 14%)")
    dte_entry: float = Field(default=4.0, description="Days to weekly contract expiry at entry")
    strike_width: float = Field(default=300.0, description="Strike width between legs (pts)")
    lot_size: int = Field(default=10, description="Contract lot size (10 for SENSEX, 25 for NIFTY)")
    contracts: int = Field(default=1, description="Number of contracts")
    stress_multiplier: float = Field(default=1.0, description="Cost stress multiplier (1.0x to 2.0x)")



class StrategyMatrixRequest(BaseModel):
    symbol: str = Field(default="sensex", description="Underlying asset symbol")
    timeframe: str = Field(default="15m", description="Bar resolution: 1m, 5m, 15m")
    k_tp: float = Field(default=2.5, description="Take profit multiplier")
    k_sl: float = Field(default=1.0, description="Stop loss multiplier")
    t_max_bars: int = Field(default=12, description="Max holding bars")
    trend_aligned: bool = Field(default=True, description="Enable regime and trend pre-gating")
    session_filter: bool = Field(default=False, description="Enable institutional session liquidity window filter (09:20-10:30 & 14:15-15:15 IST)")
    stress_multiplier: float = Field(default=1.0, description="Cost stress multiplier")


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@router.get("/datasets")
async def list_datasets():
    """Lists locally available Parquet datasets with provenance and quality metadata."""
    dm = DatasetManager()
    datasets = []
    
    for symbol in ["sensex", "nifty"]:
        for tf in ["1m", "5m", "15m"]:
            if dm.exists(symbol, tf):
                try:
                    df, meta = dm.load_dataset(symbol, tf)
                    datasets.append({
                        "symbol": symbol.upper(),
                        "timeframe": tf,
                        "row_count": len(df),
                        "start_time": meta.start_time if meta else None,
                        "end_time": meta.end_time if meta else None,
                        "data_quality_score": meta.data_quality_score if meta else 100.0,
                        "checksum_sha256": meta.checksum_sha256[:12] if meta else None,
                    })
                except Exception as e:
                    logger.warning("dataset_read_error", symbol=symbol, tf=tf, error=str(e))
                    
    return envelope(datasets, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/g0-baseline")
async def run_g0_baseline(req: G0RunRequest):
    """Executes headless Gate G0 baseline falsification backtest."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, _ = dm.load_dataset(req.symbol, "1m")
        if req.timeframe != "1m":
            df = dm.resample_candles(df_raw, target_timeframe=req.timeframe)
        else:
            df = df_raw

        strat_upper = req.strategy_key.upper().replace("-", "_")
        if "S6" in strat_upper:
            track = "S6F_T1" if "F" in strat_upper else "S6A_T1"
            s6_metrics, s6_trades, _ = run_s6_track(
                instrument=req.symbol.upper(),
                track=track,
                df_1m=df_raw,
            )
            g0_v = "INCONCLUSIVE" if s6_metrics.total_trades < 25 else ("PASSED" if s6_metrics.net_expectancy_R > 0 and s6_metrics.profit_factor >= 1.10 else "FAILED")
            reasons = [
                f"Sample size: {s6_metrics.total_trades} trades (need >= 25 for statistical validity). S6 status: EXPERIMENTAL."
            ]
            if s6_metrics.total_trades >= 25 and s6_metrics.net_expectancy_R <= 0:
                reasons.append(f"Negative net expectancy: {s6_metrics.net_expectancy_R:.3f}R")
            return {
                "metrics": {
                    "total_candidates": s6_metrics.total_candidates,
                    "total_trades": s6_metrics.total_trades,
                    "winning_trades": s6_metrics.winning_trades,
                    "losing_trades": s6_metrics.losing_trades,
                    "win_rate": round(s6_metrics.win_rate, 4),
                    "profit_factor": round(s6_metrics.profit_factor, 2),
                    "net_expectancy_pct": round(s6_metrics.net_expectancy_R * 0.005, 4),
                    "gross_expectancy_pct": round(s6_metrics.gross_expectancy_R * 0.005, 4),
                    "cost_drag_pct": round(s6_metrics.cost_drag_R * 0.005, 4),
                    "max_drawdown_pct": round(s6_metrics.max_drawdown_R * 0.005, 4),
                    "annualized_sharpe": 0.0,
                    "deflated_sharpe_ratio": 0.0,
                    "cost_survival_max_multiplier": req.stress_multiplier,
                    "gate_g0_verdict": g0_v,
                    "verdict_reasons": reasons,
                },
                "sample_trades": [
                    {
                        "entry_time": t.entry_time.isoformat(),
                        "exit_time": t.exit_time.isoformat(),
                        "strategy_id": f"{t.variant}_{t.track}",
                        "direction": t.direction,
                        "gross_pnl_pct": round(t.gross_R * 0.005, 4),
                        "net_pnl_pct": round(t.net_R * 0.005, 4),
                        "total_cost_pct": round(t.cost_drag_R * 0.005, 4),
                        "exit_reason": t.exit_reason,
                        "bars_held": t.bars_held,
                    }
                    for t in s6_trades[:50]
                ],
            }

        harness = BacktestHarness(
            t_max_bars=req.t_max_bars,
            k_tp=req.k_tp,
            k_sl=req.k_sl,
            trend_aligned=req.trend_aligned,
        )
        trades, metrics = harness.run_backtest(
            df=df,
            strategy_key=req.strategy_key,
            stress_multiplier=req.stress_multiplier,
        )
        return {
            "metrics": metrics.to_dict(),
            "sample_trades": [
                {
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "strategy_id": t.strategy_id,
                    "direction": t.direction,
                    "gross_pnl_pct": round(t.gross_pnl_pct, 4),
                    "net_pnl_pct": round(t.net_pnl_pct, 4),
                    "total_cost_pct": round(t.total_cost_pct, 4),
                    "exit_reason": t.exit_reason,
                    "bars_held": t.bars_held,
                }
                for t in trades[:50]
            ],
        }

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("g0_baseline_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Gate G0 execution failed: {str(e)}")


@router.post("/g1-ablation")
async def run_g1_ablation(req: G1RunRequest):
    """Executes Purged Walk-Forward ML Ablation across 5 arms (Gate G1)."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, _ = dm.load_dataset(req.symbol, "1m")
        if req.timeframe != "1m":
            df = dm.resample_candles(df_raw, target_timeframe=req.timeframe)
        else:
            df = df_raw

        evaluator = GateG1Evaluator(
            n_folds=req.n_folds,
            confidence_threshold=req.confidence_threshold,
            max_disagreement=req.max_disagreement,
            k_tp=req.k_tp,
            k_sl=req.k_sl,
        )
        report = evaluator.evaluate(df, strategy_key=req.strategy_key, trend_aligned=True)
        return report.to_dict()

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("g1_ablation_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Gate G1 evaluation failed: {str(e)}")


@router.post("/analogues")
async def query_historical_analogues(req: AnalogueQueryRequest):
    """Queries 8D PCA historical analogue engine for time-separated regimes."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, _ = dm.load_dataset(req.symbol, "1m")
        if req.timeframe != "1m":
            df = dm.resample_candles(df_raw, target_timeframe=req.timeframe)
        else:
            df = df_raw

        feat_engine = CausalFeatureEngine()
        df_feat = feat_engine.compute_features(df)

        query_idx = req.bar_index if req.bar_index >= 0 else len(df_feat) - 1
        query_time = df_feat["timestamp"][query_idx]

        engine = HistoricalAnalogueEngine(
            n_components=8,
            k_neighbors=req.k_neighbors,
            exclusion_window_minutes=60,
        )

        # Build quick reference index on prior bars
        from app.quant.strategies.strategies import BaselineStrategyEngine
        from app.quant.labels.label_engine import TripleBarrierLabelEngine
        strat = BaselineStrategyEngine(trend_aligned=True)
        cands = strat.scan_s1_orb(df_feat) + strat.scan_s2_momentum(df_feat)
        cands = [c for c in cands if c.bar_index < query_idx]
        
        if len(cands) < 15:
            return {
                "status": "insufficient_history",
                "message": "Fewer than 15 historical strategy candidates available prior to query timestamp.",
            }

        lbl = TripleBarrierLabelEngine(t_max_bars=10, k_tp=2.0, k_sl=1.0)
        outs = lbl.label_candidates(df_feat, [c.bar_index for c in cands], [c.direction for c in cands])
        net_rets = [o.gross_return - 0.00133 for o in outs]

        engine.build_index(df_feat, cands, outs, net_rets)
        context = engine.find_analogues(
            df_feat=df_feat,
            query_bar_idx=query_idx,
            query_time=query_time,
            query_direction=req.direction,
            k=req.k_neighbors,
        )

        return {
            "query_time": query_time.isoformat(),
            "query_direction": req.direction,
            "analogue_context": context.to_dict(),
            "top_neighbors": [
                {
                    "timestamp": n.timestamp.isoformat(),
                    "distance": n.distance,
                    "similarity": n.similarity,
                    "direction": n.direction,
                    "gross_return": round(n.gross_return, 4),
                    "net_return": round(n.net_return, 4),
                    "exit_reason": n.exit_reason,
                }
                for n in context.top_neighbors
            ],
        }

    result = await asyncio.to_thread(_execute)
    return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/options-simulate")
async def simulate_options_trade(req: OptionsSimulateRequest):
    """Simulates realistic options premium execution, Greeks, Theta decay, and statutory friction."""
    sim = OptionsExecutionSimulator(
        symbol=req.symbol,
        lot_size=10 if "SENSEX" in req.symbol.upper() else 25,
        default_iv=req.custom_iv or 0.14,
    )
    now = datetime.now(timezone.utc)
    res = sim.simulate_trade(
        entry_time=now,
        exit_time=now,
        direction=req.direction,
        spot_entry=req.spot_entry,
        spot_exit=req.spot_exit,
        bars_held=req.bars_held,
        days_to_expiry=req.days_to_expiry,
        custom_iv=req.custom_iv,
        stress_multiplier=req.stress_multiplier,
    )

    return envelope(
        {
            "symbol": req.symbol,
            "strike": res.strike,
            "option_type": res.option_type,
            "spot_entry": res.underlying_entry,
            "spot_exit": res.underlying_exit,
            "premium_entry": res.premium_entry_exec,
            "premium_exit": res.premium_exit_exec,
            "options_gross_pnl_pts": res.options_gross_pnl,
            "options_gross_roi_pct": res.options_gross_roi_pct,
            "total_statutory_cost_rupees": res.total_statutory_cost,
            "net_pnl_rupees": res.net_pnl_rupees,
            "options_net_roi_pct": res.options_net_roi_pct,
            "delta_at_entry": res.delta_at_entry,
            "theta_per_day": res.theta_per_day,
            "bars_held": res.bars_held,
            "forward_entry": res.forward_entry,
            "forward_exit": res.forward_exit,
            "simulation_class": res.simulation_class,
            "pricing_model": res.pricing_model,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.post("/options-spread-simulate")
async def simulate_options_spread(req: OptionsSpreadSimulationRequest):
    """Simulates defined-risk vertical spreads (Bull Call / Bear Put) with statutory multi-leg costs and theta decay reduction."""
    lot_size = req.lot_size
    if "SENSEX" in req.symbol.upper() and req.lot_size == 10:
        lot_size = 10
    elif "NIFTY" in req.symbol.upper() and req.lot_size == 10:
        lot_size = 25

    result = simulate_vertical_spread(
        spot_entry=req.spot_entry,
        spot_exit=req.spot_exit,
        direction=req.direction,
        holding_bars=req.holding_bars,
        bar_minutes=req.bar_minutes,
        iv=req.iv,
        dte_entry=req.dte_entry,
        strike_width=req.strike_width,
        lot_size=lot_size,
        contracts=req.contracts,
        stress_multiplier=req.stress_multiplier,
    )
    result["symbol"] = req.symbol.upper()
    return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/strategy-matrix")
async def run_strategy_matrix(req: StrategyMatrixRequest):
    """Executes empirical strategy matrix isolation across baseline strategies."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, meta = dm.load_dataset(req.symbol, "1m")
        if req.timeframe != "1m":
            df = dm.resample_candles(df_raw, target_timeframe=req.timeframe)
        else:
            df = df_raw

        provenance = {
            "source_symbol": req.symbol.upper(),
            "source_timeframe": "1m",
            "source_bars": len(df_raw),
            "analysis_timeframe": req.timeframe,
            "analysis_bars": len(df),
            "date_start": (meta.start_time.isoformat() if hasattr(meta.start_time, "isoformat") else str(meta.start_time)) if meta and meta.start_time else None,
            "date_end": (meta.end_time.isoformat() if hasattr(meta.end_time, "isoformat") else str(meta.end_time)) if meta and meta.end_time else None,
            "data_quality_score": meta.data_quality_score if meta else 100.0,
        }

        strat_descriptions = {
            "S1": "Opening Range Breakout (ORB)",
            "S2": "1m Momentum Breakout",
            "S3": "VWAP Reclaim / Reject",
            "S4": "Volatility Compression Breakout (Experimental)",
            "S5": "Structural Volume & Absorption Breakout",
            "S6-A": "S6-A: Compression Breakout (Continuation)",
            "S6-F": "S6-F: Failed Breakout Reversal",
            "S7": "Structural Absorption Reversal",
            "S8": "IV Regime Mispricing (S8SPEC_v1.0)",
            "S4+S8": "S4+S8 Confluence (Squeeze Breakout + IV Regime Agreement)",
            "S1+S3": "S1+S3 Confluence (ORB + VWAP Reclaim Agreement)",
            "ALL": "Portfolio Combination (S1-S5, S7-S8)",
        }

        matrix_rows = []
        for strat_key in ["S1", "S2", "S3", "S4", "S5", "S6-A", "S6-F", "S7", "S8", "S4+S8", "S1+S3", "ALL"]:
            if strat_key in ("S6-A", "S6-F"):
                track_id = "S6A_T1" if strat_key == "S6-A" else "S6F_T1"
                try:
                    s6_m, _, _ = run_s6_track(
                        instrument=req.symbol.upper(),
                        track=track_id,
                        df_1m=df_raw,
                    )
                    g0_v = "INCONCLUSIVE" if s6_m.total_trades < 25 else ("PASSED" if s6_m.net_expectancy_R > 0 and s6_m.profit_factor >= 1.10 else "FAILED")
                    reasons = [f"Sample size: {s6_m.total_trades} trades (need >= 25). S6 status: EXPERIMENTAL."]
                    matrix_rows.append({
                        "strategy_key": strat_key,
                        "strategy_name": strat_descriptions.get(strat_key, strat_key),
                        "total_trades": s6_m.total_trades,
                        "win_rate": round(s6_m.win_rate, 4),
                        "gross_expectancy_pct": round(s6_m.gross_expectancy_R * 0.005, 4),
                        "net_expectancy_pct": round(s6_m.net_expectancy_R * 0.005, 4),
                        "profit_factor": round(s6_m.profit_factor, 2),
                        "max_drawdown_pct": round(s6_m.max_drawdown_R * 0.005, 4),
                        "annualized_sharpe": 0.0,
                        "deflated_sharpe_ratio": 0.0,
                        "gate_g0_verdict": g0_v,
                        "verdict_reasons": reasons,
                    })
                except Exception as e:
                    logger.warning("s6_matrix_error", strat_key=strat_key, error=str(e))
                    matrix_rows.append({
                        "strategy_key": strat_key,
                        "strategy_name": strat_descriptions.get(strat_key, strat_key),
                        "total_trades": 0,
                        "win_rate": 0.0,
                        "gross_expectancy_pct": 0.0,
                        "net_expectancy_pct": 0.0,
                        "profit_factor": 0.0,
                        "max_drawdown_pct": 0.0,
                        "annualized_sharpe": 0.0,
                        "deflated_sharpe_ratio": 0.0,
                        "gate_g0_verdict": "INCONCLUSIVE",
                        "verdict_reasons": [f"Execution error: {str(e)}"],
                    })
                continue

            harness = BacktestHarness(
                lot_size=10 if "sensex" in req.symbol.lower() else 25,
                t_max_bars=req.t_max_bars,
                k_tp=req.k_tp,
                k_sl=req.k_sl,
                trend_aligned=req.trend_aligned,
                session_filter=req.session_filter,
            )
            _, metrics = harness.run_backtest(
                df=df,
                strategy_key=strat_key,
                stress_multiplier=req.stress_multiplier,
            )
            matrix_rows.append({
                "strategy_key": strat_key,
                "strategy_name": strat_descriptions.get(strat_key, strat_key),
                "total_trades": metrics.total_trades,
                "win_rate": round(metrics.win_rate, 4),
                "gross_expectancy_pct": round(metrics.gross_expectancy_pct, 4),
                "net_expectancy_pct": round(metrics.net_expectancy_pct, 4),
                "profit_factor": round(metrics.profit_factor, 2),
                "max_drawdown_pct": round(metrics.max_drawdown_pct, 4),
                "annualized_sharpe": round(metrics.annualized_sharpe, 2),
                "deflated_sharpe_ratio": round(metrics.deflated_sharpe_ratio, 4),
                "gate_g0_verdict": metrics.gate_g0_verdict,
                "verdict_reasons": metrics.verdict_reasons,
            })

        return {
            "provenance": provenance,
            "matrix": matrix_rows,
        }

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("strategy_matrix_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Strategy matrix execution failed: {str(e)}")


@router.get("/s6/trials")
async def get_s6_trials():
    """Returns historical S6 trials and recorded run artifacts from trial registry."""
    reg = S6ExperimentRegistry()
    trials_data = reg.load_registry()
    
    enriched_trials = []
    base_dir = Path("data/experiments/s6")
    for trial_id, t_info in trials_data.get("trials", {}).items():
        trial_dir = base_dir / trial_id
        latest_metrics = None
        if trial_dir.exists():
            runs = sorted(trial_dir.glob("run_*"), reverse=True)
            if runs and (runs[0] / "metrics.json").exists():
                try:
                    with open(runs[0] / "metrics.json", "r") as f:
                        latest_metrics = json.load(f)
                except Exception:
                    pass
        item = dict(t_info)
        item["metrics"] = latest_metrics
        enriched_trials.append(item)

    return envelope(
        {
            "trial_count": len(enriched_trials),
            "trials": enriched_trials,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.post("/s6/run")
async def run_s6_battery(req: S6RunRequest):
    """Executes S6 Research MVP triage across the 2x2 core matrix."""
    dm = DatasetManager()
    instrument = req.instrument.upper()
    symbol_key = instrument.lower()

    if not dm.exists(symbol_key, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {instrument}")

    def _execute():
        df_1m, meta = dm.load_dataset(symbol_key, "1m")
        tracks_to_run = (
            ["S6A_T1", "S6A_T4", "S6F_T1", "S6F_T4"]
            if req.track == "ALL"
            else [req.track.upper()]
        )

        reg = S6ExperimentRegistry()
        results: Dict[str, Any] = {}

        for trk in tracks_to_run:
            metrics, trades, run_dir = run_s6_track(
                instrument=instrument,
                track=trk,
                df_1m=df_1m,
                registry=reg,
            )
            m_dict = metrics.to_dict()
            g0_v = "INCONCLUSIVE" if metrics.total_trades < 25 else ("PASSED" if metrics.net_expectancy_R > 0 and metrics.profit_factor >= 1.10 else "FAILED")
            reasons = [f"Sample size: {metrics.total_trades} trades (need >= 25 for statistical validity). S6 status: EXPERIMENTAL."]
            if metrics.total_trades >= 25 and metrics.net_expectancy_R <= 0:
                reasons.append(f"Negative net expectancy: {metrics.net_expectancy_R:.3f}R")
            m_dict["gate_g0_verdict"] = g0_v
            m_dict["verdict_reasons"] = reasons
            m_dict["sample_trades"] = [t.to_dict() for t in trades[:10]]
            m_dict["run_dir"] = str(run_dir)
            results[trk] = m_dict

        provenance = {
            "instrument": instrument,
            "source_bars": len(df_1m),
            "start_time": (meta.start_time.isoformat() if hasattr(meta.start_time, "isoformat") else str(meta.start_time)) if meta and meta.start_time else None,
            "end_time": (meta.end_time.isoformat() if hasattr(meta.end_time, "isoformat") else str(meta.end_time)) if meta and meta.end_time else None,
            "spec_version": "S6SPEC_v1.3",
            "status": "EXPERIMENTAL",
            "promotion": "BLOCKED (G0)",
        }

        return {
            "provenance": provenance,
            "matrix": results,
        }

    try:
        res = await asyncio.to_thread(_execute)
        return envelope(res, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("s6_battery_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"S6 battery execution failed: {str(e)}")


@router.post("/g2-robustness")
async def run_g2_robustness(req: G2RunRequest):
    """Executes Gate G2 robustness: cost-stress survival + parameter sensitivity."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, _ = dm.load_dataset(req.symbol, "1m")
        if req.timeframe != "1m":
            df = dm.resample_candles(df_raw, target_timeframe=req.timeframe)
        else:
            df = df_raw

        evaluator = GateG2Evaluator(
            t_max_bars=req.t_max_bars,
            k_tp=req.k_tp,
            k_sl=req.k_sl,
            trend_aligned=req.trend_aligned,
            session_filter=req.session_filter,
            lot_size=10 if "sensex" in req.symbol.lower() else 25,
        )
        report = evaluator.evaluate(
            df, strategy_key=req.strategy_key, trend_aligned=req.trend_aligned
        )
        return report.to_dict()

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("g2_robustness_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Gate G2 evaluation failed: {str(e)}")


def _build_matrix_rows(
    symbol: str,
    timeframe: str,
    k_tp: float,
    k_sl: float,
    t_max_bars: int,
    trend_aligned: bool,
    session_filter: bool,
    stress_multiplier: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Shared strategy-matrix computation for JSON + CSV export."""
    from app.quant.research.s6_runner import run_s6_track as _run_s6

    dm = DatasetManager()
    df_raw, meta = dm.load_dataset(symbol, "1m")
    if timeframe != "1m":
        df = dm.resample_candles(df_raw, target_timeframe=timeframe)
    else:
        df = df_raw

    provenance = {
        "source_symbol": symbol.upper(),
        "source_timeframe": "1m",
        "source_bars": len(df_raw),
        "analysis_timeframe": timeframe,
        "analysis_bars": len(df),
        "date_start": (meta.start_time.isoformat() if hasattr(meta.start_time, "isoformat") else str(meta.start_time)) if meta and meta.start_time else None,
        "date_end": (meta.end_time.isoformat() if hasattr(meta.end_time, "isoformat") else str(meta.end_time)) if meta and meta.end_time else None,
        "data_quality_score": meta.data_quality_score if meta else 100.0,
    }

    strat_descriptions = {
        "S1": "Opening Range Breakout (ORB)",
        "S2": "1m Momentum Breakout",
        "S3": "VWAP Reclaim / Reject",
        "S4": "Volatility Compression Breakout (Experimental)",
        "S5": "Structural Volume & Absorption Breakout",
        "S6-A": "S6-A: Compression Breakout (Continuation)",
        "S6-F": "S6-F: Failed Breakout Reversal",
        "S7": "Structural Absorption Reversal",
        "S8": "IV Regime Mispricing (S8SPEC_v1.0)",
        "S4+S8": "S4+S8 Confluence (Squeeze Breakout + IV Regime Agreement)",
        "S1+S3": "S1+S3 Confluence (ORB + VWAP Reclaim Agreement)",
        "ALL": "Portfolio Combination (S1-S5, S7-S8)",
    }

    matrix_rows: list[dict[str, Any]] = []
    for strat_key in ["S1", "S2", "S3", "S4", "S5", "S6-A", "S6-F", "S7", "S8", "S4+S8", "S1+S3", "ALL"]:
        if strat_key in ("S6-A", "S6-F"):
            track_id = "S6A_T1" if strat_key == "S6-A" else "S6F_T1"
            try:
                s6_m, _, _ = _run_s6(
                    instrument=symbol.upper(),
                    track=track_id,
                    df_1m=df_raw,
                )
                g0_v = "INCONCLUSIVE" if s6_m.total_trades < 25 else ("PASSED" if s6_m.net_expectancy_R > 0 and s6_m.profit_factor >= 1.10 else "FAILED")
                reasons = [f"Sample size: {s6_m.total_trades} trades (need >= 25). S6 status: EXPERIMENTAL."]
                matrix_rows.append({
                    "strategy_key": strat_key,
                    "strategy_name": strat_descriptions.get(strat_key, strat_key),
                    "total_trades": s6_m.total_trades,
                    "win_rate": round(s6_m.win_rate, 4),
                    "gross_expectancy_pct": round(s6_m.gross_expectancy_R * 0.005, 4),
                    "net_expectancy_pct": round(s6_m.net_expectancy_R * 0.005, 4),
                    "profit_factor": round(s6_m.profit_factor, 2),
                    "max_drawdown_pct": round(s6_m.max_drawdown_R * 0.005, 4),
                    "annualized_sharpe": 0.0,
                    "deflated_sharpe_ratio": 0.0,
                    "gate_g0_verdict": g0_v,
                    "verdict_reasons": reasons,
                })
            except Exception as e:
                logger.warning("s6_matrix_error", strat_key=strat_key, error=str(e))
                matrix_rows.append({
                    "strategy_key": strat_key,
                    "strategy_name": strat_descriptions.get(strat_key, strat_key),
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "gross_expectancy_pct": 0.0,
                    "net_expectancy_pct": 0.0,
                    "profit_factor": 0.0,
                    "max_drawdown_pct": 0.0,
                    "annualized_sharpe": 0.0,
                    "deflated_sharpe_ratio": 0.0,
                    "gate_g0_verdict": "INCONCLUSIVE",
                    "verdict_reasons": [f"Execution error: {str(e)}"],
                })
            continue

        harness = BacktestHarness(
            lot_size=10 if "sensex" in symbol.lower() else 25,
            t_max_bars=t_max_bars,
            k_tp=k_tp,
            k_sl=k_sl,
            trend_aligned=trend_aligned,
            session_filter=session_filter,
        )
        _, metrics = harness.run_backtest(
            df=df,
            strategy_key=strat_key,
            stress_multiplier=stress_multiplier,
        )
        matrix_rows.append({
            "strategy_key": strat_key,
            "strategy_name": strat_descriptions.get(strat_key, strat_key),
            "total_trades": metrics.total_trades,
            "win_rate": round(metrics.win_rate, 4),
            "gross_expectancy_pct": round(metrics.gross_expectancy_pct, 4),
            "net_expectancy_pct": round(metrics.net_expectancy_pct, 4),
            "profit_factor": round(metrics.profit_factor, 2),
            "max_drawdown_pct": round(metrics.max_drawdown_pct, 4),
            "annualized_sharpe": round(metrics.annualized_sharpe, 2),
            "deflated_sharpe_ratio": round(metrics.deflated_sharpe_ratio, 4),
            "gate_g0_verdict": metrics.gate_g0_verdict,
            "verdict_reasons": metrics.verdict_reasons,
        })

    return provenance, matrix_rows


@router.post("/strategy-matrix-export")
async def export_strategy_matrix(req: StrategyMatrixRequest):
    """Exports the strategy isolation matrix as CSV (same computation as /strategy-matrix)."""
    if not DatasetManager().exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        provenance, matrix_rows = _build_matrix_rows(
            symbol=req.symbol,
            timeframe=req.timeframe,
            k_tp=req.k_tp,
            k_sl=req.k_sl,
            t_max_bars=req.t_max_bars,
            trend_aligned=req.trend_aligned,
            session_filter=req.session_filter,
            stress_multiplier=req.stress_multiplier,
        )
        csv_text = matrix_to_csv(matrix_rows)
        filename = f"strategy_matrix_{req.symbol.lower()}_{req.timeframe}_kTp{req.k_tp}_kSl{req.k_sl}.csv"
        return {"provenance": provenance, "csv": csv_text, "filename": filename}

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("strategy_matrix_export_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Strategy matrix export failed: {str(e)}")


@router.post("/g0-trades-export")
async def export_g0_trades(req: G0RunRequest):
    """Exports Gate G0 sample trades as CSV (same computation as /g0-baseline)."""
    dm = DatasetManager()
    if not dm.exists(req.symbol, "1m"):
        raise HTTPException(status_code=404, detail=f"Base 1m dataset not found for {req.symbol}")

    def _execute():
        df_raw, _ = dm.load_dataset(req.symbol, "1m")
        df = dm.resample_candles(df_raw, target_timeframe=req.timeframe) if req.timeframe != "1m" else df_raw
        harness = BacktestHarness(
            t_max_bars=req.t_max_bars,
            k_tp=req.k_tp,
            k_sl=req.k_sl,
            trend_aligned=req.trend_aligned,
        )
        trades, metrics = harness.run_backtest(
            df=df,
            strategy_key=req.strategy_key,
            stress_multiplier=req.stress_multiplier,
        )
        rows = [
            {
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "strategy_id": t.strategy_id,
                "direction": t.direction,
                "gross_pnl_pct": round(t.gross_pnl_pct, 4),
                "net_pnl_pct": round(t.net_pnl_pct, 4),
                "total_cost_pct": round(t.total_cost_pct, 4),
                "exit_reason": t.exit_reason,
                "bars_held": t.bars_held,
            }
            for t in trades
        ]
        csv_text = trades_to_csv(rows)
        filename = f"g0_trades_{req.symbol.lower()}_{req.timeframe}_{req.strategy_key.lower()}.csv"
        return {
            "metrics": metrics.to_dict(),
            "trade_count": len(rows),
            "csv": csv_text,
            "filename": filename,
        }

    try:
        result = await asyncio.to_thread(_execute)
        return envelope(result, provider=_PROVIDER, status=DataStatus.OFFLINE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("g0_trades_export_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"G0 trades export failed: {str(e)}")


