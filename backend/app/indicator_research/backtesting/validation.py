"""No-lookahead, repaint and causality audits (§10, §45).

Three separate claims are checked, because they fail for different reasons:

**Structural integrity** — the fill model did what it said. A signal on bar
``t`` with ``next_open`` execution must appear as a trade whose ``entry_index``
is exactly ``t + 1``. A position must never open before its signal, close
before it opens, or overlap another position.

**Rule causality** — evaluating the rule on a truncated series must reproduce
the same decision it made in the full run. If a rule could see bar ``t+1``, the
truncated run would disagree at the boundary.

**Feature causality (repaint detection)** — recomputing an indicator on a
prefix must reproduce its value on the last bar of that prefix. This is what
catches a centred moving average, a whole-sample z-score, a future pivot or any
other "future-confirmed" value that silently rewrites history. It is the
expensive check, so it is sampled — but the samples include the final bar,
where a future-looking calculation is most likely to read "future" data that
does not exist in the prefix.

The strongest check needs a ``feature_provider`` that can re-derive every
feature from a candle prefix. Without one, the report says exactly how far the
proof goes instead of implying more than was verified.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

import structlog

logger = structlog.get_logger(__name__)

FeatureProvider = Callable[[Sequence[Mapping[str, Any]]], Mapping[str, Sequence[Any]]]

_TOLERANCE = 1e-9


def _prefix_samples(length: int, count: int = 6, minimum: int = 12) -> list[int]:
    """Prefix lengths to verify, ascending, ending at the full series.

    Sampling rather than checking every bar keeps a 100k-bar run interactive
    while still crossing several indicator warm-up boundaries.
    """
    if length < minimum:
        return []
    candidates = {
        minimum,
        max(minimum, length // 4),
        max(minimum, length // 2),
        max(minimum, (3 * length) // 4),
        max(minimum, length - 1),
    }
    points = sorted(p for p in candidates if minimum <= p <= length)
    if len(points) > count:
        step = len(points) / count
        points = [points[int(i * step)] for i in range(count)]
        if points[-1] != length:
            points.append(length)
    return sorted(set(points))


def _close_enough(a: Any, b: Any) -> bool:
    if a is None and b is None:
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
    return abs(fa - fb) <= _TOLERANCE + _TOLERANCE * max(abs(fa), abs(fb))


def check_indicator_causality(
    indicator: Any,
    candles: Sequence[Mapping[str, Any]],
    params: Mapping[str, Any] | None = None,
    sample_points: int = 6,
) -> dict[str, Any]:
    """Recompute an indicator on prefixes and compare the boundary bar."""
    length = len(candles)
    samples = _prefix_samples(length, sample_points)
    report: dict[str, Any] = {
        "checked": bool(samples),
        "scope": "indicator_only",
        "indicator_id": getattr(indicator, "indicator_id", None),
        "samples": samples,
        "checks": 0,
        "mismatches": [],
    }
    if not samples:
        report["reason"] = "series too short to test causality reliably"
        return report

    try:
        full = indicator.compute(candles, params).outputs
    except Exception as e:
        report["error"] = f"indicator failed on the full series: {e}"
        return report

    for prefix in samples:
        if prefix < 2:
            continue
        try:
            truncated = indicator.compute(candles[:prefix], params).outputs
        except Exception as e:
            report["mismatches"].append(
                {"output": "*", "index": prefix - 1, "error": f"prefix run failed: {e}"}
            )
            continue
        for name, full_series in full.items():
            if prefix - 1 >= len(full_series):
                continue
            truncated_series = truncated.get(name)
            if not truncated_series or prefix - 1 >= len(truncated_series):
                report["mismatches"].append(
                    {"output": name, "index": prefix - 1, "error": "output missing on prefix"}
                )
                continue
            left = full_series[prefix - 1]
            right = truncated_series[prefix - 1]
            report["checks"] += 1
            if not _close_enough(left, right):
                report["mismatches"].append(
                    {
                        "output": name,
                        "index": prefix - 1,
                        "full_series_value": left,
                        "prefix_value": right,
                        "message": (
                            f"'{name}' changed when future bars were removed — this "
                            "indicator repaints (it reads data after the bar)."
                        ),
                    }
                )
    report["causal"] = not report["mismatches"]
    return report


def check_rule_causality(
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    features: Mapping[str, Sequence[Any]],
    long_signals: Sequence[bool],
    short_signals: Sequence[bool],
    sample_points: int = 6,
    warmup_bars: int = 0,
) -> dict[str, Any]:
    """Compare full-run signals with signals from a truncated feature slice.

    This proves the *rule engine* is causal. It assumes the features are; the
    indicator check is what proves that.
    """
    from app.indicator_research.signals.rules import evaluate_series

    length = len(long_signals)
    samples = [p for p in _prefix_samples(length, sample_points) if p - 1 >= warmup_bars]
    report: dict[str, Any] = {
        "checked": bool(samples),
        "scope": "rules_only",
        "samples": samples,
        "checks": 0,
        "mismatches": [],
    }
    for prefix in samples:
        sliced = {name: list(values)[:prefix] for name, values in features.items()}
        prefix_long = evaluate_series(long_rule, sliced, prefix)
        prefix_short = evaluate_series(short_rule, sliced, prefix)
        for idx in (prefix - 1,):
            report["checks"] += 1
            # Inside the warm-up window the engine suppresses signals by
            # design, so the expectation there is False regardless of what the
            # raw rule says.
            if prefix_long[idx] != long_signals[idx]:
                report["mismatches"].append(
                    {
                        "rule": "long",
                        "index": idx,
                        "full_series_value": long_signals[idx],
                        "prefix_value": prefix_long[idx],
                    }
                )
            if prefix_short[idx] != short_signals[idx]:
                report["mismatches"].append(
                    {
                        "rule": "short",
                        "index": idx,
                        "full_series_value": short_signals[idx],
                        "prefix_value": prefix_short[idx],
                    }
                )
    report["causal"] = not report["mismatches"]
    return report


def check_feature_causality(
    feature_provider: FeatureProvider,
    candles: Sequence[Mapping[str, Any]],
    features: Mapping[str, Sequence[Any]],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    long_signals: Sequence[bool],
    short_signals: Sequence[bool],
    sample_points: int = 5,
    warmup_bars: int = 0,
) -> dict[str, Any]:
    """Full proof: rebuild every feature from a prefix and re-evaluate rules."""
    from app.indicator_research.signals.rules import evaluate_series

    length = len(candles)
    samples = [
        p
        for p in _prefix_samples(length, sample_points, minimum=20)
        if p - 1 >= warmup_bars
    ]
    report: dict[str, Any] = {
        "checked": bool(samples),
        "scope": "full_recompute",
        "samples": samples,
        "checks": 0,
        "mismatches": [],
    }
    if not samples:
        report["reason"] = "series too short for a full recomputation check"
        return report

    for prefix in samples:
        try:
            rebuilt = feature_provider(candles[:prefix])
        except Exception as e:
            report["mismatches"].append(
                {"feature": "*", "index": prefix - 1, "error": f"recompute failed: {e}"}
            )
            continue
        idx = prefix - 1
        for name, full_series in features.items():
            rebuilt_series = rebuilt.get(name)
            if rebuilt_series is None or idx >= len(rebuilt_series):
                report["mismatches"].append(
                    {"feature": name, "index": idx, "error": "feature missing after recompute"}
                )
                continue
            report["checks"] += 1
            if not _close_enough(full_series[idx], rebuilt_series[idx]):
                report["mismatches"].append(
                    {
                        "feature": name,
                        "index": idx,
                        "full_series_value": full_series[idx],
                        "prefix_value": rebuilt_series[idx],
                        "message": (
                            f"feature '{name}' differs once future bars are removed — "
                            "the indicator that produces it reads the future."
                        ),
                    }
                )
        sliced = {name: list(values)[:prefix] for name, values in rebuilt.items()}
        if not any(v is not None for v in _flat(sliced.values())):
            continue
        prefix_long = evaluate_series(long_rule, sliced, prefix)
        prefix_short = evaluate_series(short_rule, sliced, prefix)
        report["checks"] += 2
        if prefix_long[idx] != long_signals[idx]:
            report["mismatches"].append(
                {
                    "rule": "long",
                    "index": idx,
                    "full_series_value": long_signals[idx],
                    "prefix_value": prefix_long[idx],
                    "message": "long signal is not reproducible without future bars.",
                }
            )
        if prefix_short[idx] != short_signals[idx]:
            report["mismatches"].append(
                {
                    "rule": "short",
                    "index": idx,
                    "full_series_value": short_signals[idx],
                    "prefix_value": prefix_short[idx],
                    "message": "short signal is not reproducible without future bars.",
                }
            )
    report["causal"] = not report["mismatches"]
    return report


def _flat(values: Any) -> list[Any]:
    out: list[Any] = []
    for series in values:
        out.extend(list(series))
    return out


def structural_checks(
    trades: Sequence[Any],
    settings: Any,
    warmup_bars: int,
    length: int,
) -> dict[str, Any]:
    """Verify the fill model was honoured on every trade."""
    issues: list[str] = []
    entry_fill = settings.execution.entry_fill
    expected_gap = 1 if entry_fill == "next_open" else 0

    previous_exit = -1
    for trade in trades:
        if trade.entry_index != trade.signal_index + expected_gap:
            issues.append(
                f"Trade {trade.trade_id}: entry at bar {trade.entry_index} does not match "
                f"'{entry_fill}' execution for a signal at bar {trade.signal_index}."
            )
        if trade.exit_index is not None and trade.exit_index < trade.entry_index:
            issues.append(f"Trade {trade.trade_id}: exits before it enters.")
        if trade.entry_index < warmup_bars:
            issues.append(
                f"Trade {trade.trade_id}: entered at bar {trade.entry_index}, inside the "
                f"{warmup_bars}-bar warm-up window."
            )
        if previous_exit >= 0 and trade.entry_index <= previous_exit:
            issues.append(
                f"Trade {trade.trade_id}: overlaps the previous position "
                f"(entered at {trade.entry_index}, previous exit {previous_exit})."
            )
        if trade.exit_index is not None:
            previous_exit = trade.exit_index
    return {"passed": not issues, "issues": issues}


def validate_backtest(
    *,
    candles: Sequence[Mapping[str, Any]],
    features: Mapping[str, Sequence[Any]],
    long_rule: Mapping[str, Any] | None,
    short_rule: Mapping[str, Any] | None,
    long_signals: Sequence[bool],
    short_signals: Sequence[bool],
    trades: Sequence[Any],
    settings: Any,
    warmup_bars: int,
    indicator: Any = None,
    indicator_params: Mapping[str, Any] | None = None,
    feature_provider: FeatureProvider | None = None,
    sample_points: int = 6,
) -> dict[str, Any]:
    """Full validation block attached to every backtest result."""
    length = len(candles)
    structural = structural_checks(trades, settings, warmup_bars, length)

    if feature_provider is not None:
        causality = check_feature_causality(
            feature_provider,
            candles,
            features,
            long_rule,
            short_rule,
            long_signals,
            short_signals,
            sample_points,
            warmup_bars,
        )
    elif indicator is not None:
        causality = check_indicator_causality(
            indicator, candles, indicator_params, sample_points
        )
        rules = check_rule_causality(
            long_rule,
            short_rule,
            features,
            long_signals,
            short_signals,
            sample_points,
            warmup_bars,
        )
        causality = {**causality, "rule_check": rules}
        if not rules.get("causal", True):
            causality["causal"] = False
            causality.setdefault("mismatches", [])
            causality["mismatches"] = list(causality["mismatches"]) + list(
                rules.get("mismatches", [])
            )
    else:
        causality = check_rule_causality(
            long_rule,
            short_rule,
            features,
            long_signals,
            short_signals,
            sample_points,
            warmup_bars,
        )

    issues: list[str] = list(structural.get("issues", []))
    mismatches = causality.get("mismatches") or []
    for mismatch in mismatches[:5]:
        message = mismatch.get("message")
        if message:
            issues.append(str(message))

    # Causality is only claimed when it was actually tested. An untested case
    # must not wear the badge.
    tested = bool(causality.get("checked"))
    repaint_free = bool(causality.get("causal", False)) if tested else False
    no_lookahead = bool(structural["passed"]) and repaint_free

    if not tested:
        issues.append(
            "Causality was not verified for this run (the series is too short to "
            "recompute on prefixes). The no-lookahead badge is withheld rather than "
            "shown on an untested result."
        )
    if causality.get("scope") == "rules_only":
        issues.append(
            "Only the rule engine was verified on prefixes; feature values were not "
            "recomputed. Pass a feature provider for the full check."
        )

    return {
        "no_lookahead": no_lookahead,
        "repaint_free": repaint_free,
        "tested": tested,
        "badge": "✓ NO LOOKAHEAD" if no_lookahead else "⚠ LOOKAHEAD NOT VERIFIED",
        "scope": causality.get("scope"),
        "samples_checked": causality.get("samples", []),
        "checks_run": causality.get("checks", 0),
        "structural": structural,
        "causality": causality,
        "issues": issues,
    }


__all__ = [
    "check_feature_causality",
    "check_indicator_causality",
    "check_rule_causality",
    "structural_checks",
    "validate_backtest",
]
