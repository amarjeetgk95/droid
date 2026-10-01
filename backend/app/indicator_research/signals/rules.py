"""Structured signal-rule evaluator (§8).

A rule is a JSON document. It is validated into a canonical form once and then
evaluated per bar. There is no code generation and no ``eval``: a rule that a
user saves, an optimizer mutates or an experiment file carries from another
machine is inert data.

Shape
-----
.. code-block:: json

    {
      "operator": "AND",
      "conditions": [
        {"left": "fisher", "operator": "crosses_above", "right": "signal"},
        {"left": "fisher", "operator": "<", "right": -1.0},
        {"operator": "OR", "conditions": [
            {"left": "close", "operator": ">", "right": "vwap"},
            {"left": "cycle_strength", "operator": ">", "right": 0.3}
        ]}
      ]
    }

Operands
--------
``"fisher"`` (string)
    A feature column: any indicator output or the built-in price columns
    ``open`` / ``high`` / ``low`` / ``close`` / ``volume``.
``-1.5`` (number) / ``true`` (boolean)
    A literal. For ``in_range`` / ``outside_range`` the right operand is a
    two-element array ``[lo, hi]``.
``{"feature": "rsi"}`` / ``{"value": 70}``
    Explicit form, for machine-generated rules where a bare string would be
    ambiguous (e.g. a feature literally named ``"70"``).

Operator semantics
------------------
===============  ==================================================================
``>`` ``<``       Strict comparison of the current bar's values.
``>=`` ``<=``     Inclusive comparison.
``==`` ``!=``     Equality with a 1e-12 tolerance for floats.
``crosses_above`` Previous bar ``left <= right`` and current bar ``left > right``.
``crosses_below`` Previous bar ``left >= right`` and current bar ``left < right``.
``turns_up``      ``v[t] > v[t-1]`` and ``v[t-1] < v[t-2]`` (t-1 is a strict trough).
``turns_down``    ``v[t] < v[t-1]`` and ``v[t-1] > v[t-2]`` (t-1 is a strict peak).
``slope_up``      ``v[t] > v[t-bars]``; ``bars`` defaults to 1.
``slope_down``    ``v[t] < v[t-bars]``.
``in_range``      ``lo <= left <= hi`` (right operand is ``[lo, hi]``).
``outside_range`` ``left < lo`` or ``left > hi``.
===============  ==================================================================

Lookahead
---------
Every operator reads the current bar and strictly earlier bars only. There is
no operator that can reference a future bar, which is a deliberate design
choice: an operator set that *cannot* express lookahead is worth more than a
validator for one that can.

Missing data
------------
A ``None`` operand (inside an indicator's warm-up window) makes the condition
false. It never compares as zero, and it never raises. An empty group — no
active conditions — also evaluates false, so a half-built rule produces no
trades rather than an always-on signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.indicator_research.enums import LogicOperator, RuleOperator

_EPS = 1e-12
_MAX_DEPTH = 12


class RuleError(ValueError):
    """Raised when a rule is structurally invalid."""


@dataclass(frozen=True)
class OperatorDoc:
    """UI-facing description of one operator."""

    name: str
    label: str
    description: str
    operands: int  # 1 or 2 (2 means it takes a right-hand operand)
    takes_range: bool = False


OPERATOR_DOCS: tuple[OperatorDoc, ...] = (
    OperatorDoc(">", "is greater than", "left > right on the current bar", 2),
    OperatorDoc("<", "is less than", "left < right on the current bar", 2),
    OperatorDoc(">=", "is at least", "left >= right", 2),
    OperatorDoc("<=", "is at most", "left <= right", 2),
    OperatorDoc("==", "equals", "left == right (1e-12 tolerance)", 2),
    OperatorDoc("!=", "does not equal", "left != right", 2),
    OperatorDoc(
        "crosses_above",
        "crosses above",
        "left was <= right on the previous bar and is > right now",
        2,
    ),
    OperatorDoc(
        "crosses_below",
        "crosses below",
        "left was >= right on the previous bar and is < right now",
        2,
    ),
    OperatorDoc(
        "turns_up",
        "turns up",
        "the previous bar was a strict trough and the current bar is higher",
        1,
    ),
    OperatorDoc(
        "turns_down",
        "turns down",
        "the previous bar was a strict peak and the current bar is lower",
        1,
    ),
    OperatorDoc("slope_up", "slope up", "value is higher than `bars` bars ago", 1),
    OperatorDoc("slope_down", "slope down", "value is lower than `bars` bars ago", 1),
    OperatorDoc(
        "in_range",
        "is inside range",
        "lo <= value <= hi, with the range given as [lo, hi]",
        2,
        takes_range=True,
    ),
    OperatorDoc(
        "outside_range",
        "is outside range",
        "value < lo or value > hi, with the range given as [lo, hi]",
        2,
        takes_range=True,
    ),
)

OPERATOR_NAMES: tuple[str, ...] = tuple(doc.name for doc in OPERATOR_DOCS)
_LOGIC_NAMES: tuple[str, ...] = ("AND", "OR", "NOT")


# --------------------------------------------------------------------------- #
# Normalisation / validation
# --------------------------------------------------------------------------- #
def _operand(value: Any, *, where: str) -> tuple[str, Any]:
    """Canonicalise an operand into ``("feature", name)`` or ``("literal", v)``."""
    if isinstance(value, Mapping):
        if "feature" in value:
            name = value["feature"]
            if not isinstance(name, str) or not name.strip():
                raise RuleError(f"{where}: 'feature' must be a non-empty string")
            return "feature", name.strip()
        if "value" in value:
            return "literal", value["value"]
        raise RuleError(f"{where}: operand object must have 'feature' or 'value'")
    if isinstance(value, str):
        if value == "":
            raise RuleError(f"{where}: empty feature name")
        return "feature", value
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return "literal", value
    if isinstance(value, (list, tuple)):
        items = list(value)
        if len(items) != 2 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) for v in items
        ):
            raise RuleError(f"{where}: array operand must be exactly two numbers [lo, hi]")
        return "range", [float(items[0]), float(items[1])]
    raise RuleError(f"{where}: unsupported operand {value!r}")


def _normalize_group(raw: Mapping[str, Any], depth: int, where: str) -> dict[str, Any]:
    if depth > _MAX_DEPTH:
        raise RuleError(f"{where}: rule nesting exceeds {_MAX_DEPTH} levels")
    operator = str(raw.get("operator", "AND")).upper()
    if operator not in _LOGIC_NAMES:
        raise RuleError(
            f"{where}: logical operator must be one of {list(_LOGIC_NAMES)}, got {operator!r}"
        )
    conditions_raw = raw.get("conditions")
    if conditions_raw is None:
        raise RuleError(f"{where}: group is missing 'conditions'")
    if not isinstance(conditions_raw, (list, tuple)):
        raise RuleError(f"{where}: 'conditions' must be a list")

    conditions: list[dict[str, Any]] = []
    for idx, item in enumerate(conditions_raw):
        loc = f"{where}.conditions[{idx}]"
        if not isinstance(item, Mapping):
            raise RuleError(f"{loc}: condition must be an object")
        if "operator" in item and "conditions" in item and "left" not in item:
            conditions.append(_normalize_group(item, depth + 1, loc))
        else:
            conditions.append(_normalize_condition(item, loc))

    if operator == "NOT" and len(conditions) != 1:
        raise RuleError(f"{where}: NOT takes exactly one condition, got {len(conditions)}")
    return {"operator": operator, "conditions": conditions}


def _normalize_condition(raw: Mapping[str, Any], where: str) -> dict[str, Any]:
    if "left" not in raw:
        raise RuleError(f"{where}: condition is missing 'left'")
    operator = raw.get("operator")
    if not isinstance(operator, str) or operator not in OPERATOR_NAMES:
        raise RuleError(
            f"{where}: operator must be one of {list(OPERATOR_NAMES)}, got {operator!r}"
        )
    doc = next(d for d in OPERATOR_DOCS if d.name == operator)

    left_kind, left_value = _operand(raw["left"], where=f"{where}.left")
    right_kind: str | None = None
    right_value: Any = None
    if doc.operands == 2:
        if "right" not in raw:
            raise RuleError(f"{where}: operator '{operator}' requires 'right'")
        right_kind, right_value = _operand(raw["right"], where=f"{where}.right")
        if doc.takes_range and right_kind != "range":
            raise RuleError(f"{where}: operator '{operator}' requires a [lo, hi] range")
        if not doc.takes_range and right_kind == "range":
            raise RuleError(f"{where}: operator '{operator}' does not accept a [lo, hi] range")

    bars = raw.get("bars")
    if bars is not None:
        if isinstance(bars, bool) or not isinstance(bars, (int, float)) or int(bars) < 1:
            raise RuleError(f"{where}: 'bars' must be a positive integer")
        bars = int(bars)
    elif operator in ("slope_up", "slope_down"):
        bars = 1

    return {
        "left_kind": left_kind,
        "left": left_value,
        "operator": operator,
        "right_kind": right_kind,
        "right": right_value,
        "bars": bars,
        "enabled": bool(raw.get("enabled", True)),
        "label": raw.get("label") if isinstance(raw.get("label"), str) else None,
    }


def normalize_rule(rule: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Validate and canonicalise a rule. ``None`` stays ``None`` (no signals)."""
    if rule is None:
        return None
    if not isinstance(rule, Mapping):
        raise RuleError("rule must be an object")
    return _normalize_group(rule, 0, "rule")


def _iter_conditions(group: Mapping[str, Any]):
    for cond in group.get("conditions", []):
        if "conditions" in cond:
            yield from _iter_conditions(cond)
        else:
            yield cond


def unknown_features(
    rule: Mapping[str, Any] | None, known: Sequence[str] | set[str]
) -> list[str]:
    """Feature names a rule references that are not available.

    Callers use this to fail a request with a precise 422 before running,
    rather than running on a half-populated feature map (where the missing
    column would silently evaluate as "no signal").
    """
    try:
        normalized = normalize_rule(rule)
    except RuleError:
        return []
    if normalized is None:
        return []
    available = set(known)
    missing: set[str] = set()
    for cond in _iter_conditions(normalized):
        for side in ("left", "right"):
            if cond.get(f"{side}_kind") == "feature" and cond.get(side) not in available:
                missing.add(str(cond[side]))
    return sorted(missing)


def validate_rule(
    rule: Mapping[str, Any] | None,
    available_features: Sequence[str] | None = None,
) -> list[str]:
    """Return a list of human-readable problems (empty means valid).

    Structural errors raise; this reports the softer issues a user should see
    before running — unknown feature names and rules that can never fire.
    """
    problems: list[str] = []
    try:
        normalized = normalize_rule(rule)
    except RuleError as e:
        return [str(e)]
    if normalized is None:
        return ["No rule defined."]

    active = 0
    for name in unknown_features(normalized, available_features or ()):
        problems.append(f"Unknown feature '{name}' in the rule.")
    for cond in _iter_conditions(normalized):
        if not cond.get("enabled", True):
            continue
        active += 1
    if active == 0:
        problems.append("Every condition is disabled — this rule can never produce a signal.")
    return problems


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _resolve(cond: Mapping[str, Any], side: str, features: Mapping[str, Sequence[Any]], i: int) -> Any:
    kind = cond.get(f"{side}_kind")
    if kind == "feature":
        name = cond[side]
        column = features.get(name)
        if column is None:
            raise RuleError(f"Unknown feature '{name}'")
        if i >= len(column):
            return None
        value = column[i]
        if isinstance(value, bool):
            return float(value)
        if value is None:
            return None
        return float(value)
    if kind == "range":
        return cond[side]
    return cond[side]


def _compare(op: str, left: float, right: float) -> bool:
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == "==":
        return abs(left - right) <= _EPS
    if op == "!=":
        return abs(left - right) > _EPS
    return False


def _condition_at(
    cond: Mapping[str, Any],
    features: Mapping[str, Sequence[Any]],
    i: int,
) -> bool:
    op = cond["operator"]
    kind = cond["left_kind"]

    # Unary operators act on the left-hand column alone.
    if op in ("turns_up", "turns_down", "slope_up", "slope_down"):
        if kind != "feature":
            return False
        current = _resolve(cond, "left", features, i)
        bars = int(cond["bars"] or 1)
        lag = 2 if op in ("turns_up", "turns_down") else bars
        if current is None or i - lag < 0:
            return False
        earlier = _resolve(cond, "left", features, i - lag)
        if earlier is None:
            return False
        if op == "turns_up":
            middle = _resolve(cond, "left", features, i - 1)
            return middle is not None and current > middle and middle < earlier
        if op == "turns_down":
            middle = _resolve(cond, "left", features, i - 1)
            return middle is not None and current < middle and middle > earlier
        if op == "slope_up":
            return current > earlier
        return current < earlier

    left = _resolve(cond, "left", features, i)
    right = _resolve(cond, "right", features, i)
    if left is None or right is None:
        return False

    if op in ("in_range", "outside_range"):
        lo, hi = float(right[0]), float(right[1])
        if lo > hi:
            lo, hi = hi, lo
        inside = lo <= left <= hi
        return inside if op == "in_range" else not inside

    if op in ("crosses_above", "crosses_below"):
        if i < 1:
            return False
        prev_left = _resolve(cond, "left", features, i - 1)
        prev_right = _resolve(cond, "right", features, i - 1)
        if prev_left is None or prev_right is None:
            return False
        if op == "crosses_above":
            return prev_left <= prev_right and left > right
        return prev_left >= prev_right and left < right

    return _compare(op, left, right)


def _group_at(
    group: Mapping[str, Any],
    features: Mapping[str, Sequence[Any]],
    i: int,
) -> bool:
    operator = group["operator"]
    conditions = group.get("conditions") or []

    if operator == "NOT":
        # Normalisation guarantees exactly one child, and that child may be a
        # nested group *or* a single condition. Both must be negated correctly:
        # treating a leaf as a group would evaluate an empty AND (false) and
        # make every NOT rule permanently true.
        if not conditions:
            return False
        child = conditions[0]
        if "conditions" in child:
            return not _group_at(child, features, i)
        return not _condition_at(child, features, i)

    # An enabled condition that is itself a group recurses; a disabled one is
    # dropped entirely. With nothing left active the group is false, so a
    # half-built AND rule cannot fire on every bar.
    outcomes: list[bool] = []
    for cond in conditions:
        if not cond.get("enabled", True):
            continue
        if "conditions" in cond:
            outcomes.append(_group_at(cond, features, i))
        else:
            outcomes.append(_condition_at(cond, features, i))

    if not outcomes:
        return False
    if operator == "AND":
        return all(outcomes)
    return any(outcomes)


def is_normalized(group: Mapping[str, Any] | None) -> bool:
    """True when ``group`` already came out of :func:`normalize_rule`.

    Lets the engine normalise once per run instead of once per bar.
    """
    if not isinstance(group, Mapping) or "operator" not in group:
        return False
    for cond in group.get("conditions") or []:
        if not isinstance(cond, Mapping):
            return False
        if "conditions" in cond:
            if not is_normalized(cond):
                return False
        elif "left_kind" not in cond:
            return False
    return True


def evaluate_at(
    rule: Mapping[str, Any] | None,
    features: Mapping[str, Sequence[Any]],
    index: int,
) -> bool:
    """Evaluate a rule at one bar. ``None`` rule → False.

    Accepts either a raw rule (normalised on the fly) or one already produced
    by :func:`normalize_rule`. The engine passes the normalised form.
    """
    if rule is None:
        return False
    normalized = rule if is_normalized(rule) else normalize_rule(rule)
    if normalized is None:
        return False
    return _group_at(normalized, features, index)


def evaluate_series(
    rule: Mapping[str, Any] | None,
    features: Mapping[str, Sequence[Any]],
    length: int | None = None,
) -> list[bool]:
    """Evaluate a rule for every bar.

    Causality note: this is *vectorised*, but each output element depends only
    on features at that bar and earlier ones — every operator is defined that
    way. ``backtesting.validation`` re-runs rules on truncated prefixes to
    prove it rather than assuming it.
    """
    normalized = rule if is_normalized(rule) else normalize_rule(rule)
    if length is None:
        length = max((len(v) for v in features.values()), default=0)
    if normalized is None or length <= 0:
        return [False] * max(0, length)
    return [_group_at(normalized, features, i) for i in range(length)]


# --------------------------------------------------------------------------- #
# Human-readable rendering (used by the UI and stored with experiments)
# --------------------------------------------------------------------------- #
def _operand_label(kind: str | None, value: Any) -> str:
    if kind == "feature":
        return str(value)
    if kind == "range":
        return f"[{value[0]}, {value[1]}]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def describe_condition(cond: Mapping[str, Any]) -> str:
    op = cond["operator"]
    label = _operand_label(cond.get("left_kind"), cond.get("left"))
    description = next((d.description for d in OPERATOR_DOCS if d.name == op), op)
    if cond.get("right_kind") is not None:
        return f"{label} {op} {_operand_label(cond['right_kind'], cond['right'])}"
    if op in ("slope_up", "slope_down"):
        return f"{label} {op} ({cond.get('bars', 1)} bars)"
    return f"{label} {description}"


def describe_rule(rule: Mapping[str, Any] | None) -> str:
    """One-line rendering, e.g. ``fisher crosses_above signal AND fisher < -1.0``."""
    normalized = normalize_rule(rule)
    if normalized is None:
        return "no rule"

    def render(group: Mapping[str, Any]) -> str:
        parts: list[str] = []
        for cond in group.get("conditions") or []:
            if not cond.get("enabled", True):
                continue
            if "conditions" in cond:
                parts.append(f"({render(cond)})")
            else:
                parts.append(describe_condition(cond))
        joiner = f" {group['operator']} "
        return joiner.join(parts) if parts else "∅"

    return render(normalized)
