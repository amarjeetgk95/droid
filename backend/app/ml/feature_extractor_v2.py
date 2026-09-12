"""1H Forecast v2.3 — v2 feature extractor (P2-1 / P2-2).

P2-1 BASIS DECISION — ``futures_basis`` DROPPED from the v2 schema.
---------------------------------------------------------------
Evidence (all verified in-repo, no live market futures feed exists):

- ``backend/app/api/futures.py``: ``/{symbol}/overview`` and ``/term-structure``
  return ``curve_state="UNAVAILABLE"`` with ``contracts=[]`` and
  ``basis_pts=None`` — the API explicitly refuses to fabricate basis when
  broker data is offline ("The Truth of Wall").
- ``backend/app/fno/context.py``: ``# futures data unavailable (module
  removed)`` — ``near_basis = 0`` / ``near_basis_pct = 0`` hardcoded, with NO
  timestamp / ``available_time`` attached, so PIT-safety
  (``available_time <= T``) can never be proven.
- ``backend/app/services/options_service.py``: ``futures_price`` is a
  synthetic cost-of-carry estimate (``spot * exp(r * t)``), NOT a market
  futures quote — deriving "basis" from it would be a synthetic feature.
- ``backend/app/ml/predictor.py:50-66``: ``term_structure = None`` always, so
  ``extract_ml_feature_vector(..., term_structure=None)`` yields
  ``futures_basis_pct = 0.0`` on every call — a constant-zero pseudo-feature.

Per plan P2-1 ("Do not ship a constant-zero feature"), option (b) is taken:
DROP ``futures_basis`` from the v2 set and use ``max_pain_distance``
(PIT-safe: derived from the options-chain snapshot timestamped at T) as the
positioning replacement. :data:`BASIS_DECISION` records the reason and
:func:`check_basis_availability` is the PIT gate that ANY future basis input
must pass before it may re-enter the schema (it currently cannot, which the
unit tests pin). The v1 10-feature path in ``feature_extractor.py`` /
``predictor.py`` is left untouched (legacy, labeled heuristic fallback).

PIT contract for every v2 input: only data with ``available_time <= T`` may
enter. Inputs carrying a timestamp later than ``decision_time`` raise
``ValueError`` (leakage). Missing inputs yield ``None`` + a missing-mask flag
— never a silent ``0`` — except via the DOCUMENTED neutral map
(:data:`NEUTRAL_IMPUTE_V2`), which is always returned alongside its flag.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

FEATURE_SCHEMA_V2 = "f12-v1"

# 15 stored model columns (plan allows 12-15). Supertrend enters as three
# per-TF ±1 votes; cross-TF agreement is a DERIVED helper
# (supertrend_agreement) kept out of the stored matrix because it is a
# deterministic function of the three votes (storing it would be redundant /
# collinear). It remains available for P2-5 abstention gating.
FEATURE_NAMES_V2 = [
    "rsi_1h",
    "adx_1h",
    "supertrend_1h",
    "supertrend_15m",
    "supertrend_4h",
    "bb_pct_b_1h",
    "atr_pct_1h",
    "ret_5",
    "ret_15",
    "relative_volume",
    "vwap_distance",
    "pcr_oi",
    "max_pain_distance",
    "vix",
    "minutes_to_close",
]

BASIS_DECISION = {
    "decision": "DROP",
    "dropped_feature": "futures_basis",
    "replacement_feature": "max_pain_distance",
    "reason": (
        "No PIT-safe market futures basis exists: /futures endpoints return "
        "UNAVAILABLE with empty contracts; fno/context.py hardcodes "
        "near_basis=0 with no timestamp; options_service futures_price is a "
        "synthetic cost-of-carry estimate, not a market quote; predictor.py "
        "passes term_structure=None so v1 futures_basis_pct is constant-zero. "
        "Shipping it would be a constant-zero pseudo-feature (P2-1 forbids)."
    ),
    "reentry_rule": (
        "futures_basis may re-enter only via check_basis_availability() "
        "returning (True, reason) for a timestamped, market-quoted basis with "
        "available_time <= T, plus a schema bump (f12-v2) and OOS dBrier "
        "evidence from the P1 harness."
    ),
}

# Per-feature engineering scale. Fixed (fit-free) min-max / neutral-centered
# transforms so training and inference agree byte-for-byte; the P2-3 logistic
# fits an additional z-scaler on train folds and persists its params in the
# artifact meta (recorded, never refit silently at inference).
SCALING_V2: dict[str, dict[str, Any]] = {
    "rsi_1h": {"transform": "(rsi_14 - 50) / 50", "clip": [-1.0, 1.0], "neutral": 0.0},
    "adx_1h": {"transform": "adx / 50", "clip": [0.0, 1.0], "neutral": 0.0},
    "supertrend_1h": {"transform": "BULLISH -> +1, BEARISH -> -1, else missing", "clip": [-1.0, 1.0], "neutral": 0.0},
    "supertrend_15m": {"transform": "BULLISH -> +1, BEARISH -> -1, else missing", "clip": [-1.0, 1.0], "neutral": 0.0},
    "supertrend_4h": {"transform": "BULLISH -> +1, BEARISH -> -1, else missing", "clip": [-1.0, 1.0], "neutral": 0.0},
    "bb_pct_b_1h": {"transform": "passthrough %B (v1-compatible)", "clip": [-0.5, 1.5], "neutral": 0.5},
    "atr_pct_1h": {"transform": "atr_14 / price * 100 (percent)", "clip": [0.0, 5.0], "neutral": 0.5},
    "ret_5": {"transform": "5-bar percent return", "clip": [-5.0, 5.0], "neutral": 0.0},
    "ret_15": {"transform": "15-bar percent return", "clip": [-5.0, 5.0], "neutral": 0.0},
    "relative_volume": {"transform": "current / avg_20 (ratio)", "clip": [0.0, 5.0], "neutral": 1.0},
    "vwap_distance": {"transform": "(price - vwap) / vwap * 100 (percent)", "clip": [-5.0, 5.0], "neutral": 0.0},
    "pcr_oi": {"transform": "(pcr_oi - 1) / 0.5 (v1-compatible)", "clip": [-1.0, 1.0], "neutral": 0.0},
    "max_pain_distance": {"transform": "(spot - max_pain) / spot * 100 (percent)", "clip": [-5.0, 5.0], "neutral": 0.0},
    "vix": {"transform": "passthrough level (India VIX)", "clip": [5.0, 50.0], "neutral": 15.0},
    "minutes_to_close": {"transform": "minutes_to_15:30_IST_close / 375", "clip": [0.0, 1.0], "neutral": 0.5},
}

# Documented neutral imputation (used ONLY via to_model_vector_v2, always with
# the missing flag set — never silently). Values mirror SCALING_V2 neutrals.
NEUTRAL_IMPUTE_V2: dict[str, float] = {k: float(v["neutral"]) for k, v in SCALING_V2.items()}

# Per-feature provenance for the audit trail (source + PIT note).
SOURCES_V2: dict[str, str] = {
    "rsi_1h": "primary 1h quant.rsi_14 (candles <= T only)",
    "adx_1h": "primary 1h quant.adx (candles <= T only)",
    "supertrend_1h": "primary 1h quant.supertrend_dir @ last 1h close <= T",
    "supertrend_15m": "15m quant.supertrend_dir @ last 15m close <= T",
    "supertrend_4h": "4h quant.supertrend_dir @ last 4h close <= T",
    "bb_pct_b_1h": "primary 1h quant.bb_pct_b (candles <= T only)",
    "atr_pct_1h": "primary 1h quant.atr_14 / last 1h close <= T",
    "ret_5": "1h closes: last vs 5 bars back, both <= T",
    "ret_15": "1h closes: last vs 15 bars back, both <= T",
    "relative_volume": "1h current/avg20 volume, bars <= T only",
    "vwap_distance": "last 1h close vs session VWAP from bars <= T",
    "pcr_oi": "options chain snapshot with available_time <= T; stale -> null",
    "max_pain_distance": "options chain max_pain @ snapshot <= T (basis replacement, see BASIS_DECISION)",
    "vix": "VIX quote with available_time <= T; stale/missing -> null",
    "minutes_to_close": "decision-time clock (15:30 IST close); not a market input, no lookahead",
}


def feature_schema_hash_v2() -> str:
    """Stable sha256 over schema tag + ordered feature names."""
    payload = "|".join([FEATURE_SCHEMA_V2, *FEATURE_NAMES_V2])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_ts(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        try:
            ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _quant(payload: Any) -> dict:
    """Accept a quant subdict or a full compute_features payload."""
    if not isinstance(payload, dict):
        return {}
    inner = payload.get("quant")
    if isinstance(inner, dict):
        return inner
    return payload


def _get(payload: Any, *keys: str, nested: tuple[str, ...] = ("momentum_dynamics", "volume_dynamics", "quant")) -> Any:
    """Flat lookup with fallback into known nested subdicts (full-payload tolerant)."""
    if not isinstance(payload, dict):
        return None
    for k in keys:
        if payload.get(k) is not None:
            return payload[k]
    for section in nested:
        sub = payload.get(section)
        if isinstance(sub, dict):
            for k in keys:
                if sub.get(k) is not None:
                    return sub[k]
    return None


def _clip(value: Optional[float], name: str) -> Optional[float]:
    if value is None:
        return None
    lo, hi = SCALING_V2[name]["clip"]
    try:
        return round(min(hi, max(lo, float(value))), 4)
    except (TypeError, ValueError):
        return None


def check_basis_availability(
    futures_ctx: Any,
    decision_time: Any = None,
) -> tuple[bool, str]:
    """PIT gate for any futures-basis input (P2-1 re-entry rule).

    Returns (True, reason) ONLY when ``futures_ctx`` carries a market-quoted
    (non-synthetic) basis AND a parseable timestamp with
    ``available_time <= T``. Everything observed in-repo today fails this
    gate — callers must then DROP the feature (see :data:`BASIS_DECISION`),
    never impute 0.
    """
    t_now = _parse_ts(decision_time) if decision_time is not None else None
    if not isinstance(futures_ctx, dict) or not futures_ctx:
        return False, "DROP: no futures context (predictor passes term_structure=None)"
    if futures_ctx.get("synthetic", False):
        return False, "DROP: synthetic basis (e.g. cost-of-carry estimate), not a market quote"
    if not futures_ctx.get("available", True):
        return False, f"DROP: futures unavailable ({futures_ctx.get('reason', 'no reason')})"
    basis = futures_ctx.get("futures_basis", futures_ctx.get("basis"))
    if basis is None:
        return False, "DROP: basis is None (UNAVAILABLE contracts=[], basis_pts=None)"
    try:
        if not (float(basis) != 0.0):
            return False, "DROP: basis is constant-zero placeholder (module removed, near_basis=0 hardcoded)"
    except (TypeError, ValueError):
        return False, "DROP: basis is non-numeric"
    ts = _parse_ts(futures_ctx.get("available_time", futures_ctx.get("timestamp")))
    if ts is None:
        return False, "DROP: no PIT timestamp on futures basis (cannot prove available_time <= T)"
    if t_now is not None and ts > t_now:
        return False, "DROP: futures timestamp is after decision time (lookahead)"
    if futures_ctx.get("curve_state") == "UNAVAILABLE" or futures_ctx.get("term_structure_curve") == "UNKNOWN":
        return False, "DROP: term-structure curve UNAVAILABLE/UNKNOWN (no live broker futures feed)"
    return True, f"OK: market-quoted basis {basis} timestamped {ts.isoformat()} <= T"


def assert_pit(available_time: Any, decision_time: Any, what: str = "feature input") -> datetime:
    """Raise ValueError if ``available_time`` is after ``decision_time`` (leakage)."""
    ts = _parse_ts(available_time)
    t_now = _parse_ts(decision_time)
    if ts is None:
        raise ValueError(f"PIT: {what} has no parseable timestamp (unverifiable inputs are rejected)")
    if t_now is not None and ts > t_now:
        raise ValueError(f"PIT: {what} at {ts.isoformat()} is after decision time {t_now.isoformat()} (lookahead)")
    return ts


def supertrend_sign(direction: Any) -> Optional[float]:
    """Map a supertrend direction string to ±1; unknown/neutral -> None (missing, not 0)."""
    if not isinstance(direction, str):
        return None
    d = direction.strip().upper()
    if d == "BULLISH":
        return 1.0
    if d == "BEARISH":
        return -1.0
    return None


def supertrend_agreement(d1h: Any, d15m: Any, d4h: Any) -> Optional[float]:
    """Fraction of {1h,15m,4h} supertrend votes that are BULLISH (None if any vote missing)."""
    votes = [supertrend_sign(d) for d in (d1h, d15m, d4h)]
    if any(v is None for v in votes):
        return None
    return round(sum(1.0 for v in votes if v > 0) / 3.0, 4)


def _minutes_to_close_ist(ts: datetime) -> int:
    """Minutes from an aware UTC instant to the 15:30 IST close (0 when closed/past)."""
    from datetime import timedelta as _td

    ist = ts.astimezone(timezone(_td(hours=5, minutes=30)))
    total = ist.hour * 60 + ist.minute
    close_min = 15 * 60 + 30  # 930
    open_min = 9 * 60 + 15  # 555
    if total >= close_min or total < 0:
        return 0
    if total < open_min:
        return close_min - open_min  # 375, full session ahead
    return close_min - total


def extract_feature_vector_v2(
    quant_1h: dict | None,
    quant_15m: dict | None,
    quant_4h: dict | None,
    dynamics: dict | None,
    options_ctx: dict | None,
    vix: Any,
    session_info: dict | None,
    decision_time: Any = None,
) -> dict[str, Any]:
    """Build the v2 feature row from PIT-safe slices (pure, no I/O, no network).

    Each of ``quant_1h/15m/4h`` accepts a quant subdict or a full
    ``compute_features`` payload; ``dynamics`` accepts flat keys
    (``return_5_pct`` …) or the full payload (nested lookup); ``options_ctx``
    accepts ``pcr_oi``/``max_pain`` (+ optional ``available_time`` /
    ``timestamp`` enforced against ``decision_time``); ``vix`` accepts a float
    or a ``{"value": x, "available_time": ts, "stale": bool}`` mapping
    (stale -> null + flag); ``session_info`` accepts ``minutes_to_close`` or a
    ``timestamp`` to derive it.
    """
    q1, q15, q4 = _quant(quant_1h or {}), _quant(quant_15m or {}), _quant(quant_4h or {})
    dyn = dynamics if isinstance(dynamics, dict) else {}
    opt = options_ctx if isinstance(options_ctx, dict) else {}
    sess = session_info if isinstance(session_info, dict) else {}

    t_now = _parse_ts(decision_time) if decision_time is not None else None

    # --- PIT timestamps: latest verifiable input time must be <= T ---------
    input_times: list[datetime] = []
    for payload, what in ((quant_1h, "quant_1h"), (dynamics, "dynamics"), (options_ctx, "options_ctx")):
        if isinstance(payload, dict):
            raw = payload.get("available_time", payload.get("timestamp"))
            if raw is not None:
                input_times.append(assert_pit(raw, t_now, what) if t_now else _parse_ts(raw))
    input_times = [t for t in input_times if t is not None]

    vix_val: Optional[float] = None
    vix_stale = False
    if isinstance(vix, dict):
        vix_stale = bool(vix.get("stale", False))
        raw_ts = vix.get("available_time", vix.get("timestamp"))
        if raw_ts is not None:
            ts = assert_pit(raw_ts, t_now, "vix") if t_now else _parse_ts(raw_ts)
            if ts is not None:
                input_times.append(ts)
        vix_val = vix.get("value", vix.get("vix", vix.get("atm_iv")))
    else:
        vix_val = vix
    if vix_stale:
        vix_val = None

    opt_ts_raw = opt.get("available_time", opt.get("timestamp")) if opt else None
    opt_ok = True
    if isinstance(opt, dict) and opt.get("available") is False:
        opt_ok = False

    # --- raw engineering ----------------------------------------------------
    rsi_raw = _get(q1, "rsi_14", "rsi")
    adx_raw = _get(q1, "adx")
    st_1h_raw = supertrend_sign(_get(q1, "supertrend_dir"))
    st_15m_raw = supertrend_sign(_get(q15, "supertrend_dir"))
    st_4h_raw = supertrend_sign(_get(q4, "supertrend_dir"))
    bb_raw = _get(q1, "bb_pct_b")

    price = _get(dyn, "current_price", "close", "spot")
    if price is None:
        price = _get(q1, "close", "current_price")
    atr_raw = _get(q1, "atr_14", "atr")
    atr_pct_raw = (float(atr_raw) / float(price) * 100.0) if atr_raw is not None and price else None

    ret_5_raw = _get(dyn, "return_5_pct", "ret_5")
    ret_15_raw = _get(dyn, "return_15_pct", "ret_15")
    rel_vol_raw = _get(dyn, "relative_volume", "rel_volume")
    vwap_raw = _get(dyn, "vwap_dist_pct", "vwap_distance", nested=("quant", "momentum_dynamics", "volume_dynamics"))
    if vwap_raw is None:
        vwap_raw = _get(q1, "vwap_dist_pct")

    pcr_raw = _get(opt, "pcr_oi", "pcr") if opt_ok else None
    mp_raw = _get(opt, "max_pain", "max_pain_strike") if opt_ok else None
    spot_for_mp = _get(opt, "spot", "current_price") if opt_ok else None
    if spot_for_mp is None:
        spot_for_mp = price
    mp_dist_raw = (
        (float(spot_for_mp) - float(mp_raw)) / float(spot_for_mp) * 100.0
        if mp_raw is not None and spot_for_mp
        else None
    )

    mtc_raw = sess.get("minutes_to_close")
    if mtc_raw is None:
        sess_ts = _parse_ts(sess.get("available_time", sess.get("timestamp"))) or t_now
        mtc_raw = _minutes_to_close_ist(sess_ts) if sess_ts is not None else None

    raw: dict[str, Optional[float]] = {
        "rsi_1h": (float(rsi_raw) - 50.0) / 50.0 if rsi_raw is not None else None,
        "adx_1h": float(adx_raw) / 50.0 if adx_raw is not None else None,
        "supertrend_1h": st_1h_raw,
        "supertrend_15m": st_15m_raw,
        "supertrend_4h": st_4h_raw,
        "bb_pct_b_1h": float(bb_raw) if bb_raw is not None else None,
        "atr_pct_1h": atr_pct_raw,
        "ret_5": float(ret_5_raw) if ret_5_raw is not None else None,
        "ret_15": float(ret_15_raw) if ret_15_raw is not None else None,
        "relative_volume": float(rel_vol_raw) if rel_vol_raw is not None else None,
        "vwap_distance": float(vwap_raw) if vwap_raw is not None else None,
        "pcr_oi": (float(pcr_raw) - 1.0) / 0.5 if pcr_raw is not None else None,
        "max_pain_distance": mp_dist_raw,
        "vix": float(vix_val) if vix_val is not None else None,
        "minutes_to_close": float(mtc_raw) / 375.0 if mtc_raw is not None else None,
    }
    values = {name: _clip(raw.get(name), name) for name in FEATURE_NAMES_V2}

    missing_mask = {name: (1 if values[name] is None else 0) for name in FEATURE_NAMES_V2}
    missing_count = sum(missing_mask.values())
    available_time = max(input_times).isoformat() if input_times else (t_now.isoformat() if t_now else None)

    return {
        "schema": FEATURE_SCHEMA_V2,
        "schema_hash": feature_schema_hash_v2(),
        "feature_names": list(FEATURE_NAMES_V2),
        "values": values,
        "vector": [values[name] for name in FEATURE_NAMES_V2],
        "missing_mask": missing_mask,
        "missing_count": missing_count,
        "model_vector": [values[name] if values[name] is not None else NEUTRAL_IMPUTE_V2[name] for name in FEATURE_NAMES_V2],
        "imputed": {name: (values[name] is None) for name in FEATURE_NAMES_V2},
        "available_time": available_time,
        "pit_ok": True,  # reaching here means no input was dated after decision_time
        "decision_time": t_now.isoformat() if t_now else None,
        "basis": {"included": False, **{k: v for k, v in BASIS_DECISION.items() if k in ("decision", "reason", "replacement_feature")}},
        "sources": dict(SOURCES_V2),
        "notes": (
            "supertrend_agreement available via supertrend_agreement() (derived, not stored); "
            "model_vector uses NEUTRAL_IMPUTE_V2 only where imputed[name] is true."
        ),
    }


def to_model_vector_v2(row: dict[str, Any]) -> tuple[list[float], list[int]]:
    """Split an extracted row into (imputed float vector, missing-mask ints)."""
    names = row.get("feature_names", FEATURE_NAMES_V2)
    if list(names) != FEATURE_NAMES_V2:
        raise ValueError(f"schema mismatch: expected {FEATURE_SCHEMA_V2} {FEATURE_NAMES_V2}")
    values = row.get("values", {})
    vec = [float(values[n]) if values.get(n) is not None else NEUTRAL_IMPUTE_V2[n] for n in FEATURE_NAMES_V2]
    mask = [1 if values.get(n) is None else 0 for n in FEATURE_NAMES_V2]
    return vec, mask
