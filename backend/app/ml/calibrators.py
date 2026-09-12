"""Single global calibrator for 1H forecast v2.3 (P2-4). Pure math + JSON persistence.

Primary: temperature scaling (1-param NLL minimization via grid + refine).
Challenger: 1-vs-rest isotonic regression via pool-adjacent-violators (PAVA).

Conventions (match app.ml.targets.LABEL_MAP):
    index 0 = BEARISH, 1 = NEUTRAL, 2 = BULLISH.
    P_rows[i] = [P(bear), P(neut), P(bull)], simplex (sums to 1).
    y[i] in {0, 1, 2}.

Leakage rule (hard): fit ONLY on out-of-fold / OOS predictions from the
walk-forward harness. Every fit entry point takes ``oos=True`` and raises
ValueError for any other value — in-sample fitting is refused, never
silently accepted.

Persistence: ``calibrator_h60_{INSTRUMENT}.json`` next to the trainer
artifacts (``backend/app/ml/artifacts/``)::

    {method, T (or params), fit_n, fit_window, ece_before, ece_after,
     nll_before, nll_after, version: "cal-v1"}

Inference: ``P_cal = calibrate(P_raw)``; ``confidence = max(P_cal)``;
callers surface both ``raw_confidence`` (pre-cal) and ``confidence``
(post-cal). No numpy/sklearn/scipy dependency.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.ml.calibration_metrics import ece_equal_width

CALIBRATOR_VERSION = "cal-v1"
CALIBRATOR_HORIZON_MINUTES = 60

EPS_CLIP: float = 1e-12
T_MIN_DEFAULT: float = 0.05
T_MAX_DEFAULT: float = 10.0


# ---------------------------------------------------------------------------
# validators / small pure helpers
# ---------------------------------------------------------------------------

def _validate_labels(y: Sequence[int]) -> List[int]:
    try:
        out = [int(v) for v in y]
    except TypeError as e:
        raise ValueError("y must be a sequence of ints in {0,1,2}") from e
    for i, v in enumerate(out):
        if v not in (0, 1, 2):
            raise ValueError(f"y[{i}] must be 0/1/2, got {v!r}")
    return out


def _validate_P_rows(P_rows: Sequence[Sequence[float]]) -> List[List[float]]:
    try:
        P = [[float(v) for v in row] for row in P_rows]
    except TypeError as e:
        raise ValueError("P must be a sequence of 3-element sequences") from e
    for i, row in enumerate(P):
        if len(row) != 3:
            raise ValueError(f"P[{i}] must have 3 entries, got {len(row)}")
        for v in row:
            if not (0.0 <= v <= 1.0) or v != v:
                raise ValueError(f"P[{i}] entries must be in [0,1], got {row!r}")
    return P


def _check_oos(oos: Any) -> None:
    """Hard OOS gate: only ``oos=True`` (identity check) may fit."""
    if oos is not True:
        raise ValueError(
            "CalibratorV1 refuses in-sample fitting: fit ONLY on OOS "
            f"(out-of-fold) predictions, got oos={oos!r}. Pass oos=True."
        )


def _clip_row(row: Sequence[float], eps: float = EPS_CLIP) -> List[float]:
    clipped = [min(max(float(v), eps), 1.0) for v in row]
    s = sum(clipped)
    if s <= 0:
        return [1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0]
    return [v / s for v in clipped]


def _temperature_row(row: Sequence[float], T: float) -> List[float]:
    """Apply temperature scaling to one 3-vector.

    Logits are recovered as log(P) (valid up to an additive constant, which
    softmax absorbs), scaled by 1/T, and soft-maxed. T > 1 softens
    overconfidence; T < 1 sharpens; T == 1 is identity.
    """
    t = float(T)
    if not (t > 0) or t != t:
        raise ValueError(f"T must be a positive finite float, got {T!r}")
    p = _clip_row(row)
    # p_k ** (1/T) / sum, computed in log space with max-subtraction.
    logits = [math.log(v) / t for v in p]
    m = max(logits)
    exps = [math.exp(l - m) for l in logits]
    s = sum(exps)
    return [e / s for e in exps]


def _nll(y: Sequence[int], P_rows: Sequence[Sequence[float]], eps: float = EPS_CLIP) -> float:
    total = 0.0
    for t, row in zip(y, P_rows):
        total += -math.log(min(max(row[t], eps), 1.0))
    return total / len(y) if y else 0.0


def _ece(y: Sequence[int], P_rows: Sequence[Sequence[float]], n_bins: int = 10) -> float:
    if not y:
        return 0.0
    pmax = [max(row) for row in P_rows]
    y_pred = [max(range(3), key=lambda k: row[k]) for row in P_rows]
    return float(ece_equal_width(y, pmax, n_bins, y_pred)["ece"])


def _argmax_row(row: Sequence[float]) -> int:
    return max(range(3), key=lambda k: row[k])


# ---------------------------------------------------------------------------
# temperature fit: 1-param NLL minimization via grid + refine (pure math)
# ---------------------------------------------------------------------------

def _logspace(lo: float, hi: float, n: int) -> List[float]:
    if n <= 1:
        return [float(lo)]
    llo, lhi = math.log(float(lo)), math.log(float(hi))
    return [math.exp(llo + i * (lhi - llo) / (n - 1)) for i in range(n)]


def fit_temperature(
    oos_P: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    oos: bool = True,
    t_min: float = T_MIN_DEFAULT,
    t_max: float = T_MAX_DEFAULT,
    fit_window: Any = None,
    n_bins: int = 10,
) -> Dict[str, Any]:
    """Fit the temperature T on OOS predictions by NLL minimization.

    Grid search over log-spaced T in [t_min, t_max] (41 points) followed by
    3 rounds of narrowed refine (25 points each, window x0.5/x2.0 around the
    incumbent). Returns the persistable calibrator dict::

        {method, T, fit_n, fit_window, ece_before, ece_after,
         nll_before, nll_after, version}

    Raises ValueError unless ``oos is True`` (in-sample fit refused), on
    shape misuse, or on empty inputs.
    """
    _check_oos(oos)
    yy = _validate_labels(y)
    PP = _validate_P_rows(oos_P)
    if len(yy) != len(PP):
        raise ValueError(f"length mismatch: y={len(yy)} vs oos_P={len(PP)}")
    if not yy:
        raise ValueError("fit_temperature requires at least 1 OOS row (got 0)")
    if not (float(t_min) > 0 and float(t_max) > float(t_min)):
        raise ValueError(f"need 0 < t_min < t_max, got {t_min!r}, {t_max!r}")

    ece_before = _ece(yy, PP, n_bins)
    nll_before = _nll(yy, PP)

    def _cost(T: float) -> float:
        cal = [_temperature_row(row, T) for row in PP]
        return _nll(yy, cal)

    best_T = 1.0
    best_cost = _cost(1.0)
    for T in _logspace(t_min, t_max, 41):
        c = _cost(T)
        if c < best_cost:
            best_cost = c
            best_T = T
    lo, hi = float(t_min), float(t_max)
    for _ in range(3):
        lo_r = max(lo, best_T / 2.0)
        hi_r = min(hi, best_T * 2.0)
        if not hi_r > lo_r:
            break
        for T in _logspace(lo_r, hi_r, 25):
            c = _cost(T)
            if c < best_cost:
                best_cost = c
                best_T = T

    cal_best = [_temperature_row(row, best_T) for row in PP]
    return {
        "method": "temperature",
        "T": float(best_T),
        "fit_n": len(yy),
        "fit_window": fit_window,
        "ece_before": float(ece_before),
        "ece_after": float(_ece(yy, cal_best, n_bins)),
        "nll_before": float(nll_before),
        "nll_after": float(best_cost),
        "version": CALIBRATOR_VERSION,
    }


# ---------------------------------------------------------------------------
# isotonic challenger: 1-vs-rest PAVA (pure math)
# ---------------------------------------------------------------------------

def _pava_1d(y_sorted: Sequence[float]) -> List[float]:
    """Pool-adjacent-violators isotonic regression (non-decreasing).

    Input: binary labels (0/1) sorted by increasing predicted score.
    Output: fitted monotone values, same length.
    """
    n = len(y_sorted)
    if n == 0:
        return []
    # Blocks as [sum, count]; average = sum/count.
    sums: List[float] = []
    counts: List[int] = []
    for v in y_sorted:
        sums.append(float(v))
        counts.append(1)
        while len(sums) >= 2 and (sums[-2] / counts[-2]) > (sums[-1] / counts[-1]):
            sums[-2] += sums[-1]
            counts[-2] += counts[-1]
            sums.pop()
            counts.pop()
    out: List[float] = []
    for s, c in zip(sums, counts):
        out.extend([s / c] * c)
    return out


def fit_isotonic_ovr(
    oos_P: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    oos: bool = True,
    fit_window: Any = None,
) -> Dict[str, Any]:
    """Fit 1-vs-rest isotonic maps (PAVA) on OOS predictions.

    Returns a persistable dict ``{method: "isotonic-ovr", params: {k:
    {xs, ys}}, fit_n, fit_window, ece_before, ece_after, version}`` where
    ``xs`` are the sorted unique predicted probs for class k and ``ys``
    the fitted monotone values. Raises ValueError unless ``oos is True``.
    """
    _check_oos(oos)
    yy = _validate_labels(y)
    PP = _validate_P_rows(oos_P)
    if len(yy) != len(PP):
        raise ValueError(f"length mismatch: y={len(yy)} vs oos_P={len(PP)}")
    if not yy:
        raise ValueError("fit_isotonic_ovr requires at least 1 OOS row (got 0)")
    ece_before = _ece(yy, PP)
    params: Dict[str, Any] = {}
    for k in (0, 1, 2):
        pairs = sorted(((row[k], 1.0 if t == k else 0.0) for t, row in zip(yy, PP)),
                       key=lambda pr: pr[0])
        xs_sorted = [p for p, _ in pairs]
        fitted = _pava_1d([b for _, b in pairs])
        # Collapse to unique-x step points (right-continuous: max fitted per x).
        ux: List[float] = []
        uy: List[float] = []
        for x, f in zip(xs_sorted, fitted):
            if ux and x == ux[-1]:
                uy[-1] = max(uy[-1], f)
            else:
                ux.append(x)
                uy.append(f)
        params[str(k)] = {"xs": ux, "ys": uy}
    cal = [_apply_isotonic_row(row, params) for row in PP]
    return {
        "method": "isotonic-ovr",
        "params": params,
        "fit_n": len(yy),
        "fit_window": fit_window,
        "ece_before": float(ece_before),
        "ece_after": float(_ece(yy, cal)),
        "version": CALIBRATOR_VERSION,
    }


def _isotonic_lookup(p: float, xs: List[float], ys: List[float]) -> float:
    """Right-continuous stepwise lookup: value at largest x <= p (edge-clamped)."""
    if not xs:
        return float(p)
    if p <= xs[0]:
        return float(ys[0])
    if p >= xs[-1]:
        return float(ys[-1])
    lo, hi = 0, len(xs) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if xs[mid] <= p:
            lo = mid
        else:
            hi = mid - 1
    return float(ys[lo])


def _apply_isotonic_row(row: Sequence[float], params: Dict[str, Any]) -> List[float]:
    vals = []
    for k in (0, 1, 2):
        cell = (params or {}).get(str(k), {})
        vals.append(_isotonic_lookup(float(row[k]), list(cell.get("xs", [])),
                                     list(cell.get("ys", []))))
    vals = [min(max(v, EPS_CLIP), 1.0) for v in vals]
    s = sum(vals)
    if s <= 0:
        return [1.0 / 3.0] * 3
    return [v / s for v in vals]


# ---------------------------------------------------------------------------
# CalibratorV1 class + persistence
# ---------------------------------------------------------------------------

def _sanitize_instrument(instrument: str) -> str:
    s = str(instrument or "UNKNOWN").upper().strip()
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in s.replace(" ", "_")) or "UNKNOWN"


def calibrator_path(instrument: str, h: int = CALIBRATOR_HORIZON_MINUTES) -> Path:
    """Artifact path ``calibrator_h{h}_{INSTRUMENT}.json`` in the ML artifacts dir."""
    from app.ml.trainer import MODEL_DIR  # local import: trainer owns the dir

    return Path(MODEL_DIR) / f"calibrator_h{int(h)}_{_sanitize_instrument(instrument)}.json"


class CalibratorV1:
    """Single global temperature calibrator (primary) for one (instrument, H=60).

    ``fit`` refuses anything but ``oos=True``. ``calibrate`` maps one raw
    3-vector (or one prob dict) to a calibrated simplex.
    """

    def __init__(
        self,
        T: float = 1.0,
        method: str = "temperature",
        fit_n: int = 0,
        fit_window: Any = None,
        ece_before: Optional[float] = None,
        ece_after: Optional[float] = None,
        nll_before: Optional[float] = None,
        nll_after: Optional[float] = None,
        isotonic_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        if method not in ("temperature", "isotonic-ovr"):
            raise ValueError(f"unknown calibrator method {method!r}")
        if method == "temperature" and not (float(T) > 0):
            raise ValueError(f"T must be > 0, got {T!r}")
        self.method = method
        self.T = float(T)
        self.fit_n = int(fit_n)
        self.fit_window = fit_window
        self.ece_before = ece_before
        self.ece_after = ece_after
        self.nll_before = nll_before
        self.nll_after = nll_after
        self.isotonic_params = isotonic_params

    # -- fit -------------------------------------------------------------
    def fit(
        self,
        oos_P: Sequence[Sequence[float]],
        y: Sequence[int],
        *,
        oos: bool = True,
        fit_window: Any = None,
    ) -> "CalibratorV1":
        """Fit on OOS predictions only (``oos=True`` required)."""
        _check_oos(oos)
        if self.method == "isotonic-ovr":
            d = fit_isotonic_ovr(oos_P, y, oos=True,
                                 fit_window=fit_window if fit_window is not None else self.fit_window)
            self.isotonic_params = d["params"]
            self.fit_n = d["fit_n"]
            self.fit_window = d["fit_window"]
            self.ece_before = d["ece_before"]
            self.ece_after = d["ece_after"]
        else:
            d = fit_temperature(oos_P, y, oos=True,
                                fit_window=fit_window if fit_window is not None else self.fit_window)
            self.T = d["T"]
            self.fit_n = d["fit_n"]
            self.fit_window = d["fit_window"]
            self.ece_before = d["ece_before"]
            self.ece_after = d["ece_after"]
            self.nll_before = d["nll_before"]
            self.nll_after = d["nll_after"]
        return self

    # -- inference -------------------------------------------------------
    def calibrate(self, P_raw: Sequence[float]) -> List[float]:
        """Map one raw 3-vector [bear, neut, bull] to a calibrated simplex."""
        row = _validate_P_rows([list(P_raw)])[0]
        if self.method == "isotonic-ovr":
            if not self.isotonic_params:
                raise ValueError("isotonic calibrator is unfitted (no params)")
            return _apply_isotonic_row(row, self.isotonic_params)
        return _temperature_row(row, self.T)

    def calibrate_rows(self, P_rows: Sequence[Sequence[float]]) -> List[List[float]]:
        """Batch version of :meth:`calibrate` (each output row is a simplex)."""
        PP = _validate_P_rows(P_rows)
        return [self.calibrate(row) for row in PP]

    def calibrate_dict(self, prob_dict: Dict[str, float]) -> Dict[str, float]:
        """Map ``{bullish, neutral, bearish}`` to a calibrated dict (same keys)."""
        try:
            bear = float(prob_dict["bearish"])
            neut = float(prob_dict["neutral"])
            bull = float(prob_dict["bullish"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(
                "prob_dict must hold numeric {bullish, neutral, bearish}"
            ) from e
        cal = self.calibrate([bear, neut, bull])
        return {"bullish": cal[2], "neutral": cal[1], "bearish": cal[0]}

    # -- persistence -----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "method": self.method,
            "fit_n": self.fit_n,
            "fit_window": self.fit_window,
            "ece_before": self.ece_before,
            "ece_after": self.ece_after,
            "version": CALIBRATOR_VERSION,
        }
        if self.method == "isotonic-ovr":
            d["params"] = self.isotonic_params
        else:
            d["T"] = self.T
            d["nll_before"] = self.nll_before
            d["nll_after"] = self.nll_after
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CalibratorV1":
        if not isinstance(d, dict):
            raise ValueError("calibrator payload must be a dict")
        if d.get("version") != CALIBRATOR_VERSION:
            raise ValueError(
                f"unsupported calibrator version {d.get('version')!r} "
                f"(implements {CALIBRATOR_VERSION!r})"
            )
        method = d.get("method", "temperature")
        if method == "isotonic-ovr":
            return cls(method=method, fit_n=d.get("fit_n", 0),
                       fit_window=d.get("fit_window"),
                       ece_before=d.get("ece_before"), ece_after=d.get("ece_after"),
                       isotonic_params=d.get("params"))
        return cls(T=d.get("T", 1.0), method="temperature",
                   fit_n=d.get("fit_n", 0), fit_window=d.get("fit_window"),
                   ece_before=d.get("ece_before"), ece_after=d.get("ece_after"),
                   nll_before=d.get("nll_before"), nll_after=d.get("nll_after"))


def save_calibrator(cal: CalibratorV1, instrument: str,
                    h: int = CALIBRATOR_HORIZON_MINUTES) -> Path:
    """Persist ``calibrator_h{h}_{INSTRUMENT}.json``; returns the path."""
    path = calibrator_path(instrument, h)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cal.to_dict(), indent=2, sort_keys=True))
    return path


def load_calibrator(instrument: str,
                    h: int = CALIBRATOR_HORIZON_MINUTES) -> Optional[CalibratorV1]:
    """Load a persisted calibrator, or None when no artifact exists.

    Raises ValueError on corrupt / version-mismatched payloads (callers
    degrade to uncalibrated + limitation, never crash the forecast).
    """
    path = calibrator_path(instrument, h)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"calibrator artifact unreadable ({path.name}): {e}") from e
    # Accept legacy ECE_* key aliases from early experiment logs.
    if "ece_before" not in payload and "ECE_before" in payload:
        payload["ece_before"] = payload.pop("ECE_before")
    if "ece_after" not in payload and "ECE_after" in payload:
        payload["ece_after"] = payload.pop("ECE_after")
    return CalibratorV1.from_dict(payload)


__all__ = [
    "CALIBRATOR_VERSION",
    "CALIBRATOR_HORIZON_MINUTES",
    "CalibratorV1",
    "fit_temperature",
    "fit_isotonic_ovr",
    "calibrator_path",
    "save_calibrator",
    "load_calibrator",
]
