"""
Candidate Enrichment Module for Quantitative Scanning Pipeline (Phase 3)
Handles:
  - Timeline validation (PIT)
  - AI Advisory integration
  - Machine Learning directional prediction
  - Institutional flow overlay & composite calculation
  - Confluence fusion & overall confidence scoring
  - Signal Explainability bundle assembly
"""
from __future__ import annotations

import time
from datetime import datetime as _dt, timezone as _tz
from typing import Any
import structlog

from app.signals.confluence import ARMED_THRESHOLD, DEFAULT_WEIGHTS, confluence_engine
from app.signals.explain import build_signal_explain
from app.signals.strategies.base import SignalCandidate
from app.signals.validation.pit_validator import pit_validator

logger = structlog.get_logger()


async def enrich_candidate(
    cand: SignalCandidate,
    active_candles: list[dict],
    fno_data: dict[str, Any],
    fno_is_degraded: bool,
    risk_decision: Any,
    overlay: Any,
    rejected_gates: list[str],
) -> tuple[float, dict[str, Any], Any, str]:
    """
    Runs multi-domain intelligence enrichment and returns:
    (fused_score, inst_overlay, explain_bundle, fsm_init_state).
    """
    # 1. AI Advisory
    ai_advice = None
    try:
        c_snap = getattr(cand, "context_snapshot", {}) or {}
        ai_snapshot = {
            "regime": c_snap.get("regime") or ("RANGE" if cand.regime_score in (70.0, 85.0) else "TREND"),
            "fno": c_snap.get("fno", {}),
            "mtf": c_snap.get("mtf", {}),
            "indicators": c_snap.get("indicators") or {"volatility": {"atr": float(cand.risk_points or 20.0)}},
            "spot_price": float(c_snap.get("spot_price") or cand.spot_price),
            "vwap": float(c_snap.get("vwap") or cand.spot_price),
            "volume_ma_20": c_snap.get("volume_ma_20"),
        }
        ai_advice = await confluence_engine.fetch_ai_advisory(cand, ai_snapshot)
        cand.ai_score = ai_advice.score
        if ai_advice.rationale:
            cand.rationale.append(f"AI: {ai_advice.rationale}")
    except Exception as ai_err:
        logger.debug("ai_advisory_fetch_skipped", error=str(ai_err))

    # 2. PIT Timeline Validation
    try:
        _pit = pit_validator.validate_timeline(
            decision_timestamp_ms=int(time.time() * 1000),
            candles=active_candles if isinstance(active_candles, list) else [],
            fno_data=fno_data if isinstance(fno_data, dict) else None,
            quote_timestamp_ms=None,
        )
        if not _pit.passed:
            rejected_gates.append(f"{cand.strategy}:PIT_LOOKAHEAD_{';'.join(_pit.violations)[:120]}")
            logger.warning("candidate_rejected_pit", strategy=cand.strategy, violations=_pit.violations)
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

    # 4. Institutional Flow Overlay
    inst_overlay: dict[str, Any] = {"applied": False, "delta": 0.0, "reasons": ["disabled"], "downgrade_to_validated": False}
    try:
        from app.institutional.flow_store import flow_store
        from app.signals.institutional_overlay import compute_institutional_adjustment

        _flow = flow_store.as_of(_dt.now(_tz.utc))
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
            _pcr = float(_fno.get("pcr", 1.0) or 1.0)
            if _pcr >= 1.2:
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

    # 6. Signal Explain Bundle
    _explain = None
    try:
        _c_snap = getattr(cand, "context_snapshot", {}) or {}
        _ind = _c_snap.get("indicators", {}) or {}
        _fno = _c_snap.get("fno", {}) or {}
        _mtf = _c_snap.get("mtf", {}) or {}
        _inputs_snapshot = {
            "spot": float(_c_snap.get("spot_price") or cand.spot_price),
            "vwap": float(_c_snap.get("vwap") or cand.spot_price),
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
            _inputs_snapshot["volume_ratio"] = float(_ind.get("volume_ratio") or (_ind.get("volume") or {}).get("ratio") or 1.0)
        except Exception:
            pass
        try:
            _inputs_snapshot["pcr"] = float(_fno.get("pcr", 1.0))
        except Exception:
            pass
        try:
            _inputs_snapshot["atm_iv"] = float(_fno.get("atm_iv", 14.5))
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

    # Determine initial FSM state
    _divergence_downgrade = bool(isinstance(inst_overlay, dict) and inst_overlay.get("downgrade_to_validated"))
    if _divergence_downgrade:
        try:
            cand.rationale.append(f"Divergence guard: {inst_overlay.get('reasons', ['flow-divergence'])[-1]} — forced VALIDATED")
        except Exception:
            pass
    fsm_init_state = "VALIDATED" if (fno_is_degraded or _divergence_downgrade) else ("ARMED" if fused_score >= ARMED_THRESHOLD else "VALIDATED")

    return fused_score, inst_overlay, _explain, fsm_init_state
