"""3-class calibration metrics for 1H forecast v2.3 (P1-4). Pure math only.

Conventions (match app.ml.targets.LABEL_MAP):
    index 0 = BEARISH, 1 = NEUTRAL, 2 = BULLISH.
    P_rows[i] = [P(bear), P(neut), P(bull)], simplex (sums to 1).
    y_true_idx[i] in {0, 1, 2}.

Functions:
    brier_score_3class(y_true_idx, P_rows)
        Mean over rows of sum_k (p_k - onehot_k)^2. Range [0, 2].
        Perfect (p_true=1) -> 0. Uniform (1/3 each) -> 2/3 ~= 0.6667.
    log_loss_3class(y_true_idx, P_rows, eps=1e-12)
        Mean -log(clip(p_true, eps, 1)). Natural log. Perfect -> 0,
        uniform -> -log(1/3) ~= 1.0986.
    ece_equal_width(y_true_idx, pmax, n_bins=10, y_pred_idx=None)
        Equal-width ECE over confidence. Returns {"ece", "bins", "n", "n_bins"}.
        Correctness: if y_pred_idx given, correct = (y_pred == y_true);
        else y_true_idx must already be binary 0/1 correctness.
        Bin j covers [j/B, (j+1)/B), last bin inclusive of 1.0.
        ece = sum_j (n_j / N) * |acc_j - conf_j|.
    reliability_table(...) -> bins list (same rows as ece bins).
    calibration_slope_intercept(y_true_binary, p_pred)
        Binary logistic fit y ~ sigmoid(a + b * logit(p)) via Newton-Raphson
        (IRLS), pure math, no sklearn/scipy. Well-calibrated -> slope ~= 1,
        intercept ~= 0. Returns {"slope", "intercept", "n", "converged", "method"}.
    calibration_slopes_ovr(y_true_idx, P_rows)
        1-vs-rest wrapper: per-class {0,1,2} slope/intercept dicts.
    calibration_report(y_true_idx, P_rows, n_bins=10)
        One-call bundle {n, brier, log_loss, ece, bins, slopes_ovr, n_bins}
        for the walk-forward report dict.

All functions are pure (no I/O, no globals) and handle empty inputs by
returning 0/empty rather than raising, so offline report wiring never breaks
on thin cells. Type/shape misuse raises ValueError with a clear message.
No numpy/sklearn/scipy dependency.
"""

from __future__ import annotations

import math
from typing import Dict, List, Sequence

EPS_LOGLOSS: float = 1e-12
EPS_LOGIT: float = 1e-6


# ---------------------------------------------------------------------------
# internal validators
# ---------------------------------------------------------------------------

def _as_index_list(y_true_idx: Sequence[int]) -> List[int]:
    try:
        out = [int(v) for v in y_true_idx]
    except TypeError as e:
        raise ValueError("y_true_idx must be a sequence of ints") from e
    return out


def _validate_3class(y_true_idx: Sequence[int], P_rows: Sequence[Sequence[float]]) -> tuple[List[int], List[List[float]]]:
    y = _as_index_list(y_true_idx)
    try:
        P = [[float(v) for v in row] for row in P_rows]
    except TypeError as e:
        raise ValueError("P_rows must be a sequence of 3-element sequences") from e
    if len(y) != len(P):
        raise ValueError(f"length mismatch: y_true_idx={len(y)} vs P_rows={len(P)}")
    for i, (t, row) in enumerate(zip(y, P)):
        if t not in (0, 1, 2):
            raise ValueError(f"y_true_idx[{i}] must be 0/1/2, got {t!r}")
        if len(row) != 3:
            raise ValueError(f"P_rows[{i}] must have 3 entries, got {len(row)}")
        for v in row:
            if not (0.0 <= v <= 1.0) or v != v:  # NaN check via v != v
                raise ValueError(f"P_rows[{i}] entries must be in [0,1], got {row!r}")
    return y, P


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def _logit(p: float) -> float:
    c = min(max(float(p), EPS_LOGIT), 1.0 - EPS_LOGIT)
    return math.log(c / (1.0 - c))


# ---------------------------------------------------------------------------
# Brier / log-loss
# ---------------------------------------------------------------------------

def brier_score_3class(y_true_idx: Sequence[int], P_rows: Sequence[Sequence[float]]) -> float:
    """Multiclass Brier score (mean squared simplex error). Lower is better."""
    y, P = _validate_3class(y_true_idx, P_rows)
    if not y:
        return 0.0
    total = 0.0
    for t, row in zip(y, P):
        for k in range(3):
            d = row[k] - (1.0 if k == t else 0.0)
            total += d * d
    return total / len(y)


def log_loss_3class(
    y_true_idx: Sequence[int],
    P_rows: Sequence[Sequence[float]],
    eps: float = EPS_LOGLOSS,
) -> float:
    """Multiclass log-loss with eps clipping of p_true. Lower is better."""
    if not eps > 0:
        raise ValueError(f"eps must be > 0, got {eps!r}")
    y, P = _validate_3class(y_true_idx, P_rows)
    if not y:
        return 0.0
    total = 0.0
    for t, row in zip(y, P):
        p = min(max(row[t], eps), 1.0)
        total += -math.log(p)
    return total / len(y)


# ---------------------------------------------------------------------------
# ECE / reliability
# ---------------------------------------------------------------------------

def ece_equal_width(
    y_true_idx: Sequence[int],
    pmax: Sequence[float],
    n_bins: int = 10,
    y_pred_idx: Sequence[int] | None = None,
) -> Dict:
    """Equal-width Expected Calibration Error over confidence.

    Args:
        y_true_idx: true class indices {0,1,2}, OR binary correctness {0,1}
            when y_pred_idx is None.
        pmax: per-row confidence = max(P) in [0,1].
        n_bins: number of equal-width bins over [0,1] (>= 1).
        y_pred_idx: optional predicted class indices; when given,
            correctness = (y_pred == y_true).

    Returns:
        {"ece": float, "bins": [...], "n": int, "n_bins": int} where each bin
        is {"bin", "lo", "hi", "n", "acc", "conf", "gap"}.
    """
    try:
        nb = int(n_bins)
    except (TypeError, ValueError) as e:
        raise ValueError(f"n_bins must be a positive int, got {n_bins!r}") from e
    if nb < 1:
        raise ValueError(f"n_bins must be >= 1, got {n_bins!r}")
    y = _as_index_list(y_true_idx)
    try:
        conf = [float(v) for v in pmax]
    except TypeError as e:
        raise ValueError("pmax must be a sequence of floats") from e
    if len(y) != len(conf):
        raise ValueError(f"length mismatch: y_true_idx={len(y)} vs pmax={len(conf)}")
    for i, v in enumerate(conf):
        if not (0.0 <= v <= 1.0) or v != v:
            raise ValueError(f"pmax[{i}] must be in [0,1], got {v!r}")
    if y_pred_idx is not None:
        yp = _as_index_list(y_pred_idx)
        if len(yp) != len(y):
            raise ValueError("y_pred_idx length must match y_true_idx")
        for v in yp:
            if v not in (0, 1, 2):
                raise ValueError(f"y_pred_idx entries must be 0/1/2, got {v!r}")
        correct = [1 if a == b else 0 for a, b in zip(yp, y)]
    else:
        if any(v not in (0, 1) for v in y):
            raise ValueError(
                "y_true_idx holds class labels 0/1/2 but no y_pred_idx was given; "
                "pass y_pred_idx=argmax(P) or pass binary correctness directly"
            )
        correct = list(y)
    n_total = len(y)
    if n_total == 0:
        return {"ece": 0.0, "bins": [], "n": 0, "n_bins": nb}
    bins: List[Dict] = []
    ece = 0.0
    for b in range(nb):
        lo = b / nb
        hi = (b + 1) / nb
        idx = [
            i for i, c in enumerate(conf)
            if (c >= lo and (c < hi or (b == nb - 1 and c <= 1.0)))
        ]
        cnt = len(idx)
        if cnt == 0:
            bins.append({"bin": b, "lo": lo, "hi": hi, "n": 0, "acc": 0.0, "conf": 0.0, "gap": 0.0})
            continue
        acc = sum(correct[i] for i in idx) / cnt
        cf = sum(conf[i] for i in idx) / cnt
        gap = abs(acc - cf)
        ece += (cnt / n_total) * gap
        bins.append({"bin": b, "lo": lo, "hi": hi, "n": cnt, "acc": acc, "conf": cf, "gap": gap})
    return {"ece": ece, "bins": bins, "n": n_total, "n_bins": nb}


def reliability_table(
    y_true_idx: Sequence[int],
    pmax: Sequence[float],
    n_bins: int = 10,
    y_pred_idx: Sequence[int] | None = None,
) -> List[Dict]:
    """Per-confidence-bin reliability rows (same bins as ece_equal_width)."""
    return ece_equal_width(y_true_idx, pmax, n_bins, y_pred_idx)["bins"]


# ---------------------------------------------------------------------------
# calibration slope / intercept (binary logistic on logit(p))
# ---------------------------------------------------------------------------

def calibration_slope_intercept(
    y_true_binary: Sequence[int],
    p_pred: Sequence[float],
    max_iter: int = 100,
    tol: float = 1e-8,
) -> Dict:
    """Fit y ~ sigmoid(a + b*logit(p)) by Newton-Raphson (IRLS). Pure math.

    Well-calibrated predictor -> slope b ~= 1, intercept a ~= 0.
    b < 1 means overconfident (predicted spread too wide); b > 1 underconfident.

    Edge handling (documented, deterministic):
    - empty input -> slope 0, intercept 0, converged False.
    - all y equal (complete separation) -> slope 0.0, intercept +/-10.0
      (sign of the constant class), converged False.
    - constant p (singular Hessian) -> slope 0.0,
      intercept = logit(mean(y) clipped), converged False.

    Returns {"slope", "intercept", "n", "converged", "method"}.
    """
    try:
        y = [int(v) for v in y_true_binary]
    except TypeError as e:
        raise ValueError("y_true_binary must be a sequence of 0/1") from e
    try:
        p = [float(v) for v in p_pred]
    except TypeError as e:
        raise ValueError("p_pred must be a sequence of floats") from e
    if len(y) != len(p):
        raise ValueError(f"length mismatch: y={len(y)} vs p={len(p)}")
    for v in y:
        if v not in (0, 1):
            raise ValueError(f"y_true_binary entries must be 0/1, got {v!r}")
    for i, v in enumerate(p):
        if not (0.0 <= v <= 1.0) or v != v:
            raise ValueError(f"p_pred[{i}] must be in [0,1], got {v!r}")
    n = len(y)
    method = "logistic(y ~ logit(p)) via Newton-Raphson (IRLS), pure math, no sklearn"
    if n == 0:
        return {"slope": 0.0, "intercept": 0.0, "n": 0, "converged": False, "method": method}
    s = sum(y)
    if s == 0 or s == n:
        return {
            "slope": 0.0,
            "intercept": 10.0 if s == n else -10.0,
            "n": n,
            "converged": False,
            "method": method + "; separated (constant y)",
        }
    xs = [_logit(v) for v in p]
    # constant-p guard: variance ~ 0 -> singular Hessian
    mean_x = sum(xs) / n
    if sum((x - mean_x) ** 2 for x in xs) < 1e-12:
        mu = min(max(s / n, EPS_LOGIT), 1.0 - EPS_LOGIT)
        return {
            "slope": 0.0,
            "intercept": math.log(mu / (1.0 - mu)),
            "n": n,
            "converged": False,
            "method": method + "; constant p (singular Hessian)",
        }
    a, b = 0.0, 0.0
    converged = False
    for _ in range(int(max_iter)):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for yi, xi in zip(y, xs):
            ph = _sigmoid(a + b * xi)
            r = yi - ph
            w = ph * (1.0 - ph)
            g0 += r
            g1 += xi * r
            h00 += w
            h01 += xi * w
            h11 += xi * xi * w
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            converged = False
            break
        da = (h11 * g0 - h01 * g1) / det
        db = (-h01 * g0 + h00 * g1) / det
        a += da
        b += db
        if max(abs(da), abs(db)) < tol:
            converged = True
            break
    return {"slope": b, "intercept": a, "n": n, "converged": converged, "method": method}


def calibration_slopes_ovr(
    y_true_idx: Sequence[int],
    P_rows: Sequence[Sequence[float]],
) -> Dict[int, Dict]:
    """1-vs-rest calibration slopes: {class_idx: slope/intercept dict}."""
    y, P = _validate_3class(y_true_idx, P_rows)
    out: Dict[int, Dict] = {}
    for k in (0, 1, 2):
        yb = [1 if t == k else 0 for t in y]
        pp = [row[k] for row in P]
        if not yb:
            out[k] = {"slope": 0.0, "intercept": 0.0, "n": 0, "converged": False,
                      "method": "empty 1-vs-rest split"}
        else:
            out[k] = calibration_slope_intercept(yb, pp)
    return out


def calibration_report(
    y_true_idx: Sequence[int],
    P_rows: Sequence[Sequence[float]],
    n_bins: int = 10,
) -> Dict:
    """One-call bundle for the walk-forward report dict.

    Returns {"n", "brier", "log_loss", "ece", "bins", "slopes_ovr", "n_bins"}.
    Empty inputs -> zeros/empties (never raises on empty).
    """
    y, P = _validate_3class(y_true_idx, P_rows)
    if not y:
        return {"n": 0, "brier": 0.0, "log_loss": 0.0, "ece": 0.0,
                "bins": [], "slopes_ovr": {}, "n_bins": int(n_bins)}
    pmax = [max(row) for row in P]
    y_pred = [max(range(3), key=lambda k: row[k]) for row in P]
    ece_out = ece_equal_width(y, pmax, n_bins, y_pred)
    return {
        "n": len(y),
        "brier": brier_score_3class(y, P),
        "log_loss": log_loss_3class(y, P),
        "ece": ece_out["ece"],
        "bins": ece_out["bins"],
        "slopes_ovr": calibration_slopes_ovr(y, P),
        "n_bins": ece_out["n_bins"],
    }


def attach_calibration(report_dict: Dict, y_true_idx, P_rows, n_bins: int = 10) -> Dict:
    """Return a copy of report_dict with report_dict['calibration'] set.

    Pure helper for walk-forward wiring; raises ValueError on shape misuse
    (caller should catch and skip so backtest never breaks).
    """
    out = dict(report_dict)
    out["calibration"] = calibration_report(y_true_idx, P_rows, n_bins)
    return out
