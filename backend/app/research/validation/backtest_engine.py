"""Cheap Validation Gate for offline indicator backtesting (§19, §20).

Iterates through historical candles with strict Point-in-Time (PIT) integrity,
generates indicator predictions, measures forward outcomes, and evaluates statistical edge.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import math
import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.enums import Direction, ExperimentStatus, ForecastHorizon, MarketRegime, MarketSession
from app.research.features import classify_session_ist, determine_market_regime
from app.research.indicator_base import IndicatorBase
from app.research.models import (
    ExperimentDefinition,
    ExperimentRun,
    IndicatorContext,
    PredictionOutcome,
    ResearchPrediction,
    ValidationReport,
)
from app.research.outcome_measurer import OutcomeMeasurer
from app.research.predictions import PredictionService
from app.research.registry import IndicatorRegistry
from app.research.validation.baseline import NaiveMomentumBaseline
from app.research.validation.statistical_evaluator import StatisticalEvaluator

logger = structlog.get_logger(__name__)


class CheapValidationGate:
    """Offline validation engine for rapid, zero-risk indicator evaluation."""

    @classmethod
    async def run_experiment(
        cls,
        indicator: IndicatorBase,
        candles: List[Dict[str, Any]],
        instrument: str = "NIFTY 50",
        timeframe: str = "5m",
        horizon_candles: int = 5,
        forecast_horizon: ForecastHorizon = ForecastHorizon.HORIZON_15M,
        warmup_period: int = 30,
        stride: int = 5,
        options_ctx: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> Tuple[ExperimentRun, ValidationReport]:
        """Execute a backtest run over historical candles.
        
        Enforces Point-in-Time (PIT) integrity:
        At decision index t, the indicator can ONLY observe candles[0 : t+1].
        Forward candles[t+1 : t+1+horizon_candles] are strictly quarantined
        until the decision has been logged.
        """
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        exp_id = f"exp_{indicator.indicator_id}_{int(datetime.now(timezone.utc).timestamp())}"
        started_at = datetime.now(timezone.utc)

        total_candles = len(candles)
        if total_candles < (warmup_period + horizon_candles):
            err_msg = f"Insufficient candles: {total_candles} provided, need at least {warmup_period + horizon_candles}"
            return (
                ExperimentRun(
                    run_id=run_id,
                    experiment_id=exp_id,
                    status=ExperimentStatus.FAILED,
                    sample_count=0,
                    error_message=err_msg,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                ),
                StatisticalEvaluator.evaluate([], []),
            )

        predictions: List[ResearchPrediction] = []
        outcomes: List[PredictionOutcome] = []
        regimes: Dict[str, str] = {}
        sessions: Dict[str, str] = {}

        # Run baseline along with indicator to obtain real-world baseline accuracy
        baseline_model = NaiveMomentumBaseline()
        baseline_correct = 0

        logger.info(
            "starting_cheap_validation_gate",
            indicator=indicator.indicator_id,
            candles_count=total_candles,
            stride=stride,
        )

        for t in range(warmup_period, total_candles - horizon_candles, stride):
            past_candles = candles[: t + 1]
            forward_candles = candles[t + 1 : t + 1 + horizon_candles]

            decision_candle = past_candles[-1]
            raw_ts = decision_candle.get("timestamp")
            if isinstance(raw_ts, str):
                try:
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.now(timezone.utc)
            elif isinstance(raw_ts, datetime):
                dt = raw_ts
            else:
                dt = datetime.now(timezone.utc)

            curr_price = float(decision_candle["close"])
            sess = classify_session_ist(dt)

            p_closes = [float(c["close"]) for c in past_candles]
            p_highs = [float(c["high"]) for c in past_candles]
            p_lows = [float(c["low"]) for c in past_candles]
            dynamic_regime = determine_market_regime(p_closes, p_highs, p_lows, curr_price)

            ctx = IndicatorContext(
                instrument=instrument,
                timeframe=timeframe,
                timestamp=dt,
                candles=past_candles,
                current_price=curr_price,
                options_context=options_ctx,
                market_regime=dynamic_regime,
                session=sess,
            )

            # 1. Indicator computes prediction strictly from past data
            try:
                output = await indicator.calculate(ctx)
            except Exception as e:
                logger.warning("indicator_calc_failed_at_step", t=t, error=str(e))
                continue

            pred_id = f"pred_{uuid.uuid4().hex[:12]}"
            prediction = ResearchPrediction(
                prediction_id=pred_id,
                indicator_id=indicator.indicator_id,
                indicator_version=indicator.version,
                instrument=instrument,
                timeframe=timeframe,
                timestamp=dt,
                current_price=curr_price,
                direction=output.direction,
                score=output.score,
                confidence=output.confidence,
                raw_value=output.raw_value,
                normalized_value=output.normalized_value,
                component_values=output.component_values,
                forecast_horizon=forecast_horizon,
                horizon_candles=horizon_candles,
                target_price=output.target_price,
                invalidation_price=output.invalidation_price,
                created_at=dt,
            )
            predictions.append(prediction)
            regimes[pred_id] = output.regime_context or "UNKNOWN"
            sessions[pred_id] = sess.value

            # 2. Measure actual outcome from strictly quarantined forward data
            outcome = OutcomeMeasurer.evaluate_forward_candles(prediction, forward_candles)
            outcomes.append(outcome)

            # Baseline check
            base_dir = baseline_model.predict(past_candles)
            if base_dir == outcome.actual_direction:
                baseline_correct += 1

        empirical_baseline_acc = (baseline_correct / len(predictions)) if predictions else 0.50

        # 3. Statistical evaluation
        report = StatisticalEvaluator.evaluate(
            predictions=predictions,
            outcomes=outcomes,
            baseline_accuracy=empirical_baseline_acc,
            regimes=regimes,
            sessions=sessions,
        )

        completed_at = datetime.now(timezone.utc)
        metrics_dict = report.model_dump()

        # P1-3 power (defensive: missing module never breaks backtest).
        try:
            from app.research.validation.power import (
                ALPHA as _P_ALPHA,
                BASELINE_RATE as _P_P0,
                MDE_ABSOLUTE as _P_MDE,
                POWER as _P_PW,
                cell_status as _cell_status,
                required_n as _required_n,
            )

            _req = _required_n(_P_P0, _P_MDE, _P_ALPHA, _P_PW)
            _n = len(predictions)
            _contradictory = bool(report.is_statistically_significant and report.excess_accuracy < 0)
            metrics_dict["power"] = {
                "n": _n,
                "required_n": _req,
                "status": _cell_status(_n, _req, _contradictory),
                "baseline_rate": _P_P0,
                "mde_absolute": _P_MDE,
                "alpha": _P_ALPHA,
                "power": _P_PW,
            }
        except Exception:
            pass

        # P1-4 calibration (defensive; only when v2 probabilities present).
        try:
            from app.ml.calibration_metrics import calibration_report as _cal_report

            _idx = {"BEARISH": 0, "NEUTRAL": 1, "BULLISH": 2}

            def _dir_idx(d) -> Optional[int]:
                try:
                    key = getattr(d, "value", d)
                    return _idx.get(str(key))
                except Exception:
                    return None

            _y, _P = [], []
            _outcome_by_id = {o.prediction_id: o for o in outcomes}
            for pred in predictions:
                o = _outcome_by_id.get(pred.prediction_id)
                if o is None:
                    continue
                t = _dir_idx(o.actual_direction)
                if t is None:
                    continue
                probs = None
                try:
                    cv = pred.component_values or {}
                    if isinstance(cv.get("probabilities"), dict):
                        probs = cv["probabilities"]
                    elif isinstance(cv.get("ml_forecast"), dict) and isinstance(
                        cv["ml_forecast"].get("probabilities"), dict
                    ):
                        probs = cv["ml_forecast"]["probabilities"]
                except Exception:
                    probs = None
                if not isinstance(probs, dict):
                    continue
                try:
                    row = [float(probs["bearish"]), float(probs["neutral"]), float(probs["bullish"])]
                except (KeyError, TypeError, ValueError):
                    continue
                _y.append(t)
                _P.append(row)
            if _y and _P:
                metrics_dict["calibration"] = _cal_report(_y, _P)
        except Exception:
            pass

        # P1-5 reference costs provenance (defensive; gross/net need returns,
        # which this gate does not produce — the offline runner computes them).
        try:
            from app.research.validation.costs import COSTS_VERSION as _CV, REFERENCE_COSTS_V1 as _RC

            metrics_dict["costs_version"] = _CV
            metrics_dict["reference_costs"] = dict(_RC)
        except Exception:
            pass

        run_record = ExperimentRun(
            run_id=run_id,
            experiment_id=exp_id,
            status=ExperimentStatus.COMPLETED,
            sample_count=len(predictions),
            metrics=metrics_dict,
            started_at=started_at,
            completed_at=completed_at,
            created_at=completed_at,
        )

        logger.info(
            "validation_experiment_completed",
            samples=len(predictions),
            accuracy=report.accuracy,
            baseline=report.baseline_accuracy,
            p_value=report.p_value,
            significant=report.is_statistically_significant,
        )

        return run_record, report


# ---------------------------------------------------------------------------
# P1-2 Walk-forward + purge/embargo harness for 1H forecast v2.3
# ---------------------------------------------------------------------------
# Additive only: CheapValidationGate.run_experiment above is untouched.
#
# Design notes:
# - Chronological folds, NO shuffle. Decision indices are sequential 1h bar
#   positions; each fold's test block follows the previous fold in time.
# - Purge (H bars) + embargo (trading days -> bars) separate train/test in
#   *index space*: train = candidates with idx <= test_start - gap, where
#   gap = purge_bars + embargo_days * 6 (≈6x1h bars per NSE 09:15-15:30 day).
# - Session-aware: every candidate window [T, T+60m] is checked with
#   app.ml.sessions.classify_window. Unsettleable windows (cross-close,
#   holiday, special, off-session) are DROPPED from metrics and counted
#   separately in n_unsettleable + unsettleable_reasons. Never bridged.
# - PIT: prediction at t sees only candles[:t+1]; forward candles[t+1:t+1+H]
#   are quarantined until the decision is logged (same rule as run_experiment).
# - Targets: sibling agent may create backend/app/ml/targets_v2.py in
#   parallel — import it defensively, else fall back to app.ml.targets with
#   a comment; never fail import (spec requirement).
# - Calibration helpers (Brier / log-loss / ECE) are pure functions with
#   stdlib math only — no sklearn/scipy deps.

# Approximate 1h bars per NSE regular session (09:15-15:30 ~= 6.25h).
_WF_BARS_PER_DAY = 6


def _wf_parse_ts_utc(value: Any) -> Optional[datetime]:
    """Parse a candle timestamp to aware UTC (None on failure)."""
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str) and value:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _wf_direction_to_class(direction: Any) -> str:
    """Map Direction enum/str to lowercase 3-class key."""
    try:
        v = getattr(direction, "value", direction)
        s = str(v).upper()
    except Exception:
        s = "NEUTRAL"
    if s == "BULLISH":
        return "bullish"
    if s == "BEARISH":
        return "bearish"
    return "neutral"


def _wf_probs_for_direction(direction: Direction) -> Dict[str, float]:
    """Default deterministic 3-class probabilities for a direction."""
    if direction == Direction.BULLISH:
        return {"bullish": 0.6, "neutral": 0.2, "bearish": 0.2}
    if direction == Direction.BEARISH:
        return {"bullish": 0.2, "neutral": 0.2, "bearish": 0.6}
    return {"bullish": 0.25, "neutral": 0.5, "bearish": 0.25}


def _wf_normalize_probs(probs: Any) -> Dict[str, float]:
    """Coerce to a valid 3-class simplex (clip + renormalize, pure)."""
    out = {"bullish": 1.0 / 3.0, "neutral": 1.0 / 3.0, "bearish": 1.0 / 3.0}
    try:
        if isinstance(probs, dict):
            b = float(probs.get("bullish", out["bullish"]))
            n = float(probs.get("neutral", out["neutral"]))
            be = float(probs.get("bearish", out["bearish"]))
            b = min(1.0, max(0.0, b))
            n = min(1.0, max(0.0, n))
            be = min(1.0, max(0.0, be))
            s = b + n + be
            if s > 0:
                out = {"bullish": b / s, "neutral": n / s, "bearish": be / s}
    except Exception:
        pass
    return out


def brier_score_3class(
    y_true: List[str],
    probs: List[Dict[str, float]],
) -> float:
    """Multiclass Brier score: mean over rows of sum_k (p_k - onehot_k)^2.

    Pure (stdlib only). Range [0, 2]; lower is better. Returns 0.0 for empty.
    """
    if not y_true or not probs or len(y_true) != len(probs):
        return 0.0
    total = 0.0
    n = 0
    for y, p in zip(y_true, probs):
        try:
            pb = float(p.get("bullish", 1.0 / 3.0))
            pn = float(p.get("neutral", 1.0 / 3.0))
            pbe = float(p.get("bearish", 1.0 / 3.0))
        except Exception:
            continue
        yb = 1.0 if y == "bullish" else 0.0
        yn = 1.0 if y == "neutral" else 0.0
        ybe = 1.0 if y == "bearish" else 0.0
        total += (pb - yb) ** 2 + (pn - yn) ** 2 + (pbe - ybe) ** 2
        n += 1
    return round(total / n, 4) if n else 0.0


def log_loss_3class(
    y_true: List[str],
    probs: List[Dict[str, float]],
    eps: float = 1e-12,
) -> float:
    """3-class log-loss: -mean log(p_true clipped to [eps, 1]). Pure."""
    if not y_true or not probs or len(y_true) != len(probs):
        return 0.0
    try:
        e = float(eps)
        if not (0.0 < e < 1.0):
            e = 1e-12
    except Exception:
        e = 1e-12
    total = 0.0
    n = 0
    for y, p in zip(y_true, probs):
        try:
            pt = float(p.get(y, 1.0 / 3.0))
        except Exception:
            continue
        pt = min(1.0, max(e, pt))
        total += -math.log(pt)
        n += 1
    return round(total / n, 4) if n else 0.0


def ece_equal_width(
    confidences: List[float],
    corrects: List[bool],
    bins: int = 10,
) -> Tuple[float, List[Dict[str, Any]]]:
    """Expected Calibration Error with equal-width bins (pure, no deps).

    Accuracy signal = hit (is_correct), confidence = max(P). Returns
    (ece, reliability_table[10]) where each row has bin/lo/hi/n/accuracy/
    avg_confidence. Empty input -> (0.0, 10 empty rows).
    """
    try:
        nb = int(bins)
    except Exception:
        nb = 10
    if nb <= 0:
        nb = 10
    table: List[Dict[str, Any]] = []
    n_total = len(confidences) if confidences else 0
    if not n_total or len(corrects) != n_total:
        for b in range(1, nb + 1):
            lo = round((b - 1) / nb, 4)
            hi = round(b / nb, 4)
            table.append(
                {"bin": b, "lo": lo, "hi": hi, "n": 0,
                 "accuracy": 0.0, "avg_confidence": round((lo + hi) / 2.0, 4)}
            )
        return 0.0, table
    ece = 0.0
    for b in range(1, nb + 1):
        lo = (b - 1) / nb
        hi = b / nb
        idxs = [
            i for i, c in enumerate(confidences)
            if (float(c) > lo and float(c) <= hi) or (b == 1 and float(c) <= hi and float(c) >= 0.0)
        ]
        cnt = len(idxs)
        if cnt == 0:
            table.append({"bin": b, "lo": round(lo, 4), "hi": round(hi, 4),
                          "n": 0, "accuracy": 0.0,
                          "avg_confidence": round((lo + hi) / 2.0, 4)})
            continue
        acc = sum(1 for i in idxs if corrects[i]) / cnt
        avg_c = sum(float(confidences[i]) for i in idxs) / cnt
        ece += abs(acc - avg_c) * (cnt / n_total)
        table.append({"bin": b, "lo": round(lo, 4), "hi": round(hi, 4), "n": cnt,
                      "accuracy": round(acc, 4),
                      "avg_confidence": round(avg_c, 4)})
    return round(ece, 4), table


def _wf_split_sequential(idxs: List[int], folds: int) -> List[List[int]]:
    """Split index list into `folds` contiguous chronological blocks."""
    n = len(idxs)
    base = n // folds
    rem = n % folds
    out: List[List[int]] = []
    pos = 0
    for f in range(folds):
        size = base + (1 if f < rem else 0)
        out.append(idxs[pos: pos + size])
        pos += size
    return out


class WalkForwardGate:
    """Walk-forward + purge/embargo harness for 1H forecast v2.3 (P1-2)."""

    @classmethod
    def _summarize_records(cls, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate per-sample records into the full P1-2 metric dict."""
        n = len(records)
        if n == 0:
            _, empty_table = ece_equal_width([], [], bins=10)
            return {
                "n": 0,
                "hit_rate": 0.0,
                "wilson95": [0.0, 0.0],
                "baseline_naive_accuracy": 0.0,
                "baseline_buyhold_accuracy": 0.0,
                "excess_vs_naive": 0.0,
                "brier": 0.0,
                "log_loss": 0.0,
                "ece10": 0.0,
                "reliability_table": empty_table,
                "mfe_mean": 0.0,
                "mae_mean": 0.0,
                "target_hit_rate": 0.0,
                "stop_hit_rate": 0.0,
                "time_to_target_mean_sec": 0.0,
                "turnover": 0.0,
                "n_traded": 0,
                "p_value": 1.0,
                "is_significant": False,
            }
        correct = sum(1 for r in records if r.get("is_correct"))
        hit_rate = round(correct / n * 100.0, 2)
        try:
            ci_lo, ci_hi = StatisticalEvaluator.calculate_confidence_interval(correct, n)
        except Exception:
            ci_lo, ci_hi = 0.0, 0.0
        naive_acc = round(
            sum(1 for r in records if r.get("baseline_naive_correct")) / n * 100.0, 2
        )
        bh_acc = round(
            sum(1 for r in records if r.get("baseline_buyhold_correct")) / n * 100.0, 2
        )
        excess = round(hit_rate - naive_acc, 2)
        y_true = [str(r.get("actual_class", "neutral")) for r in records]
        plist = [dict(r.get("probs") or {}) for r in records]
        brier = brier_score_3class(y_true, plist)
        ll = log_loss_3class(y_true, plist)
        confs = [float((r.get("probs") or {}).get("p_max", r.get("confidence", 0.0)) or 0.0) for r in records]
        # p_max fallback: max of simplex when p_max missing
        fixed_confs: List[float] = []
        for r, c in zip(records, confs):
            try:
                if c and 0.0 < float(c) <= 1.0:
                    fixed_confs.append(float(c))
                    continue
                pr = r.get("probs") or {}
                fixed_confs.append(float(max(
                    float(pr.get("bullish", 0.0)),
                    float(pr.get("neutral", 0.0)),
                    float(pr.get("bearish", 0.0)),
                )))
            except Exception:
                fixed_confs.append(0.0)
        ece, rel_table = ece_equal_width(
            fixed_confs, [bool(r.get("is_correct")) for r in records], bins=10
        )
        mfe_mean = round(sum(float(r.get("mfe", 0.0)) for r in records) / n, 2)
        mae_mean = round(sum(float(r.get("mae", 0.0)) for r in records) / n, 2)
        tgt_rate = round(sum(1 for r in records if r.get("target_hit")) / n * 100.0, 2)
        stp_rate = round(sum(1 for r in records if r.get("stop_hit")) / n * 100.0, 2)
        ttt_vals = [float(r["time_to_target_sec"]) for r in records if r.get("time_to_target_sec") is not None]
        try:
            ttt_mean = round(sum(ttt_vals) / len(ttt_vals), 2) if ttt_vals else 0.0
        except Exception:
            ttt_mean = 0.0
        n_traded = sum(1 for r in records if r.get("traded"))
        turnover = round(n_traded / n, 4) if n else 0.0
        try:
            p_val = StatisticalEvaluator.calculate_p_value(
                correct / n, (naive_acc / 100.0) if n else 0.50, n
            )
        except Exception:
            p_val = 1.0
        return {
            "n": n,
            "hit_rate": hit_rate,
            "wilson95": [ci_lo, ci_hi],
            "baseline_naive_accuracy": naive_acc,
            "baseline_buyhold_accuracy": bh_acc,
            "excess_vs_naive": excess,
            "brier": brier,
            "log_loss": ll,
            "ece10": ece,
            "reliability_table": rel_table,
            "mfe_mean": mfe_mean,
            "mae_mean": mae_mean,
            "target_hit_rate": tgt_rate,
            "stop_hit_rate": stp_rate,
            "time_to_target_mean_sec": ttt_mean,
            "turnover": turnover,
            "n_traded": n_traded,
            "p_value": p_val,
            "is_significant": bool(p_val < 0.05 and excess > 0),
        }

    @classmethod
    def run_walkforward(
        cls,
        candles_1h: List[Dict[str, Any]],
        candles_1m: Optional[List[Dict[str, Any]]] = None,
        instrument: str = "NIFTY 50",
        warmup: int = 100,
        stride: int = 1,
        folds: int = 5,
        purge_bars: int = 1,
        embargo_days: int = 1,
        options_ctx: Optional[Dict[str, Any]] = None,
        cost_model: Optional[Any] = None,
        label_fn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Run chronological walk-forward validation with purge + embargo.

        PIT: decision at bar t sees only candles_1h[:t+1]; forward
        candles_1h[t+1:t+1+H] (H=1 for 1h) are quarantined. No shuffle:
        candidates are sequential bar indices split into contiguous folds;
        train = all prior candidates ending `gap` bars before the test
        block, where gap = purge_bars + embargo_days*6.

        Session-aware: each candidate [T, T+60m] is checked with
        app.ml.sessions.classify_window; unsettleable windows are dropped
        from metrics and counted in n_unsettleable/unsettleable_reasons.

        label_fn (optional sync callable): maps past_candles -> prediction.
        Accepted returns: Direction, or dict with direction/confidence/
        probabilities/score. Tried as fn(past, options_ctx) then fn(past).
        Default (None) = naive-momentum direction with fixed 0.6/0.2/0.2
        probabilities (deterministic, PIT-clean).
        """
        # Defensive targets import: sibling agent may create targets_v2 in
        # parallel — prefer it, else fall back to targets; never fail import.
        try:
            from app.ml.targets_v2 import label_forward_return_v2 as _label_v2  # noqa: F401
            target_spec_version = "v2-atr-em-session"
        except Exception:
            try:
                from app.ml.targets import TARGET_SPEC_VERSION as _v1spec  # noqa: F401
                target_spec_version = str(_v1spec)
            except Exception:
                target_spec_version = "v1-atr-band"

        # Horizon config (1h): prefer shared HORIZON_CONFIG, fallback to H=1.
        try:
            from app.research.trend_forecast import HORIZON_CONFIG as _HC
            _hcfg = (_HC or {}).get("1h", {}) or {}
            h_candles = int(_hcfg.get("horizon_candles", 1) or 1)
            h_minutes = int(_hcfg.get("minutes", 60) or 60)
        except Exception:
            h_candles, h_minutes = 1, 60

        if folds is None or int(folds) < 5:
            raise ValueError(f"folds must be >= 5 for credible OOS (got {folds})")
        folds = int(folds)
        if int(warmup) < 1:
            raise ValueError("warmup must be >= 1")
        if int(stride) < 1:
            raise ValueError("stride must be >= 1")
        if int(purge_bars) < 0:
            raise ValueError("purge_bars must be >= 0")
        if int(embargo_days) < 0:
            raise ValueError("embargo_days must be >= 0")
        warmup, stride = int(warmup), int(stride)
        purge_bars, embargo_days = int(purge_bars), int(embargo_days)

        n_1h = len(candles_1h or [])
        if n_1h < (warmup + folds + h_candles):
            raise ValueError(
                f"Insufficient 1h candles: {n_1h} provided, need at least "
                f"warmup({warmup}) + folds({folds}) + H({h_candles})"
            )

        try:
            from app.ml.sessions import classify_window as _classify_window
        except Exception:
            _classify_window = None  # type: ignore[assignment]

        # Local baselines share identical settlement (no peeking).
        try:
            from app.research.validation.baseline import (
                BuyAndHoldBaseline as _BH,
                NaiveMomentumBaseline as _NM,
            )
        except Exception:  # pragma: no cover - baseline module always present
            _BH = None  # type: ignore[assignment]
            _NM = None  # type: ignore[assignment]
        _naive = _NM() if _NM is not None else None
        _bh = _BH() if _BH is not None else None

        if isinstance(cost_model, str):
            costs_version = cost_model
        elif isinstance(cost_model, dict):
            costs_version = str(cost_model.get("costs_version", cost_model.get("version", "base")))
        elif cost_model is None:
            costs_version = "base"
        else:
            costs_version = str(cost_model)

        embargo_bars = int(embargo_days * _WF_BARS_PER_DAY)
        gap_bars = int(purge_bars + embargo_bars)

        candidates: List[int] = list(range(warmup, n_1h - h_candles, stride))
        if len(candidates) < folds:
            raise ValueError(
                f"Not enough candidate decision points ({len(candidates)}) "
                f"for {folds} folds; provide more 1h candles or lower warmup"
            )
        chunks = _wf_split_sequential(candidates, folds)

        fold_reports: List[Dict[str, Any]] = []
        all_records: List[Dict[str, Any]] = []
        n_unsettleable = 0
        unsettleable_reasons: Dict[str, int] = {}

        logger.info(
            "walkforward_start",
            instrument=instrument,
            candles_1h=n_1h,
            candles_1m=len(candles_1m or []),
            folds=folds,
            warmup=warmup,
            stride=stride,
            purge_bars=purge_bars,
            embargo_days=embargo_days,
            gap_bars=gap_bars,
            target_spec=target_spec_version,
        )

        for fi, test_indices in enumerate(chunks):
            if not test_indices:
                continue
            test_start, test_end = int(min(test_indices)), int(max(test_indices))
            train_indices: List[int] = [c for c in candidates if int(c) <= test_start - gap_bars - 1]
            train_start = int(min(train_indices)) if train_indices else None
            train_end = int(max(train_indices)) if train_indices else None

            fold_records: List[Dict[str, Any]] = []
            fold_unsettleable = 0

            for t in list(test_indices):  # chronological, no shuffle
                t = int(t)
                past = (candles_1h or [])[: t + 1]
                forward = (candles_1h or [])[t + 1: t + 1 + h_candles]
                if not forward or len(forward) < h_candles:
                    continue
                dec = (candles_1h or [])[t]
                dt = _wf_parse_ts_utc((dec or {}).get("timestamp"))

                settleable = True
                reason = "same-regular-session"
                if _classify_window is not None and dt is not None:
                    try:
                        res = _classify_window(instrument, dt, h_minutes)
                        settleable = bool((res or {}).get("settleable", True))
                        reason = str((res or {}).get("reason", "unknown") or "unknown")
                    except Exception as e:
                        settleable = True
                        reason = f"settle-check-failed-fallback-settleable:{e}"
                if not settleable:
                    n_unsettleable += 1
                    fold_unsettleable += 1
                    unsettleable_reasons[reason] = int(unsettleable_reasons.get(reason, 0)) + 1
                    continue

                # ---- prediction (PIT: past only) ----
                direction = Direction.NEUTRAL
                confidence = 0.5
                probs = {"bullish": 1.0 / 3.0, "neutral": 1.0 / 3.0, "bearish": 1.0 / 3.0}
                score = 0.0
                if label_fn is not None:
                    try:
                        try:
                            out = label_fn(past, options_ctx)
                        except TypeError:
                            out = label_fn(past)
                    except Exception as e:
                        logger.warning("walkforward_label_failed", fold=fi, t=t, error=str(e))
                        continue
                    try:
                        import inspect as _inspect

                        if _inspect.isawaitable(out):
                            raise ValueError(
                                "label_fn must be sync for run_walkforward "
                                "(got awaitable; wrap with asyncio.run outside)"
                            )
                    except ValueError:
                        raise
                    except Exception:
                        pass
                    try:
                        if isinstance(out, Direction):
                            direction = out
                            confidence = 0.6 if direction != Direction.NEUTRAL else 0.34
                            probs = _wf_probs_for_direction(direction)
                            score = 50.0 if direction == Direction.BULLISH else (
                                -50.0 if direction == Direction.BEARISH else 0.0)
                        elif isinstance(out, dict):
                            raw_d = out.get("direction", Direction.NEUTRAL)
                            if isinstance(raw_d, Direction):
                                direction = raw_d
                            else:
                                try:
                                    direction = Direction(str(raw_d).upper())
                                except Exception:
                                    direction = Direction.NEUTRAL
                            try:
                                confidence = float(out.get("confidence", 0.5))
                            except Exception:
                                confidence = 0.5
                            confidence = min(1.0, max(0.0, confidence))
                            probs = _wf_normalize_probs(out.get("probabilities"))
                            try:
                                score = float(out.get("score", 0.0))
                            except Exception:
                                score = 0.0
                            score = min(100.0, max(-100.0, score))
                        else:
                            try:
                                direction = Direction(str(out).upper())
                            except Exception:
                                direction = Direction.NEUTRAL
                            confidence = 0.6 if direction != Direction.NEUTRAL else 0.34
                            probs = _wf_probs_for_direction(direction)
                    except Exception as e:
                        logger.warning("walkforward_label_parse_failed", fold=fi, t=t, error=str(e))
                        continue
                else:
                    try:
                        direction = _naive.predict(past) if _naive is not None else Direction.NEUTRAL
                    except Exception:
                        direction = Direction.NEUTRAL
                    if direction not in (Direction.BULLISH, Direction.BEARISH, Direction.NEUTRAL):
                        direction = Direction.NEUTRAL
                    confidence = 0.6 if direction != Direction.NEUTRAL else 0.34
                    probs = _wf_probs_for_direction(direction)
                    score = 50.0 if direction == Direction.BULLISH else (
                        -50.0 if direction == Direction.BEARISH else 0.0)

                try:
                    curr_price = float((dec or {})["close"])
                except Exception:
                    continue
                if dt is None:
                    dt = datetime.now(timezone.utc)

                pred = ResearchPrediction(
                    prediction_id=f"wf_f{fi}_{uuid.uuid4().hex[:8]}",
                    indicator_id="walkforward_1h_v23",
                    indicator_version="v23",
                    instrument=instrument,
                    timeframe="1h",
                    timestamp=dt,
                    current_price=curr_price,
                    direction=direction,
                    score=float(score),
                    confidence=float(confidence),
                    component_values={"probabilities": dict(probs)},
                    forecast_horizon=ForecastHorizon.HORIZON_1H,
                    horizon_candles=h_candles,
                )
                try:
                    outcome = OutcomeMeasurer.evaluate_forward_candles(pred, forward)
                except Exception as e:
                    logger.warning("walkforward_outcome_failed", fold=fi, t=t, error=str(e))
                    continue

                # Identical-settlement baselines (no peeking: past only).
                try:
                    base_naive_dir = _naive.predict(past) if _naive is not None else Direction.NEUTRAL
                except Exception:
                    base_naive_dir = Direction.NEUTRAL
                try:
                    base_bh_dir = _bh.predict(past) if _bh is not None else Direction.BULLISH
                except Exception:
                    base_bh_dir = Direction.BULLISH

                try:
                    p_closes = [float(c["close"]) for c in past]
                    p_highs = [float(c["high"]) for c in past]
                    p_lows = [float(c["low"]) for c in past]
                    regime = determine_market_regime(p_closes, p_highs, p_lows, curr_price)
                    regime_s = getattr(regime, "value", str(regime))
                except Exception:
                    regime_s = "UNKNOWN"
                try:
                    sess = classify_session_ist(dt)
                    session_s = getattr(sess, "value", str(sess))
                except Exception:
                    session_s = "UNKNOWN"

                actual_class = _wf_direction_to_class(outcome.actual_direction)
                pred_class = _wf_direction_to_class(direction)
                rec = {
                    "fold": fi,
                    "t": t,
                    "direction": getattr(direction, "value", str(direction)),
                    "pred_class": pred_class,
                    "actual_class": actual_class,
                    "confidence": float(confidence),
                    "probs": {
                        "bullish": float(probs.get("bullish", 0.0)),
                        "neutral": float(probs.get("neutral", 0.0)),
                        "bearish": float(probs.get("bearish", 0.0)),
                        "p_max": float(max(
                            float(probs.get("bullish", 0.0)),
                            float(probs.get("neutral", 0.0)),
                            float(probs.get("bearish", 0.0)),
                        )),
                    },
                    "is_correct": bool(outcome.is_correct),
                    "mfe": float(outcome.mfe),
                    "mae": float(outcome.mae),
                    "target_hit": bool(outcome.target_hit),
                    "stop_hit": bool(outcome.stop_hit),
                    "time_to_target_sec": outcome.time_to_target_sec,
                    "traded": bool(direction != Direction.NEUTRAL),
                    "baseline_naive_correct": bool(base_naive_dir == outcome.actual_direction),
                    "baseline_buyhold_correct": bool(base_bh_dir == outcome.actual_direction),
                    "regime": str(regime_s),
                    "session": str(session_s),
                }
                fold_records.append(rec)
                all_records.append(rec)

            metrics = cls._summarize_records(fold_records)
            fold_reports.append({
                "fold": fi,
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "train_size": len(train_indices),
                "test_size": len(test_indices),
                "n_settleable": metrics.get("n", 0),
                "n_unsettleable": int(fold_unsettleable),
                "train_indices": [int(x) for x in train_indices],
                "test_indices": [int(x) for x in test_indices],
                "metrics": metrics,
            })

        pooled = cls._summarize_records(all_records)

        def _group(records: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for r in records:
                g = str(r.get(key, "UNKNOWN") or "UNKNOWN")
                groups.setdefault(g, []).append(r)
            return {g: cls._summarize_records(v) for g, v in sorted(groups.items())}

        by_instrument = {str(instrument): dict(pooled)}
        by_regime = _group(all_records, "regime")
        by_session = _group(all_records, "session")
        by_direction = _group(all_records, "direction")

        purge_ok = True
        for f in fold_reports:
            tri = f.get("train_indices") or []
            tei = f.get("test_indices") or []
            if tri and tei:
                if set(tri) & set(tei):
                    purge_ok = False
                if int(min(tei)) - int(max(tri)) <= int(purge_bars):
                    purge_ok = False

        report: Dict[str, Any] = {
            "instrument": instrument,
            "horizon": "1h",
            "horizon_minutes": h_minutes,
            "horizon_candles": h_candles,
            "target_spec_version": target_spec_version,
            "costs_version": costs_version,
            "params": {
                "warmup": warmup,
                "stride": stride,
                "folds": folds,
                "purge_bars": purge_bars,
                "embargo_days": embargo_days,
                "embargo_bars": embargo_bars,
                "gap_bars": gap_bars,
                "horizon_minutes": h_minutes,
                "horizon_candles": h_candles,
                "n_1h": n_1h,
                "n_1m": len(candles_1m or []),
                "costs_version": costs_version,
                "target_spec_version": target_spec_version,
            },
            "total_candidates": len(candidates),
            "n_settleable": pooled.get("n", 0),
            "n_unsettleable": int(n_unsettleable),
            "unsettleable_reasons": dict(unsettleable_reasons),
            "folds": fold_reports,
            "pooled": pooled,
            "by_instrument": by_instrument,
            "by_regime": by_regime,
            "by_session": by_session,
            "by_direction": by_direction,
            "leakage_audit": {
                "chronological": True,
                "no_shuffle": True,
                "purge_respected": bool(purge_ok),
                "gap_bars": gap_bars,
                "purge_bars": purge_bars,
                "embargo_days": embargo_days,
                "embargo_bars": embargo_bars,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "walkforward_completed",
            instrument=instrument,
            pooled_n=pooled.get("n", 0),
            unsettleable=int(n_unsettleable),
            hit_rate=pooled.get("hit_rate", 0.0),
            purge_ok=bool(purge_ok),
        )
        return report

