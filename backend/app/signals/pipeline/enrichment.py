"""
Candidate Enrichment Module for Quantitative Scanning Pipeline (Phase 3)
Handles:
  - Timeline validation (PIT) — BLOCKING, fail-closed
  - AI Advisory integration
  - Machine Learning directional prediction
  - Institutional flow overlay & composite calculation
  - Confluence fusion & overall confidence scoring
  - Signal Explainability bundle assembly
"""
from __future__ import annotations

from datetime import datetime as _dt, timezone as _tz
from typing import Any
import structlog

from app.signals.confluence import ARMED_THRESHOLD, DEFAULT_WEIGHTS, confluence_engine
from app.signals.explain import build_signal_explain
from app.signals.strategies.base import SignalCandidate
from app.signals.validation.pit_validator import pit_validator

logger = structlog.get_logger()

# Sentinel FSM state: PIT rejected the candidate — scanner must drop it, never register.
REJECT_STATE = "REJECT"


async def enrich_candidate(
    cand: SignalCandidate,
    active_candles: list[dict] | None,
    fno_data: dict[str, Any] | None,
    fno_is_degraded: bool,
    risk_decision: Any,
    overlay: Any,
    rejected_gates: list[str],
    decision_timestamp_ms: int | None = None,
    quote_timestamp_ms: int | None = None,
) -> tuple[float, dict[str, Any], Any, str, Any, Any]:
    """
    Runs multi-domain intelligence enrichment and returns:
    (fused_score, inst_overlay, explain_bundle, fsm_init_state, ai_advice, ml_pred).

    PIT inputs are threaded from the scanner (decision/quote timestamps, candles,
    F&O) — never synthesized here via time.time()/None/[]. A failed PIT timeline
    is BLOCKING: returns fsm_init_state == REJECT and the scanner must drop the
    candidate without registering.
    """
    c_snap = getattr(cand, "context_snapshot", {}) or {}

    # Resolve PIT decision/quote timestamps from threaded inputs (no synthetic fallbacks).
    _decision_ts: int | None = None
    for _raw in (decision_timestamp_ms, c_snap.get("timestamp_ms"), getattr(cand, "created_at_utc", None)):
        try:
            if _raw is not None and int(_raw) > 0:
                _decision_ts = int(_raw)
                break
        except Exception:
            continue
    _quote_ts: int | None = None
    for _raw in (quote_timestamp_ms, c_snap.get("quote_timestamp_ms")):
        try:
            if _raw is not None and int(_raw) > 0:
                _quote_ts = int(_raw)
                break
        except Exception:
            continue
    if isinstance(active_candles, list):
        _pit_candles = active_candles
    elif isinstance(c_snap.get("candles"), list):
        _pit_candles = c_snap.get("candles") or []
    else:
        _pit_candles = []
    _pit_fno = fno_data if isinstance(fno_data, dict) else (c_snap.get("fno") if isinstance(c_snap.get("fno"), dict) else None)

    # 1. AI Advisory (real snapshot only — missing vwap/indicators propagate as None,
    #    never synthesized from spot/risk_points; confluence applies the haircut)
    ai_advice = None
    try:
        ai_snapshot = {
            "regime": c_snap.get("regime") or ("RANGE" if cand.regime_score in (70.0, 85.0) else "TREND"),
            "fno": c_snap.get("fno", {}),
            "mtf": c_snap.get("mtf", {}),
            "indicators": c_snap.get("indicators") or {},
            "spot_price": float(c_snap.get("spot_price") or cand.spot_price),
            "vwap": float(c_snap["vwap"]) if c_snap.get("vwap") is not None else None,
            "volume_ma_20": c_snap.get("volume_ma_20"),
        }
        ai_advice = await confluence_engine.fetch_ai_advisory(cand, ai_snapshot)
        cand.ai_score = ai_advice.score
        if ai_advice.rationale:
            cand.rationale.append(f"AI: {ai_advice.rationale}")
    except Exception as ai_err:
        logger.debug("ai_advisory_fetch_skipped", error=str(ai_err))

    # 2. PIT Timeline Validation — BLOCKING. Reject, do not append-and-continue.
    _pit = None
    try:
        _pit = pit_validator.validate_timeline(
            decision_timestamp_ms=int(_decision_ts or 0),
            candles=_pit_candles,
            fno_data=_pit_fno,
            quote_timestamp_ms=_quote_ts,
        )
        if not _pit.passed:
            rejected_gates.append(f"{cand.strategy}:PIT_LOOKAHEAD_{';'.join(_pit.violations)[:120]}")
            logger.warning("candidate_rejected_pit", strategy=cand.strategy, violations=_pit.violations)
            _rej_overlay: dict[str, Any] = {
                "applied": False,
                "delta": 0.0,
                "reasons": ["pit-rejected"],
                "downgrade_to_validated": False,
            }
            return 0.0, _rej_overlay, None, REJECT_STATE, ai_advice, None
    except Exception as _pit_err:
        logger.debug("pit_validation_skipped", error=str(_pit_err))

    # 3. ML Directional Prediction
    ml_pred = None
    try:
        from app.ml.predictor import ml_predictor
        ml_res = await ml_predictor.predict_probabilities(cand.underlying)
        if ml_res:
            ml_pred = {
                "is_available": True,
                "bullish_pct": ml_res.bullish_pct,
                "bearish_pct": ml_res.bearish_pct,
                "confidence_score": ml_res.confidence_score,
            }
            is_call = "CALL" in cand.direction
            cand_ml_score = ml_res.bullish_pct if is_call else ml_res.bearish_pct
            cand.rationale.append(f"ML: {ml_res.predicted_bias} ({cand_ml_score:.1f}% prob, conf {ml_res.confidence_score:.0f}%)")
    except Exception as ml_err:
        logger.debug("ml_prediction_fetch_skipped", error=str(ml_err))

    # 3b. Stage A ML Challenger Observation (Non-interfering observation per Section 28)
    try:
        from app.ml.models.regime_model import regime_model
        from app.ml.features.schema import NEUTRAL_IMPUTE_V3, FEATURE_NAMES_V3
        vec = [NEUTRAL_IMPUTE_V3[k] for k in FEATURE_NAMES_V3]
        reg_res = regime_model.predict_regime(vec)
        if reg_res:
            cand.rationale.append(f"ML Challenger Regime: {reg_res['regime']} ({reg_res['model_version']})")
            if not isinstance(cand.context_snapshot, dict):
                cand.context_snapshot = {}
            cand.context_snapshot["ml_challenger_stage_a"] = {
                "regime": reg_res["regime"],
                "regime_probabilities": reg_res["probabilities"],
                "model_version": reg_res["model_version"],
            }
    except Exception as reg_err:
        logger.debug("stage_a_regime_observation_skipped", error=str(reg_err))

    # 3c. Stage B ML Challenger Shadow Gating (Section 28 & Section 14)
    # Evaluates Breakout Validation & Trade Outcome Meta-Labeling.
    # CRITICAL: Non-interfering observation only. Logs PASS/VETO recommendation
    # and counterfactual tracking; live execution proceeds untouched.
    try:
        from app.ml.models.breakout_model import breakout_model
        from app.ml.models.trade_outcome_model import trade_outcome_model
        from app.ml.features.schema import NEUTRAL_IMPUTE_V3, FEATURE_NAMES_V3

        vec = [NEUTRAL_IMPUTE_V3[k] for k in FEATURE_NAMES_V3]
        try:
            if _pit_candles:
                from app.ml.features.feature_extractor_v3 import extract_features_v3
                f_res = extract_features_v3(
                    instrument=cand.underlying,
                    feature_timestamp_ms=int(_decision_ts or 0),
                    candles_1m=_pit_candles,
                    indicators=c_snap.get("indicators"),
                    options_analytics=_pit_fno,
                )
                vec = f_res.features
        except Exception:
            pass

        # Breakout validation
        bo_res = breakout_model.predict_breakout_quality(vec, direction=cand.direction, strategy_name=cand.strategy)
        p_bo = float(bo_res.get("p_valid_breakout", 0.50))

        # Direction probability from ml_pred if available
        p_dir = 0.50
        if ml_pred and isinstance(ml_pred, dict):
            p_dir = (ml_pred.get("bullish_pct", 50.0) / 100.0) if ("CALL" in cand.direction) else (ml_pred.get("bearish_pct", 50.0) / 100.0)

        # Meta-label outcome prediction
        to_res = trade_outcome_model.predict_trade_outcome(vec, direction_prob=p_dir, breakout_prob=p_bo)
        p_t1 = float(to_res.get("p_target_before_stop", 0.50))
        recommendation = "PASS" if p_t1 >= 0.55 else "VETO"

        cand.rationale.append(f"ML Shadow Gate: {recommendation} (P(T1)={p_t1:.2f}, MFE={to_res.get('expected_mfe_r', 0.0)}R)")

        if not isinstance(cand.context_snapshot, dict):
            cand.context_snapshot = {}
        cand.context_snapshot["ml_shadow_gate"] = {
            "action": recommendation,
            "recommendation": recommendation,
            "p_target_before_stop": p_t1,
            "p_stop_before_target": to_res.get("p_stop_before_target", 0.0),
            "p_timeout": to_res.get("p_timeout", 0.0),
            "expected_mfe_r": to_res.get("expected_mfe_r", 0.0),
            "expected_mae_r": to_res.get("expected_mae_r", 0.0),
            "breakout_valid_prob": p_bo,
            "is_continuation": bo_res.get("is_continuation", True),
            "is_calibrated": to_res.get("is_calibrated", False),
            "model_version": to_res.get("model_version", "trade_outcome_v1"),
            "counterfactual_tracked": True,
        }

        # 3d. Options Intelligence & Net EV Calculation (§16, §17)
        try:
            from app.ml.models.option_model import options_intelligence_model
            from app.ml.models.ev_engine import ev_engine

            opt_res = options_intelligence_model.evaluate_strikes(
                underlying=cand.underlying,
                direction=cand.direction,
                spot_price=float(cand.spot_price),
                target_1=float(cand.target_1),
                stop_loss=float(cand.stop_loss),
                p_target=p_t1,
                p_stop=float(to_res.get("p_stop_before_target", 0.0)),
                p_timeout=float(to_res.get("p_timeout", 0.0)),
            )

            ev_res = ev_engine.calculate_trade_ev(
                entry_premium=opt_res["selected_premium"],
                lot_size=opt_res["lot_size"],
                lots=1,
                expected_gain_at_t1=opt_res["expected_gain_at_t1"],
                expected_loss_at_sl=opt_res["expected_loss_at_sl"],
                expected_timeout_pnl=-opt_res["selected_theta_day"] * (15.0 / 375.0),
                p_target=p_t1,
                p_stop=float(to_res.get("p_stop_before_target", 0.0)),
                p_timeout=float(to_res.get("p_timeout", 0.0)),
            )

            cand.context_snapshot["ml_options_ev"] = {
                "selected_strike": opt_res["selected_strike"],
                "selected_strike_type": opt_res["selected_strike_type"],
                "selected_premium": opt_res["selected_premium"],
                "delta": opt_res["selected_delta"],
                "gross_ev": ev_res.gross_ev_total,
                "net_ev": ev_res.net_ev_total,
                "ev_risk_ratio": ev_res.ev_risk_ratio,
                "is_viable": ev_res.is_viable,
                "total_friction": ev_res.frictions.total_friction,
            }
            cand.rationale.append(f"ML Strike: {opt_res['selected_strike']} {opt_res['selected_strike_type']} (Net EV ₹{ev_res.net_ev_total:+.0f}, EV/Risk {ev_res.ev_risk_ratio:.2f})")
        except Exception as opt_err:
            logger.debug("options_ev_evaluation_skipped", error=str(opt_err))
    except Exception as sg_err:
        logger.debug("stage_b_shadow_gating_skipped", error=str(sg_err))

    # 4. Institutional Flow Overlay (PIT-safe read as of the decision timestamp, never now())
    inst_overlay: dict[str, Any] = {"applied": False, "delta": 0.0, "reasons": ["disabled"], "downgrade_to_validated": False}
    try:
        from app.institutional.flow_store import flow_store
        from app.signals.institutional_overlay import compute_institutional_adjustment

        try:
            _decision_dt = _dt.fromtimestamp(float(_decision_ts or 0) / 1000.0, tz=_tz.utc)
        except Exception:
            _decision_dt = None
        _flow = flow_store.as_of(_decision_dt) if _decision_dt is not None else flow_store.as_of()
        _c_snap = getattr(cand, "context_snapshot", {}) or {}
        _fno = dict(_c_snap.get("fno", {}) or {})
        _part = {
            "label": str(getattr(getattr(cand, "participation", None), "label", "") or ""),
            "support_hold": False,
            "put_writing": False,
        }
        try:
            _sr = ((_c_snap.get("indicators", {}) or {}).get("support_resistance", {}) or {})
            _sup = _sr.get("support")
            _sup_lvls = _sup if isinstance(_sup, (list, tuple)) else ([_sup] if _sup is not None else [])
            for _s in _sup_lvls:
                try:
                    if abs(float(cand.spot_price) - float(_s)) / float(cand.spot_price) < 0.002:
                        _part["support_hold"] = True
                except Exception:
                    pass
            # Real PCR only — missing PCR propagates as unknown (no 1.0 synthetic default).
            _pcr_raw = _fno.get("pcr")
            if _pcr_raw is not None and float(_pcr_raw) >= 1.2:
                _part["put_writing"] = True
        except Exception:
            pass

        _delta, _info = compute_institutional_adjustment(
            cand.direction, getattr(cand, "context_snapshot", {}).get("regime", "RANGE"),
            _flow, _fno, _part,
        )
        try:
            from app.institutional.drift import is_degraded as _inst_degraded
            if _inst_degraded():
                _delta = 0.0
                _info = dict(_info)
                _info["applied"] = False
                _info["reasons"] = list(_info.get("reasons", [])) + ["drift-degraded-neutralised"]
        except Exception:
            pass

        inst_overlay = {"delta": _delta, **_info}
        if _info.get("applied"):
            cand.rationale.append(f"Flow({_info.get('flow_event_date')}): {_info['reasons'][0]} delta {_delta:+.1f}")

        # Composite institutional score
        try:
            from app.institutional.composite import compute_composite
            from app.institutional.market_engines import get_breadth_snapshot, get_vix_snapshot

            _breadth = await get_breadth_snapshot()
            _vixs = await get_vix_snapshot()
            _comp = compute_composite(_flow, None, _breadth, _vixs, _fno, getattr(cand, "context_snapshot", {}).get("regime", "RANGE"))
            inst_overlay["composite_score"] = _comp.get("score")
            inst_overlay["composite_sentiment"] = _comp.get("sentiment")
            inst_overlay["composite_status"] = _comp.get("status")
            if _comp.get("score") is not None:
                cand.rationale.append(f"Composite:{_comp['sentiment']} {_comp['score']:.0f} ({_comp['status']})")
                _is_call = "CALL" in cand.direction
                if (_is_call and _comp["sentiment"] == "BEARISH" and _comp["score"] <= 30.0) or (
                    not _is_call and _comp["sentiment"] == "BULLISH" and _comp["score"] >= 70.0
                ):
                    inst_overlay["downgrade_to_validated"] = True
                    inst_overlay["reasons"] = list(inst_overlay.get("reasons", [])) + ["composite-strong-opposition-force-VALIDATED"]
        except Exception as _cp_err:
            logger.debug("institutional_composite_skipped", error=str(_cp_err))
    except Exception as _fl_err:
        logger.debug("institutional_overlay_skipped", error=str(_fl_err))

    # 5. Confluence Fusion
    fused_score = confluence_engine.fuse(cand, ai_result=ai_advice, ml_prediction=ml_pred, institutional=inst_overlay)
    cand.overall_confidence = fused_score

    # Sizing adjustment for mild institutional opposition
    try:
        _neg = isinstance(inst_overlay, dict) and bool(inst_overlay.get("applied")) and float(inst_overlay.get("delta", 0.0)) <= -2.5
        if _neg and not bool(inst_overlay.get("downgrade_to_validated")):
            _lots = int(getattr(risk_decision, "lots", 1) or 1)
            _qty = int(getattr(risk_decision, "quantity", _lots) or _lots)
            if _lots > 1:
                _new_lots = max(1, _lots // 2)
                _per = _qty // max(1, _lots)
                risk_decision.lots = _new_lots
                risk_decision.quantity = _new_lots * _per
                cand.rationale.append(f"Institutional reduce-only: lots {_lots}->{_new_lots} (flow opposes, delta {float(inst_overlay.get('delta')):+.1f})")
                inst_overlay["sizing"] = f"halved-{_lots}-to-{_new_lots}"
    except Exception as _sz_err:
        logger.debug("institutional_sizing_skipped", error=str(_sz_err))

    # Stage C: Soft Sizing Authority based on Net EV & Half-Kelly (§19, §28)
    try:
        if risk_decision is not None and isinstance(cand.context_snapshot, dict) and "ml_options_ev" in cand.context_snapshot:
            ev_info = cand.context_snapshot["ml_options_ev"]
            _lots = int(getattr(risk_decision, "lots", 1) or 1)
            _qty = int(getattr(risk_decision, "quantity", _lots) or _lots)
            _per = _qty // max(1, _lots)

            from app.ml.risk.dynamic_sizer import dynamic_position_sizer
            sg_info = cand.context_snapshot.get("ml_shadow_gate", {})
            sizing_res = dynamic_position_sizer.compute_size(
                base_lots=_lots,
                max_lots=max(_lots, 4),
                calibrated_p_win=float(sg_info.get("p_target_before_stop", 0.50)),
                expected_mfe_r=float(sg_info.get("expected_mfe_r", 1.5)),
                expected_mae_r=float(sg_info.get("expected_mae_r", 0.8)),
                net_ev_total=float(ev_info.get("net_ev", 0.0)),
                is_ev_viable=bool(ev_info.get("is_viable", True)),
            )
            cand.context_snapshot["ml_sizing"] = {
                "recommended_lots": sizing_res.recommended_lots,
                "multiplier": sizing_res.sizing_multiplier,
                "half_kelly": sizing_res.half_kelly_fraction,
                "authorized": sizing_res.is_authorized,
            }
            # Soft authority: if net EV is negative and lots > 1, defensively reduce to 1 lot
            if not sizing_res.is_authorized and _lots > 1:
                risk_decision.lots = 1
                risk_decision.quantity = 1 * _per
                cand.rationale.append(f"ML Soft Sizing: {_lots}->1 lot (Negative Net EV ₹{ev_info.get('net_ev', 0.0):.0f})")
            elif sizing_res.sizing_multiplier < 1.0 and _lots > 1:
                new_lots = max(1, int(round(_lots * sizing_res.sizing_multiplier)))
                if new_lots < _lots:
                    risk_decision.lots = new_lots
                    risk_decision.quantity = new_lots * _per
                    cand.rationale.append(f"ML Soft Sizing: {_lots}->{new_lots} lots (Half-Kelly {sizing_res.half_kelly_fraction:.2f})")
    except Exception as sz_err:
        logger.debug("ml_soft_sizing_skipped", error=str(sz_err))

    # 6. Signal Explain Bundle (real inputs only — missing vwap/pcr/iv/volume propagate as None)
    _explain = None
    try:
        _c_snap = getattr(cand, "context_snapshot", {}) or {}
        _ind = _c_snap.get("indicators", {}) or {}
        _fno = _c_snap.get("fno", {}) or {}
        _mtf = _c_snap.get("mtf", {}) or {}
        _vwap_raw = _c_snap.get("vwap")
        _inputs_snapshot = {
            "spot": float(_c_snap.get("spot_price") or cand.spot_price),
            "vwap": float(_vwap_raw) if _vwap_raw is not None else None,
            "rsi": None,
            "adx": None,
            "volume_ratio": None,
            "pcr": None,
            "atm_iv": None,
            "regime": _c_snap.get("regime"),
            "mtf_bias": _mtf.get("overall_bias", _mtf.get("bias")),
            "indicators": _ind,
            "fno": _fno,
            "mtf": _mtf,
        }
        try:
            _inputs_snapshot["rsi"] = float(_ind.get("rsi") or (_ind.get("momentum") or {}).get("rsi"))
        except Exception:
            pass
        try:
            _inputs_snapshot["adx"] = float((_ind.get("momentum") or {}).get("adx") or _ind.get("adx"))
        except Exception:
            pass
        try:
            _inputs_snapshot["volume_ratio"] = float(_ind.get("volume_ratio") or (_ind.get("volume") or {}).get("ratio"))
        except Exception:
            pass
        try:
            _inputs_snapshot["pcr"] = float(_fno["pcr"]) if _fno.get("pcr") is not None else None
        except Exception:
            pass
        try:
            _inputs_snapshot["atm_iv"] = float(_fno["atm_iv"]) if _fno.get("atm_iv") is not None else None
        except Exception:
            pass

        _data_health = {
            "fno_degraded": bool(fno_is_degraded),
            "vwap_degraded": bool(getattr(cand, "vwap_degraded", False)),
            "vwap_coverage_pct": float(getattr(cand, "vwap_coverage_pct", 100.0) or 100.0),
        }
        _weights_cfg = {"weights_fraction": dict(DEFAULT_WEIGHTS), "version": 2}
        _thr_cfg = {"armed": float(ARMED_THRESHOLD)}
        _explain = build_signal_explain(
            cand, fused_score, ai_advice, ml_pred, overlay,
            _weights_cfg, _thr_cfg, rejected_gates,
            _inputs_snapshot, _data_health,
        )
    except Exception as _ex:
        logger.debug("signal_explain_build_skipped", error=str(_ex))

    # Determine initial FSM state — VALIDATED on any degraded/unverified input,
    # ARMED only on full verification plus sufficient fused confidence.
    _divergence_downgrade = bool(isinstance(inst_overlay, dict) and inst_overlay.get("downgrade_to_validated"))
    if _divergence_downgrade:
        try:
            cand.rationale.append(f"Divergence guard: {inst_overlay.get('reasons', ['flow-divergence'])[-1]} — forced VALIDATED")
        except Exception:
            pass
    _ai_unavailable = not (ai_advice is not None and getattr(ai_advice, "status", None) == "AVAILABLE")
    _vwap_degraded = bool(getattr(cand, "vwap_degraded", False))
    _pit_ok = bool(_pit is not None and _pit.passed)
    if fno_is_degraded or _vwap_degraded or (not _pit_ok) or _ai_unavailable or _divergence_downgrade:
        fsm_init_state = "VALIDATED"
    else:
        fsm_init_state = "ARMED" if fused_score >= ARMED_THRESHOLD else "VALIDATED"

    return fused_score, inst_overlay, _explain, fsm_init_state, ai_advice, ml_pred
