"""
VORTEX-SNAP API Router
Endpoints for Microstructure Telemetry, Live State Machine HUD,
Event-Driven Backtesting, Ablation Study, and Research Experiments (§43–§47).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.envelope import envelope
from app.models.market import DataStatus
from app.quant.data.provenance import ProvenanceError
from app.signals.strategies.base import StrategyContext
from app.signals.strategies.vortex_snap.config import VortexSnapConfig
from app.signals.strategies.vortex_snap.session import MarketSessionModel
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.ml.validator import VortexMLValidator
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalDataLoader, HistoricalBarContext
from app.signals.strategies.vortex_snap.backtest.engine import VortexBacktestEngine
from app.signals.strategies.vortex_snap.backtest.cost_model import TransactionCostModel
from app.signals.strategies.vortex_snap.backtest.ablation import ComponentAblationRunner
from app.signals.strategies.vortex_snap.types import Candle

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/strategies/vortex-snap", tags=["vortex-snap"])
_PROVIDER = "vortex_snap_engine"


# -------------------------------------------------------------
# Request & Response Schemas
# -------------------------------------------------------------
class VortexBacktestRequest(BaseModel):
    symbol: str = Field(default="SENSEX", description="Instrument symbol (SENSEX, NIFTY, BANKNIFTY)")
    slippage_stress: float = Field(default=1.0, ge=1.0, le=5.0, description="Cost stress factor (1.0x to 5.0x)")
    execution_lag: int = Field(default=1, ge=0, le=2, description="Execution delay in bars (0 or 1)")
    initial_capital: float = Field(default=500_000.0, description="Starting capital in INR")
    max_bars: Optional[int] = Field(default=1500, description="Maximum bars to simulate (None for full dataset)")


# -------------------------------------------------------------
# Global Singletons / Cached Instances
# -------------------------------------------------------------
_config = VortexSnapConfig()
# Default strict real-data ON: the live HUD path must 503 when the 1m parquet is
# missing instead of silently serving the seed-42 simulation. (File default in
# backend/config/vortex_snap.json is require_real_data=true; enforced here as well
# so runtime never depends on a lax programmatic default. Env var can still opt
# out explicitly for local dev: VORTEX_SNAP_REQUIRE_REAL_DATA=false.)
_config.data.require_real_data = True
_session_model = MarketSessionModel(_config.session)
_ml_validator = VortexMLValidator(enabled=True)
_strategy_instance: Optional[VortexSnapStrategy] = None
_data_loader = HistoricalDataLoader()


def get_vortex_strategy() -> VortexSnapStrategy:
    global _strategy_instance
    if _strategy_instance is None:
        _strategy_instance = VortexSnapStrategy(_config)
    return _strategy_instance


def _require_real_data() -> bool:
    env = os.environ.get(_config.data.strict_mode_env)
    if env is not None:
        return env.strip().lower() in ("1", "true", "yes", "on")
    return _config.data.require_real_data


def _get_live_candles(symbol: str, count: int) -> Tuple[List[Candle], Dict[str, Any]]:
    """Read closed 1m candles aggregated from FYERS HSM websocket ticks.

    Source of truth for the live HUD. Returns ([], NO_DATA status) when the
    feed has nothing — it never fabricates prices.
    """
    try:
        from app.services.live_candles import live_candles

        return live_candles.get_candles(symbol, count)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("vortex_live_candles_unavailable", instrument=symbol, error=str(exc)[:200])
        return [], {"status": "NO_DATA", "bars": 0, "age_s": None}


def _get_candles(
    symbol: str, count: int = 375, *, allow_synthetic: bool = False, prefer_live: bool = True
) -> Tuple[List[Candle], Dict[str, Any]]:
    """Helper returning candles + an honest source dict.

    Source priority (live path, prefer_live=True):
      1. Live 1m candles aggregated from FYERS HSM websocket ticks
         (``app.services.live_candles``) — the source of truth.
      2. Verified real parquet (only when the live feed has insufficient bars).
      3. Explicit synthetic (backtest/ablation opt-in only).

    Strict-by-default: when neither live bars nor a verified parquet dataset is
    available, the live HUD path raises HTTP 503. No silent seed-42 fallback.
    """
    symbol_upper = symbol.upper()
    require_real = _require_real_data()
    if allow_synthetic:
        # Explicit backtest/test opt-in to the seed-42 generator. Real parquet,
        # when present, is still preferred by load_candles_with_source.
        require_real = False

    if prefer_live:
        live, live_status = _get_live_candles(symbol_upper, count)
        min_bars = int(os.environ.get("VORTEX_LIVE_MIN_BARS", "30"))
        if len(live) >= min_bars:
            logger.info(
                "vortex_data_live_ws",
                instrument=symbol_upper,
                bars=len(live),
                feed_status=live_status.get("status"),
            )
            source = {
                "type": "fyers_ws_live",
                "instrument": symbol_upper,
                "path": None,
                "is_simulated": False,
                "note": "Live 1m OHLCV aggregated from FYERS HSM websocket ticks.",
                "provenance_verified": True,
                "live": live_status,
            }
            return live, source
        if require_real and _data_loader.locate_parquet(symbol_upper, "1m") is None:
            # Contain the phrase "Real market data required" so callers/tests
            # get one consistent strict-mode message. When a dataset path does
            # exist, fall through: the loader's provenance screen still decides
            # (an unverifiable parquet 503s there).
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Real market data required for VORTEX-SNAP but the live FYERS websocket "
                    f"feed has no usable 1m candles for {symbol_upper} "
                    f"(live status={live_status.get('status')}, bars={len(live)}, "
                    f"min_required={min_bars}) and no 1m parquet dataset exists. "
                    f"Ensure FYERS_WS_ENABLED=true and the HSM socket is authenticated, "
                    f"or provide a verified 1m parquet dataset."
                ),
            )
        logger.warning(
            "vortex_live_feed_insufficient",
            instrument=symbol_upper,
            feed_status=live_status.get("status"),
            bars=len(live),
            min_required=min_bars,
            note="falling back to provenance-checked parquet",
        )

    try:
        candles, source = _data_loader.load_candles_with_source(
            instrument=symbol_upper,
            timeframe="1m",
            count=count,
            require_real_data=require_real,
        )
    except FileNotFoundError:
        symbol_lower = symbol_upper.lower()
        raise HTTPException(
            status_code=503,
            detail=(
                f"Real market data required for VORTEX-SNAP but no 1m parquet dataset found for {symbol}. "
                f"Provide backend/data/raw/{symbol_lower}/1m.parquet or set {_config.data.strict_mode_env}=false "
                "to permit the simulated fallback."
            ),
        )
    except ProvenanceError as exc:
        # A parquet that exists but is not market data is a data-source failure,
        # not a working HUD on synthetic prices. Never degrade into a fallback.
        logger.error("vortex_data_provenance_failed", instrument=symbol, error=str(exc))
        raise HTTPException(
            status_code=503,
            detail=(
                f"1m dataset for {symbol} exists but is not verifiable market data: {exc}"
            ),
        )
    if source.type == "synthetic":
        logger.warning("vortex_data_synthetic_fallback", instrument=symbol, note=source.note)
    return candles, source.to_dict()


def _compute_atr_14(candles: List[Candle], period: int = 14) -> float:
    """Real ATR-14 (Wilder smoothing) in index points over 1m candles."""
    if len(candles) < 2:
        return 0.0
    trs: List[float] = []
    for prev, c in zip(candles[:-1], candles[1:]):
        trs.append(max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close)))
    if len(trs) < period:
        return round(float(sum(trs) / len(trs)), 2)
    atr = float(sum(trs[:period]) / period)
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 2)


def _serialize_level(level: Any) -> Dict[str, Any]:
    """Full level passthrough: type, relevance, touches, rejections, broken/retest, distances."""
    level_type = getattr(level.level_type, "value", str(level.level_type))
    return {
        "price": level.price,
        "level_type": level_type,
        "relevance": round(level.relevance_score, 3),
        "touches": level.touch_count,
        "rejections": level.rejection_count,
        "is_broken": level.is_broken,
        "is_retest": level.is_retested,
        "distance_points": round(level.distance_points, 2),
        "distance_pct": level.distance_pct,
    }


# -------------------------------------------------------------
# 1. Engine Status & Telemetry (§43)
# -------------------------------------------------------------
@router.get("/status")
async def get_vortex_status():
    """Get active telemetry, session phase, kill-switch status, and ML validator health."""
    now_ms = int(time.time() * 1000)
    session_info = _session_model.evaluate(now_ms)
    
    ml_health = {
        "is_model_loaded": _ml_validator._is_loaded,
        "model_artifact_path": str(_ml_validator.artifact_path) if _ml_validator.artifact_path else None,
        "feature_count": 22,
        "calibration_enabled": _ml_validator.enabled,
        "acceptance_threshold": _ml_validator.acceptance_threshold,
    }

    return envelope(
        data={
            "strategy": "VORTEX_SNAP",
            "version": "1.0.0-PROD",
            "status": "ONLINE",
            "primary_hypothesis": "Translation Ratio (Pressure vs Price Displacement) contains predictive short-horizon alpha",
            "primary_timeframe": "1m execution / 5m contextual regime",
            "instruments_supported": ["SENSEX", "NIFTY", "BANKNIFTY"],
            "session": {
                "phase": session_info.session_phase.value,
                "is_trading_allowed": session_info.is_trading_allowed,
                "is_forced_square_off": session_info.is_forced_square_off,
                "session_progress_pct": round(min(1.0, max(0.0, session_info.minutes_from_open / 375.0)) * 100, 2),
                "minutes_to_market_close": session_info.minutes_to_close,
            },
            "ml_validator": ml_health,
            "config": _config.model_dump(),
        },
        provider=_PROVIDER,
    )


# -------------------------------------------------------------
# 2. Point-in-Time Microstructure State & HUD (§43)
# -------------------------------------------------------------
@router.get("/microstructure/{symbol}")
async def get_microstructure_state(
    symbol: str = "SENSEX",
    bars: int = Query(default=120, ge=30, le=500),
):
    """
    Returns the real-time microstructure state computed over recent candles.
    Feeds the Microstructure HUD: Compression, Pressure, Translation Ratio,
    Absorption, Liquidity Vacuum, Snap Energy, Regime, and FSM state.
    """
    symbol_clean = symbol.upper()
    candles_1m, source_dict = _get_candles(symbol_clean, count=bars)
    candles_5m = HistoricalDataLoader.resample_5m(candles_1m)

    strat = get_vortex_strategy()
    feature_engine = strat.feature_engine

    last_candle = candles_1m[-1]
    snapshot = feature_engine.compute_snapshot(
        instrument=symbol_clean,
        candles_1m=candles_1m,
        timestamp_ms=last_candle.timestamp,
        spot_price=last_candle.close,
        candles_5m=candles_5m,
    )

    # Convert candles to dict format expected by StrategyContext
    dict_candles = [
        {
            "timestamp": c.timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
        }
        for c in candles_1m
    ]

    # Evaluate candidate using strategy adapter
    ctx = StrategyContext(
        underlying=symbol_clean,
        spot_price=Decimal(str(round(last_candle.close, 2))),
        timestamp_ms=last_candle.timestamp,
        candles=dict_candles,
        daily_loss_limit_breached=False,
        portfolio_positions=[],
    )
    candidate = strat.detect(ctx)

    comp = snapshot.compression
    press = snapshot.pressure
    trans = snapshot.translation
    absorb = snapshot.absorption
    vac = snapshot.vacuum
    snap = snapshot.snap_energy
    reg = snapshot.regime
    levels = snapshot.structural_levels

    hud_data = {
        "symbol": symbol_clean,
        "data_source": source_dict,
        "timestamp": datetime.fromtimestamp(snapshot.timestamp_ms / 1000, tz=timezone.utc).isoformat(),
        # Last-candle freshness for the frontend (age/staleness handling lives
        # in the UI — it diffs server_now_ms against last_candle_timestamp_ms).
        "last_candle_timestamp_ms": last_candle.timestamp,
        "last_candle_timestamp": datetime.fromtimestamp(last_candle.timestamp / 1000, tz=timezone.utc).isoformat(),
        "server_now_ms": int(time.time() * 1000),
        "latest_close": last_candle.close,
        "compression": {
            "score": round(comp.compression_score, 4),
            "zone": comp.zone.value,
            "is_compressed": comp.zone.value in ("ARMED", "EXTREME"),
            "is_severe_compression": comp.zone.value == "EXTREME",
            "duration_bars": comp.duration_bars,
            "channel_range_pct": round(comp.range_contraction * 100, 3),
        },
        "directional_pressure": {
            "score": round(press.pressure_score, 4),
            "persistence": press.pressure_persistence,
            "persistence_abs": abs(press.pressure_persistence),
            # Normalized acceleration is comparable to score units/bar.
            # Raw value kept for debugging/ML backward-compat.
            "acceleration": round(float(getattr(press, "pressure_acceleration_norm", press.pressure_acceleration)), 4),
            "acceleration_raw": round(press.pressure_acceleration, 4),
            "is_bullish": press.pressure_score > 0,
            "is_strong": abs(press.pressure_score) > 0.50,
        },
        "translation_ratio": {
            "ratio": round(trans.translation_ratio, 4),
            # Backward-compat: normalized (dimensionless) value.
            "displacement": round(trans.normalized_displacement, 4),
            "displacement_norm": round(trans.normalized_displacement, 4),
            "displacement_pts": round(float(getattr(trans, "raw_displacement_points", 0.0)), 2),
            "translation_state": trans.translation_state.value,
            "is_directional_acceptance": trans.translation_state.value == "DIRECTIONAL_ACCEPTANCE",
            "is_absorption_candidate": trans.translation_state.value == "ABSORPTION_CANDIDATE",
            "is_rejection_conflict": trans.translation_state.value == "REJECTION_CONFLICT",
        },
        "absorption": {
            "is_detected": absorb.is_absorption_suspected,
            "absorption_score": round(absorb.absorption_score, 4),
            "side": 1 if absorb.opposing_pressure else -1,
            "exhaustion_volume_ratio": round(absorb.volume_shock_ratio, 2),
        },
        "liquidity_vacuum": {
            "is_detected": vac.is_vacuum_detected,
            "vacuum_score": round(vac.liquidity_vacuum_score, 4),
            "thin_depth_side": "ASK" if press.pressure_score > 0 else "BID",
            "displacement_velocity": round(vac.range_expansion, 2),
        },
        "snap_energy": {
            "energy_score": round(snap.snap_energy, 4),
            "is_snap_ready": snap.energy_tier in ("HIGH", "EXPLOSIVE"),
            "energy_tier": snap.energy_tier,
        },
        "market_regime": {
            "regime": reg.regime.value,
            "confidence": round(reg.regime_confidence, 3),
            # Explicit fallback marker: UNKNOWN regime or low confidence (<=0.30)
            # means "no measurement" — includes the ablation-disabled path
            # (UNKNOWN) and the insufficient-history path. Never styled as a
            # measured call on the frontend when true.
            "is_fallback": bool(reg.regime.value == "UNKNOWN" or reg.regime_confidence <= 0.30),
            "fallback_reason": (
                "ablation_or_insufficient_data:UNKNOWN"
                if reg.regime.value == "UNKNOWN"
                else ("low_confidence_fallback" if reg.regime_confidence <= 0.30 else None)
            ),
            "adx": round(reg.trend_strength * 50.0, 2),
            "atr_14": _compute_atr_14(candles_1m),
            "efficiency_ratio": round(reg.efficiency_ratio, 4),
            "volatility_state": reg.volatility_state,
        },
        "structural_levels": {
            # Backward-compat price shortcuts:
            "nearest_support": levels.nearest_support.price if levels.nearest_support else None,
            "nearest_resistance": levels.nearest_resistance.price if levels.nearest_resistance else None,
            # Explicit type labels: nearest support may be a broken HIGH-type
            # (e.g. SWING_HIGH_5M/SESSION_HIGH below price after a breakout) and
            # nearest resistance may be a LOW-type — never infer side from type.
            "nearest_support_type": (
                levels.nearest_support.level_type.value if levels.nearest_support else None
            ),
            "nearest_resistance_type": (
                levels.nearest_resistance.level_type.value if levels.nearest_resistance else None
            ),
            "nearest_support_detail": (
                _serialize_level(levels.nearest_support) if levels.nearest_support else None
            ),
            "nearest_resistance_detail": (
                _serialize_level(levels.nearest_resistance) if levels.nearest_resistance else None
            ),
            "support_distance_points": round(levels.distance_to_nearest_support or 0.0, 2),
            "resistance_distance_points": round(levels.distance_to_nearest_resistance or 0.0, 2),
            "relevance_score": round(levels.nearest_support.relevance_score if levels.nearest_support else 0.0, 3),
            "levels": [
                _serialize_level(lvl)
                for lvl in sorted(levels.levels, key=lambda l: l.relevance_score, reverse=True)[:10]
            ],
        },
        "fsm_state": {
            "current_state": strat.fsm.state.value if hasattr(strat.fsm.state, "value") else str(strat.fsm.state),
            "state_enter_bar_count": strat.fsm.state_enter_bar_count,
            "transition_history": [
                {
                    "from_state": t.from_state.value,
                    "to_state": t.to_state.value,
                    "timestamp_ms": t.timestamp_ms,
                    "reason": t.reason,
                }
                for t in strat.fsm.transition_history[-10:]
            ],
        },
        "active_candidate": (
            {
                "strategy": candidate.strategy,
                "underlying": candidate.underlying,
                "direction": candidate.direction,
                "trigger_price": float(candidate.trigger),
                "stop_loss": float(candidate.stop_loss),
                "target_1": float(candidate.target_1),
                "target_2": float(candidate.target_2),
                "confidence": round(float(candidate.overall_confidence), 3),
                "reason_codes": candidate.rationale,
            }
            if candidate
            else None
        ),
    }

    return envelope(data=hud_data, provider=_PROVIDER)


# -------------------------------------------------------------
# 3. Interactive Event-Driven Backtesting Engine (§30, §35)
# -------------------------------------------------------------
@router.post("/backtest")
async def run_vortex_backtest(request: VortexBacktestRequest):
    """
    Executes a high-fidelity, event-driven backtest for VORTEX-SNAP.
    Enforces conservative execution rules, transaction cost friction, and returns
    full institutional metrics with sample-decimated equity curve.
    """
    symbol_clean = request.symbol.upper()
    # Explicit synthetic flag: backtests may use the seed-42 session when no
    # parquet exists (source reported in data_source); live HUD path may not.
    candles, source_dict = _get_candles(
        symbol_clean, count=request.max_bars or 1500, allow_synthetic=True, prefer_live=False
    )
    bar_contexts = HistoricalDataLoader.compute_session_levels(candles)

    cost_model = TransactionCostModel(
        brokerage_per_order=20.0,
        slippage_stress_multiplier=request.slippage_stress,
    )

    lot_size = 10 if "SENSEX" in symbol_clean else (15 if "BANK" in symbol_clean else 25)

    engine = VortexBacktestEngine(
        cost_model=cost_model,
        initial_capital=request.initial_capital,
        lot_size=lot_size,
        enable_dynamic_exits=True,
        enable_time_decay=True,
        enable_pressure_collapse_exit=True,
        execution_lag_bars=request.execution_lag,
    )

    summary = engine.run(bar_contexts, instrument=symbol_clean)
    metrics_dict = summary.to_dict()

    # Sample equity curve for smooth rendering
    eq_curve = summary.equity_curve
    max_pts = 400
    if len(eq_curve) > max_pts:
        step = len(eq_curve) // max_pts
        sampled_curve = eq_curve[::step]
        if eq_curve[-1] != sampled_curve[-1]:
            sampled_curve.append(eq_curve[-1])
    else:
        sampled_curve = eq_curve

    response_data = {
        "symbol": symbol_clean,
        "data_source": source_dict,
        "total_bars": len(bar_contexts),
        "metrics": metrics_dict,
        "exit_breakdown": summary.exit_reasons_breakdown,
        "equity_curve": sampled_curve,
        "recent_trades": [
            {
                "trade_id": t.trade_id,
                "entry_time_ms": t.entry_time_ms,
                "exit_time_ms": t.exit_time_ms,
                "direction": t.direction,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "gross_pnl_rupees": round(t.gross_pnl_rupees, 2),
                "net_pnl_rupees": round(t.net_pnl_rupees, 2),
                "friction_rupees": round(t.friction_rupees, 2),
                "exit_reason": t.exit_reason,
                "holding_bars": t.holding_bars,
                "holding_minutes": round(t.holding_minutes, 1),
                "confidence": round(t.signal_confidence, 2),
                "reason_codes": t.reason_codes,
            }
            for t in engine.last_trades[-50:]
        ],
    }

    return envelope(data=response_data, provider=_PROVIDER)


# -------------------------------------------------------------
# 4. 9-Stage Component Ablation Runner (§32)
# -------------------------------------------------------------
@router.get("/ablation")
async def get_or_run_ablation(
    symbol: str = "SENSEX",
    sample_bars: int = Query(default=750, ge=375, le=3000),
):
    """
    Executes the 9-stage component ablation study and returns the matrix.
    Tests the Primary Hypothesis: Translation Ratio contribution.
    """
    symbol_clean = symbol.upper()
    # Explicit synthetic flag: ablation studies may use the seed-42 session when
    # no parquet exists (source reported in data_source); live HUD path may not.
    candles, source_dict = _get_candles(
        symbol_clean, count=sample_bars, allow_synthetic=True, prefer_live=False
    )
    bar_contexts = HistoricalDataLoader.compute_session_levels(candles)

    runner = ComponentAblationRunner()
    report = runner.run_study(bar_contexts, instrument=symbol_clean)

    return envelope(
        data={
            "symbol": symbol_clean,
            "data_source": source_dict,
            "bars_tested": len(bar_contexts),
            **report.to_dict(),
        },
        provider=_PROVIDER,
    )


# -------------------------------------------------------------
# 5. Saved Research Experiment Reports (§50, §52)
# -------------------------------------------------------------
@router.get("/experiments")
async def list_experiment_reports():
    """List all saved research reports from data/experiments/."""
    exp_dir = Path("data/experiments")
    if not exp_dir.exists():
        return envelope(data=[], provider=_PROVIDER)

    reports = []
    for p in exp_dir.glob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = json.load(f)
            
            meta = content.get("metadata", {})
            metrics = content.get("metrics", {})
            reports.append({
                "id": p.stem,
                "filename": p.name,
                "strategy": meta.get("strategy", "VORTEX_SNAP"),
                "instrument": meta.get("instrument", "SENSEX"),
                "total_bars": meta.get("total_bars", 0),
                "generated_at": meta.get("timestamp_utc", ""),
                "metrics": {
                    "total_trades": metrics.get("total_trades", 0),
                    "win_rate_pct": round(metrics.get("win_rate_pct", metrics.get("win_rate", 0) * 100), 2),
                    "annualized_sharpe": round(metrics.get("annualized_sharpe", metrics.get("sharpe_ratio", 0)), 3),
                    "profit_factor": round(metrics.get("profit_factor", 0), 2),
                    "net_pnl_rupees": round(metrics.get("net_pnl_rupees", metrics.get("net_pnl", 0)), 2),
                    "max_drawdown_pct": round(metrics.get("max_drawdown_pct", 0), 2),
                },
            })
        except Exception as e:
            logger.warning("failed_to_parse_experiment_report", path=str(p), error=str(e))

    return envelope(data=reports, provider=_PROVIDER)


@router.get("/experiments/{experiment_id}")
async def get_experiment_report(experiment_id: str):
    """Retrieve full JSON and markdown text for a specific experiment."""
    json_path = Path(f"data/experiments/{experiment_id}.json")
    md_path = Path(f"data/experiments/{experiment_id}.md")

    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")

    with open(json_path, "r", encoding="utf-8") as f:
        json_content = json.load(f)

    md_content = ""
    if md_path.exists():
        with open(md_path, "r", encoding="utf-8") as f:
            md_content = f.read()

    return envelope(
        data={
            "id": experiment_id,
            "structured": json_content,
            "markdown": md_content,
        },
        provider=_PROVIDER,
    )
