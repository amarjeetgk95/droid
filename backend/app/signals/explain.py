"""Immutable forecast explainability bundles for signals + research forecasts.

Pure functions only: no I/O, no imports from app modules (to avoid cycles),
never throw — every helper degrades gracefully on None / malformed input.
"""
from __future__ import annotations

from typing import Any

STRATEGY_RULES: dict[str, str] = {
    "BREAKOUT": "Buy strength when price breaks above resistance with strong volume.",
    "MEAN_REVERSION": "Fade the extreme: buy oversold dips, sell overbought rallies back to the average.",
    "TREND_PULLBACK": "Join the trend after a small pullback, not after a vertical run.",
    "VWAP_SCALP": "Quick trade back toward VWAP (the day's fair price) when price stretches away.",
    "MICRO_MOMENTUM": "Ride a fresh 1-minute burst of momentum while buyers stay in control.",
    "EMA_RIBBON": "Trade in the direction the stacked moving averages point, like lanes on a highway.",
    "GAMMA_SQUEEZE": "Dealers hedging can push price further once a big options wall breaks.",
    "GAMMA_SPIKE": "A sudden burst in options activity often kicks off a fast short move.",
    "ORB": "Trade the break of the first few minutes' high/low range once direction is chosen.",
}

WEIGHTS_VERSION_DEFAULT = 2
THRESHOLD_ARMED_DEFAULT = 70.0


def _num(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or isinstance(v, bool):
            return default
        f = float(v)
        # guard NaN / inf
        if f != f or f in (float("inf"), float("-inf")):
            return default
        return f
    except Exception:
        return default


def _str(v: Any, default: str = "") -> str:
    try:
        if v is None:
            return default
        s = str(v)
        return s if s else default
    except Exception:
        return default


def _get(d: Any, *keys: str, default: Any = None) -> Any:
    """Nested-safe dict getter: _get(d, 'a', 'b') == d['a']['b'] or default."""
    try:
        cur = d
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k, default)
            if cur is None:
                return default
        return cur
    except Exception:
        return default


def _extract_rsi(indicators: Any) -> float | None:
    if not isinstance(indicators, dict):
        return None
    for v in (
        indicators.get("rsi"),
        _get(indicators, "momentum", "rsi"),
        _get(indicators, "momentum", "rsi_14"),
        indicators.get("rsi_14"),
    ):
        n = _num(v)
        if n is not None:
            return n
    return None


def _extract_adx(indicators: Any) -> float | None:
    if not isinstance(indicators, dict):
        return None
    for v in (
        indicators.get("adx"),
        _get(indicators, "momentum", "adx"),
        _get(indicators, "trend", "adx"),
        indicators.get("adx_14"),
    ):
        n = _num(v)
        if n is not None:
            return n
    return None


def _extract_vol_ratio(indicators: Any) -> float | None:
    if not isinstance(indicators, dict):
        return None
    for v in (
        indicators.get("volume_ratio"),
        _get(indicators, "volume", "ratio"),
        _get(indicators, "volume", "volume_ratio"),
        indicators.get("rvol"),
    ):
        n = _num(v)
        if n is not None:
            return n
    return None


def layman_for_indicators(indicators: dict, regime: str, vwap: Any, spot: Any) -> list[str]:
    """Deterministic plain-English bullets for technical indicators (max 3-5)."""
    try:
        bullets: list[str] = []
        indicators = indicators if isinstance(indicators, dict) else {}
        regime_s = _str(regime, "RANGE").upper() if regime else "RANGE"
        rsi = _extract_rsi(indicators)
        adx = _extract_adx(indicators)
        vol = _extract_vol_ratio(indicators)
        spot_f = _num(spot)
        vwap_f = _num(vwap)

        if rsi is not None:
            if rsi >= 70:
                bullets.append(f"RSI {rsi:.0f} — overheated, buyers may be exhausted")
            elif rsi > 60:
                bullets.append(f"RSI {rsi:.0f} — buyers strong but getting stretched")
            elif rsi >= 40:
                bullets.append(f"RSI {rsi:.0f} — balanced, no side in control")
            elif rsi >= 30:
                bullets.append(f"RSI {rsi:.0f} — sellers pressing, nearing washed-out")
            else:
                bullets.append(f"RSI {rsi:.0f} — washed out, sellers may be exhausted")
        if adx is not None:
            if adx >= 25:
                bullets.append(f"ADX {adx:.0f} — strong trend, follow-through more likely")
            elif adx >= 20:
                bullets.append(f"ADX {adx:.0f} — trend forming but not decisive yet")
            else:
                bullets.append(f"ADX {adx:.0f} — choppy market, expect whipsaws")
        if spot_f is not None and vwap_f is not None and vwap_f > 0:
            pct = (spot_f - vwap_f) / vwap_f * 100.0
            if pct > 0.3:
                bullets.append(f"Price above VWAP ({pct:+.2f}%) — buyers paying above fair value")
            elif pct < -0.3:
                bullets.append(f"Price below VWAP ({pct:+.2f}%) — sellers pushing below fair value")
            else:
                bullets.append("Price near VWAP — trading at the day's fair price")
        if vol is not None:
            if vol >= 1.4:
                bullets.append(f"Volume {vol:.1f}x normal — strong participation behind the move")
            elif vol >= 1.0:
                bullets.append(f"Volume {vol:.1f}x normal — average participation")
            else:
                bullets.append(f"Volume {vol:.1f}x normal — thin participation, move is fragile")
        if not bullets:
            bullets.append(f"Market regime {regime_s} — waiting for a clearer edge")
        return bullets[:5]
    except Exception:
        try:
            return [f"Market regime {_str(regime, 'RANGE')} — indicators unavailable"]
        except Exception:
            return ["Indicators unavailable"]


def layman_for_fno(fno: dict) -> list[str]:
    """Deterministic plain-English bullets for F&O positioning."""
    try:
        bullets: list[str] = []
        fno = fno if isinstance(fno, dict) else {}
        pcr = _num(fno.get("pcr", fno.get("pcr_oi")), None)
        if pcr is not None:
            if pcr >= 1.2:
                bullets.append(f"PCR {pcr:.2f} — options crowd leaning bullish")
            elif pcr <= 0.8:
                bullets.append(f"PCR {pcr:.2f} — options crowd leaning bearish")
            else:
                bullets.append(f"PCR {pcr:.2f} — options positioning neutral")
        atm_iv = _num(fno.get("atm_iv", fno.get("iv")), None)
        if atm_iv is not None:
            if atm_iv >= 20:
                bullets.append(f"ATM IV {atm_iv:.1f}% — options expensive, big move expected")
            elif atm_iv >= 12:
                bullets.append(f"ATM IV {atm_iv:.1f}% — normal option pricing")
            else:
                bullets.append(f"ATM IV {atm_iv:.1f}% — options cheap, calm market expected")
        max_pain = _num(fno.get("max_pain"), None)
        if max_pain is not None and max_pain > 0:
            bullets.append(f"Max pain {max_pain:,.0f} — price often drifts toward this level")
        if not bullets:
            bullets.append("F&O positioning unavailable — trading without options confirmation")
        return bullets[:4]
    except Exception:
        return ["F&O positioning unavailable"]


def _change_mind_bullets(direction: str, regime: str) -> list[str]:
    try:
        d = _str(direction, "").upper()
        r = _str(regime, "RANGE").upper()
        is_call = "CALL" in d or "BULL" in d or "LONG" in d
        if is_call:
            out = [
                "Price loses VWAP and holds below it — buyers have given up control",
                "RSI rolls under 40 with rising volume — momentum has flipped to sellers",
            ]
        elif "PUT" in d or "BEAR" in d or "SHORT" in d:
            out = [
                "Price reclaims VWAP and holds above it — sellers have lost control",
                "RSI pushes back above 60 with strong volume — buyers are back in charge",
            ]
        else:
            out = [
                "A clean break of the day's range with strong volume — a new trend is starting",
                "PCR swings hard to one side — options crowd picking a direction",
            ]
        if "TREND" in r:
            out.append("Trend structure breaks (lower high for longs, higher low for shorts)")
        elif "EVENT" in r or "VOL" in r:
            out.append("A scheduled event or volatility shock reprices the market")
        else:
            out = out[:2] + ["Volume dries up and price goes flat — the edge has faded"]
        return out[:3]
    except Exception:
        return ["Price action reverses with strong volume — the setup is invalid"]


def _safe_score(v: Any) -> float | None:
    n = _num(v)
    if n is None:
        return None
    try:
        return round(max(0.0, min(100.0, n)), 1)
    except Exception:
        return None


def build_signal_explain(
    candidate: Any,
    fused_score: Any,
    ai_advice: Any,
    ml_pred: Any,
    overlay: Any,
    weights: Any,
    thresholds: Any,
    rejected_gates: Any,
    inputs_snapshot: Any,
    data_health: Any,
) -> dict:
    """Build an immutable explain bundle for one signal. Pure, never throws."""
    try:
        weights = weights if isinstance(weights, dict) else {}
        thresholds = thresholds if isinstance(thresholds, dict) else {}
        inputs_snapshot = dict(inputs_snapshot) if isinstance(inputs_snapshot, dict) else {}
        data_health = dict(data_health) if isinstance(data_health, dict) else {}
        rejected = list(rejected_gates) if isinstance(rejected_gates, (list, tuple)) else []

        def _cand_attr(*names: str, default: Any = None) -> Any:
            for n in names:
                try:
                    if isinstance(candidate, dict):
                        if n in candidate:
                            return candidate[n]
                    else:
                        v = getattr(candidate, n, None)
                        if v is not None:
                            return v
                except Exception:
                    continue
            return default

        strategy = _str(_cand_attr("strategy"), "UNKNOWN").upper()
        direction = _str(_cand_attr("direction"), "UNKNOWN").upper()
        regime = _str(inputs_snapshot.get("regime") or _cand_attr("regime_at_confirmation", "regime"), "RANGE")
        if not regime or regime == "None":
            regime = "RANGE"

        fused = _num(fused_score, 50.0) or 50.0
        try:
            fused = round(max(15.0, min(98.0, fused)), 1)
        except Exception:
            fused = 50.0

        armed_thr = _num(thresholds.get("armed"), THRESHOLD_ARMED_DEFAULT) or THRESHOLD_ARMED_DEFAULT
        weights_version = weights.get("version", WEIGHTS_VERSION_DEFAULT)
        try:
            weights_version = int(weights_version)
        except Exception:
            weights_version = WEIGHTS_VERSION_DEFAULT
        wf = weights.get("weights_fraction", weights) if isinstance(weights, dict) else {}

        def _w(key: str, default: float) -> float:
            n = _num(wf.get(key), default)
            return float(n) if n is not None else default

        w_tech, w_mtf, w_fno, w_reg, w_ai = (
            _w("technical", 0.40),
            _w("mtf", 0.20),
            _w("fno", 0.15),
            _w("regime", 0.10),
            _w("ai", 0.10),
        )
        w_ml = _w("ml", _w("ml_max", 0.07))

        # Scores
        s_tech = _safe_score(_cand_attr("technical_score"))
        s_mtf = _safe_score(_cand_attr("mtf_score"))
        s_fno = _safe_score(_cand_attr("fno_score"))
        s_reg = _safe_score(_cand_attr("regime_score"))
        s_ai: float | None = None
        ai_status = "UNAVAILABLE"
        try:
            if ai_advice is not None:
                if isinstance(ai_advice, dict):
                    ai_status = _str(ai_advice.get("status"), "UNAVAILABLE").upper()
                    s_ai = _safe_score(ai_advice.get("score"))
                else:
                    ai_status = _str(getattr(ai_advice, "status", "UNAVAILABLE"), "UNAVAILABLE").upper()
                    s_ai = _safe_score(getattr(ai_advice, "score", None))
        except Exception:
            s_ai = None
        s_ml: float | None = None
        ml_avail = False
        try:
            if isinstance(ml_pred, dict) and ml_pred.get("is_available"):
                ml_avail = True
                key = "bullish_pct" if "CALL" in direction else "bearish_pct"
                s_ml = _safe_score(ml_pred.get(key, ml_pred.get("confidence_score")))
        except Exception:
            s_ml = None

        def _pts(score: float | None, w: float) -> float:
            if score is None:
                return 0.0
            try:
                return round(score * w, 1)
            except Exception:
                return 0.0

        maths = [
            {"domain": "technical", "score": s_tech, "weight": w_tech, "points": _pts(s_tech, w_tech), "label": "Chart patterns & indicators"},
            {"domain": "mtf", "score": s_mtf, "weight": w_mtf, "points": _pts(s_mtf, w_mtf), "label": "Multi-timeframe alignment"},
            {"domain": "fno", "score": s_fno, "weight": w_fno, "points": _pts(s_fno, w_fno), "label": "Options positioning (PCR, IV)"},
            {"domain": "regime", "score": s_reg, "weight": w_reg, "points": _pts(s_reg, w_reg), "label": "Market regime fit"},
            {
                "domain": "ai",
                "score": s_ai,
                "weight": w_ai,
                "points": _pts(s_ai, w_ai),
                "label": f"AI desk ({ai_status.lower()})" if ai_status != "AVAILABLE" else "AI desk review",
            },
            {
                "domain": "ml",
                "score": s_ml,
                "weight": w_ml,
                "points": _pts(s_ml, w_ml),
                "label": "ML predictor" if ml_avail else "ML predictor (unavailable)",
            },
        ]

        penalties: list[str] = []
        try:
            if ai_status != "AVAILABLE":
                penalties.append(f"AI {ai_status.lower()} — deterministic fallback, confidence trimmed")
            fno_deg = bool(data_health.get("fno_degraded", _cand_attr("fno_degraded", False)))
            vwap_deg = bool(data_health.get("vwap_degraded", _cand_attr("vwap_degraded", False)))
            if fno_deg:
                penalties.append("F&O feed degraded — signal capped at watch-only, extra haircut applied")
            if vwap_deg:
                cov = _num(data_health.get("vwap_coverage_pct", _cand_attr("vwap_coverage_pct", 100.0)), 100.0) or 100.0
                penalties.append(f"Session VWAP degraded (coverage {cov:.1f}%) — confidence trimmed")
            try:
                ev_state = _str(getattr(overlay, "proximity_state", "") if overlay is not None else "", "")
                if not ev_state and isinstance(overlay, dict):
                    ev_state = _str(overlay.get("proximity_state"), "")
                if ev_state and ev_state.upper() not in ("", "NORMAL", "NONE"):
                    penalties.append(f"Event risk {ev_state} — position size reduced")
            except Exception:
                pass
        except Exception:
            pass

        try:
            state = "ARMED" if fused >= armed_thr else "VALIDATED"
        except Exception:
            state = "VALIDATED"

        gates_rejected_by_others = []
        try:
            prefix = strategy + ":"
            for g in rejected:
                gs = _str(g)
                if gs and not gs.upper().startswith(prefix):
                    gates_rejected_by_others.append(gs)
            gates_rejected_by_others = gates_rejected_by_others[:10]
        except Exception:
            gates_rejected_by_others = []

        why: list[str] = []
        try:
            ind = inputs_snapshot.get("indicators") if isinstance(inputs_snapshot.get("indicators"), dict) else {}
            why.extend(layman_for_indicators(ind or {}, regime, inputs_snapshot.get("vwap"), inputs_snapshot.get("spot")))
            fno_snap = inputs_snapshot.get("fno") if isinstance(inputs_snapshot.get("fno"), dict) else {}
            why.extend(layman_for_fno(fno_snap or {}))
            rule = STRATEGY_RULES.get(strategy)
            if rule and len(why) < 7:
                why.append(f"Setup ({strategy}): {rule}")
        except Exception:
            pass
        if not why:
            why = ["Signal passed confluence checks across chart, trend and options data."]

        return {
            "verdict": {"direction": direction, "confidence": fused, "state": state},
            "maths": maths,
            "penalties": penalties,
            "gates_passed": ["trigger_integrity", "rsi_confirmation", "risk_engine"],
            "gates_rejected_by_others": gates_rejected_by_others,
            "inputs_snapshot": inputs_snapshot,
            "why_layman": why[:7],
            "what_would_change_mind": _change_mind_bullets(direction, regime),
            "data_health": data_health,
            "strategy_rule": STRATEGY_RULES.get(strategy, "Trade the confirmed direction with defined risk."),
            "weights_version": weights_version,
            "threshold_armed": armed_thr,
        }
    except Exception:
        try:
            return {
                "verdict": {"direction": "UNKNOWN", "confidence": _num(fused_score, 50.0) or 50.0, "state": "VALIDATED"},
                "maths": [],
                "penalties": ["Explain degraded — inputs unavailable"],
                "gates_passed": [],
                "gates_rejected_by_others": [],
                "inputs_snapshot": {},
                "why_layman": ["Signal explanation unavailable — inputs missing."],
                "what_would_change_mind": ["Fresh price and volume data would clarify the setup."],
                "data_health": {"degraded": True},
                "strategy_rule": "Trade the confirmed direction with defined risk.",
                "weights_version": WEIGHTS_VERSION_DEFAULT,
                "threshold_armed": THRESHOLD_ARMED_DEFAULT,
            }
        except Exception:
            return {"verdict": {}, "maths": [], "penalties": [], "why_layman": []}


def build_forecast_explain(
    ensemble_result: Any,
    mtf_features: Any,
    indicator_outputs: Any,
    ml_forecast: Any,
    options_ctx: Any,
    current_price: Any,
) -> dict:
    """Build an immutable explain bundle for a research forecast. Pure, never throws."""
    try:
        from app.research.trend_forecast import (
            LAYER_WEIGHTS as _LW,  # local import, no cycle at runtime
        )
        _weights = dict(_LW)
    except Exception:
        _weights = {"mtf_alignment": 0.30, "indicators": 0.30, "ml": 0.25, "options": 0.10, "structure": 0.05}
    try:
        ens = dict(ensemble_result) if isinstance(ensemble_result, dict) else {}
        mtf = dict(mtf_features) if isinstance(mtf_features, dict) else {}
        opts = dict(options_ctx) if isinstance(options_ctx, dict) else {}
        layer_scores = dict(ens.get("layer_scores", {})) if isinstance(ens.get("layer_scores"), dict) else {}
        ml = dict(ml_forecast) if isinstance(ml_forecast, dict) else {}

        direction = _str(ens.get("direction"), "NEUTRAL").upper()
        confidence = _num(ens.get("confidence"), 0.0) or 0.0
        score = _num(ens.get("score"), 0.0) or 0.0
        price = _num(current_price, _num(ens.get("current_price"))) or 0.0

        labels = {
            "mtf_alignment": "Multi-timeframe trend alignment",
            "indicators": "Research indicators (RSI/VWAP/MACD/Momentum/OMPI)",
            "ml": "ML ensemble",
            "options": "Options context (PCR/walls/max pain)",
            "structure": "Primary-timeframe structure (Supertrend + RSI)",
        }
        maths = []
        for domain in ("mtf_alignment", "indicators", "ml", "options", "structure"):
            s = _num(layer_scores.get(domain), 0.0) or 0.0
            w = _num(_weights.get(domain), 0.0) or 0.0
            try:
                pts = round(s * w, 2)
            except Exception:
                pts = 0.0
            maths.append({"domain": domain, "score": round(s, 2), "weight": w, "points": pts, "label": labels[domain]})

        # — layman bullets —
        why: list[str] = []
        try:
            alignment = mtf.get("alignment", {}) if isinstance(mtf.get("alignment"), dict) else {}
            overall_bias = _str(alignment.get("overall_bias"), "NEUTRAL").upper()
            align_score = _num(alignment.get("alignment_score"), 0.0) or 0.0
            tf = _str(ens.get("timeframe"), "1h")
            if overall_bias in ("BULLISH", "BEARISH"):
                why.append(f"{tf} trend {overall_bias} (alignment {align_score:.0f}/100)")
            else:
                why.append(f"{tf} trend mixed across timeframes (alignment {align_score:.0f}/100)")

            per_tf = mtf.get("per_timeframe", {}) if isinstance(mtf.get("per_timeframe"), dict) else {}
            feat_primary: dict = {}
            try:
                if tf in per_tf and isinstance(per_tf[tf], dict):
                    feat_primary = (per_tf[tf].get("features", {}) or {})
                if not feat_primary:
                    for payload in per_tf.values():
                        if isinstance(payload, dict) and payload.get("features"):
                            feat_primary = payload["features"]
                            break
            except Exception:
                feat_primary = {}
            quant = feat_primary.get("quant", {}) if isinstance(feat_primary.get("quant"), dict) else {}
            st_dir = _str(quant.get("supertrend_dir"), "").upper()
            rsi_14 = _num(quant.get("rsi_14"), None)
            if st_dir in ("BULLISH", "BEARISH"):
                why.append(f"Supertrend {st_dir} on the primary timeframe")
            if rsi_14 is not None:
                if rsi_14 >= 60:
                    why.append(f"RSI {rsi_14:.0f} — buyers in control")
                elif rsi_14 <= 40:
                    why.append(f"RSI {rsi_14:.0f} — sellers in control")
                else:
                    why.append(f"RSI {rsi_14:.0f} — trend indecisive")
            pcr_oi = _num(opts.get("pcr_oi"), None)
            if pcr_oi is not None:
                if pcr_oi >= 1.2:
                    why.append(f"Options PCR {pcr_oi:.2f} — bullish positioning")
                elif pcr_oi <= 0.8:
                    why.append(f"Options PCR {pcr_oi:.2f} — bearish positioning")
            if ml:
                b = _num(ml.get("bullish_pct"), None)
                be = _num(ml.get("bearish_pct"), None)
                bias = _str(ml.get("predicted_bias"), "")
                if b is not None and be is not None:
                    why.append(f"ML model {bias or 'mixed'} (bull {b:.0f}% / bear {be:.0f}%)")
        except Exception:
            pass
        if not why:
            why = [f"Forecast {direction} with score {score:.1f} — mixed layer agreement."]
        why = why[:5]

        # — data health: which TF missing —
        expected_tfs = ["1m", "5m", "15m", "30m", "1h", "4h", "1D"]
        missing: list[str] = []
        resampled: list[str] = []
        try:
            per_tf = mtf.get("per_timeframe", {}) if isinstance(mtf.get("per_timeframe"), dict) else {}
            raw_candles = mtf.get("candles", {}) if isinstance(mtf.get("candles"), dict) else {}
            for t in expected_tfs:
                payload = per_tf.get(t)
                feats = (payload.get("features") if isinstance(payload, dict) else None)
                if not feats:
                    missing.append(t)
            for t in expected_tfs:
                if isinstance(raw_candles.get(t), dict) and raw_candles[t].get("resampled"):
                    resampled.append(t)
            # also honour explicit flags if the feature layer provides them
            for k in ("resampled_timeframes", "resampled"):
                v = mtf.get(k)
                if isinstance(v, (list, tuple)):
                    for t in v:
                        ts = _str(t)
                        if ts and ts not in resampled:
                            resampled.append(ts)
        except Exception:
            pass
        data_health = {
            "missing_timeframes": missing,
            "resampled_timeframes": resampled,
            "degraded": bool(missing),
            "ml_available": bool(ml),
            "indicator_count": len(indicator_outputs) if isinstance(indicator_outputs, (list, tuple)) else 0,
        }

        inputs_snapshot: dict = {}
        try:
            per_tf = mtf.get("per_timeframe", {}) if isinstance(mtf.get("per_timeframe"), dict) else {}
            feat_primary = {}
            tf = _str(ens.get("timeframe"), "1h")
            if tf in per_tf and isinstance(per_tf[tf], dict):
                feat_primary = per_tf[tf].get("features", {}) or {}
            if not feat_primary:
                for payload in per_tf.values():
                    if isinstance(payload, dict) and payload.get("features"):
                        feat_primary = payload["features"]
                        break
            quant = feat_primary.get("quant", {}) if isinstance(feat_primary.get("quant"), dict) else {}
            alignment = mtf.get("alignment", {}) if isinstance(mtf.get("alignment"), dict) else {}
            vol_dyn = feat_primary.get("volume_dynamics", {}) if isinstance(feat_primary.get("volume_dynamics"), dict) else {}
            rsi_v = _num(quant.get("rsi_14"), None)
            adx_v = _num(quant.get("adx"), None)
            vwap_v = _num(quant.get("vwap"), None)
            rel_vol = _num(vol_dyn.get("relative_volume"), None)
            pcr_v = _num(opts.get("pcr_oi"), None)
            inputs_snapshot = {
                # canonical evidence keys (frontend WhyPanel) + legacy aliases
                "spot": price,
                "current_price": price,
                "vwap": vwap_v,
                "rsi": rsi_v,
                "rsi_14": rsi_v,
                "adx": adx_v,
                "pcr": pcr_v,
                "pcr_oi": pcr_v,
                "volume": rel_vol,
                "relative_volume": rel_vol,
                "supertrend_dir": _str(quant.get("supertrend_dir"), "NEUTRAL"),
                "max_pain": _num(opts.get("max_pain"), None),
                "alignment_score": _num(alignment.get("alignment_score"), 0.0) or 0.0,
                "overall_bias": _str(alignment.get("overall_bias"), "NEUTRAL"),
                "current_price_alias": price,
            }
        except Exception:
            inputs_snapshot = {"current_price": price}

        if direction == "BULLISH":
            change_mind = [
                "Price breaks back below Supertrend with rising volume — uptrend has failed",
                "RSI drops under 40 and PCR flips below 0.8 — sellers taking over",
                "A lower timeframe turns bearish first — early warning the move is fading",
            ]
        elif direction == "BEARISH":
            change_mind = [
                "Price reclaims Supertrend with strong volume — downtrend has failed",
                "RSI pushes above 60 and PCR flips above 1.2 — buyers taking over",
                "A lower timeframe turns bullish first — early warning the drop is fading",
            ]
        else:
            change_mind = [
                "Alignment score jumps above 60 either way — a real trend is starting",
                "Supertrend flips with RSI confirmation — direction is resolving",
            ]

        penalties: list[str] = []
        try:
            if not ml:
                penalties.append("ML layer neutral — no calibrated model for this horizon")
            if missing:
                penalties.append(f"Missing timeframes {missing} — forecast degraded")
            if resampled:
                penalties.append(f"Resampled from 1m: {resampled} — treat structure with care")
        except Exception:
            pass

        return {
            "verdict": {"direction": direction, "confidence": confidence, "state": _str(ens.get("forecast_horizon"), _str(ens.get("timeframe"), "1h"))},
            "maths": maths,
            "penalties": penalties,
            "gates_passed": [],
            "gates_rejected_by_others": [],
            "inputs_snapshot": inputs_snapshot,
            "why_layman": why,
            "what_would_change_mind": change_mind[:3],
            "data_health": data_health,
            "strategy_rule": "Weighted vote of trend, indicators, ML, options and structure layers.",
            "weights_version": "forecast-v1",
            "threshold_armed": 20.0,
            "final_score": score,
        }
    except Exception:
        return {
            "verdict": {"direction": "NEUTRAL", "confidence": 0.0, "state": "UNKNOWN"},
            "maths": [],
            "penalties": ["Explain degraded — inputs unavailable"],
            "gates_passed": [],
            "gates_rejected_by_others": [],
            "inputs_snapshot": {},
            "why_layman": ["Forecast explanation unavailable — inputs missing."],
            "what_would_change_mind": ["Fresh multi-timeframe data would clarify direction."],
            "data_health": {"degraded": True},
            "strategy_rule": "",
            "weights_version": "forecast-v1",
            "threshold_armed": 20.0,
        }
