"""Signal-rule engine tests, operator by operator."""

from __future__ import annotations

import pytest

from app.indicator_research.signals.rules import (
    OPERATOR_NAMES,
    RuleError,
    describe_rule,
    evaluate_at,
    evaluate_series,
    is_normalized,
    normalize_rule,
    unknown_features,
    validate_rule,
)

FEATURES = {
    "close": [10.0, 11.0, 12.0, 11.0, 10.0, 10.0],
    "vwap": [10.5, 10.5, 10.5, 10.5, 10.5, 10.5],
    "rsi": [40.0, 55.0, 70.0, 50.0, 30.0, 45.0],
    "warming": [None, None, 5.0, 5.0, 5.0, 5.0],
}


def series(rule):
    return evaluate_series(rule, FEATURES, len(FEATURES["close"]))


def condition(left, operator, right=None, **extra):
    payload = {"left": left, "operator": operator}
    if right is not None:
        payload["right"] = right
    payload.update(extra)
    return {"operator": "AND", "conditions": [payload]}


# --------------------------------------------------------------------------- #
# Comparison operators
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "operator,right,expected_indexes",
    [
        (">", 10.5, [1, 2, 3]),
        ("<", 10.5, [0, 4, 5]),
        (">=", 10.0, [0, 1, 2, 3, 4, 5]),
        ("<=", 10.0, [0, 4, 5]),
        ("==", 10.0, [0, 4, 5]),
        ("!=", 10.0, [1, 2, 3]),
    ],
)
def test_comparison_operators(operator, right, expected_indexes):
    result = series(condition("close", operator, right))
    assert [i for i, v in enumerate(result) if v] == expected_indexes


def test_crosses_above_is_strict_and_needs_a_previous_bar():
    result = series(condition("close", "crosses_above", 11.0))
    # 11 -> 12 crosses 11 upwards at index 2; index 1 does not (10 -> 11, not >).
    assert [i for i, v in enumerate(result) if v] == [2]


def test_crosses_below_is_strict():
    result = series(condition("close", "crosses_below", 12.0))
    # 12 -> 11 at index 3 (previous 12 >= 12, now 11 < 12).
    assert [i for i, v in enumerate(result) if v] == [3]


def test_crosses_treats_equal_previous_as_crossing():
    features = {"a": [1.0, 2.0, 2.0], "b": [2.0, 2.0, 2.0]}
    result = evaluate_series(condition("a", "crosses_above", "b"), features, 3)
    # a <= b at index 1 (2 <= 2) and a > b is false at 1; at index 2 a == b.
    assert result == [False, False, False]
    features2 = {"a": [1.0, 2.0, 2.5], "b": [2.0, 2.0, 2.0]}
    result2 = evaluate_series(condition("a", "crosses_above", "b"), features2, 3)
    assert result2 == [False, False, True]


def test_turns_up_requires_a_strict_trough():
    result = series(condition("rsi", "turns_up"))
    # rsi: 40,55,70,50,30,45 -> trough at index 4 (30 < 50), rising at 5.
    assert [i for i, v in enumerate(result) if v] == [5]


def test_turns_down_requires_a_strict_peak():
    result = series(condition("rsi", "turns_down"))
    # peak at index 2 (70 > 55), falling at 3.
    assert [i for i, v in enumerate(result) if v] == [3]


def test_slope_operators_read_the_requested_lag():
    up = series(condition("close", "slope_up", bars=2))
    # close[i] > close[i-2]: index 2 (12 > 10), index 5 (10 > 11? no).
    assert [i for i, v in enumerate(up) if v] == [2]
    down = series(condition("close", "slope_down", bars=2))
    # close[i] < close[i-2]: index 4 (10 < 12) and index 5 (10 < 11).
    assert [i for i, v in enumerate(down) if v] == [4, 5]


def test_in_and_outside_range():
    inside = series(condition("rsi", "in_range", [40, 60]))
    assert [i for i, v in enumerate(inside) if v] == [0, 1, 3, 5]
    outside = series(condition("rsi", "outside_range", [40, 60]))
    assert [i for i, v in enumerate(outside) if v] == [2, 4]


def test_range_operand_must_be_a_pair():
    with pytest.raises(RuleError):
        normalize_rule(condition("rsi", "in_range", 50))
    with pytest.raises(RuleError):
        normalize_rule(condition("rsi", "in_range", [1, 2, 3]))


def test_all_documented_operators_are_implementable():
    for name in OPERATOR_NAMES:
        right = [0, 100] if name in ("in_range", "outside_range") else 0
        normalize_rule(condition("rsi", name, right))


# --------------------------------------------------------------------------- #
# Logic
# --------------------------------------------------------------------------- #
def test_and_or_not():
    long = {
        "operator": "AND",
        "conditions": [
            {"left": "close", "operator": ">", "right": "vwap"},
            {"left": "rsi", "operator": "<", "right": 60},
        ],
    }
    assert [i for i, v in enumerate(series(long)) if v] == [1, 3]

    either = {
        "operator": "OR",
        "conditions": [
            {"left": "close", "operator": ">", "right": 11.5},
            {"left": "rsi", "operator": "<", "right": 40},
        ],
    }
    assert [i for i, v in enumerate(series(either)) if v] == [2, 4]

    negation = {
        "operator": "NOT",
        "conditions": [{"left": "close", "operator": ">", "right": 11.5}],
    }
    assert [i for i, v in enumerate(series(negation)) if v] == [0, 1, 3, 4, 5]


def test_nested_groups():
    nested = {
        "operator": "AND",
        "conditions": [
            {"left": "rsi", "operator": ">", "right": 40},
            {
                "operator": "OR",
                "conditions": [
                    {"left": "close", "operator": ">", "right": 11.5},
                    {"left": "close", "operator": "<", "right": 10.5},
                ],
            },
        ],
    }
    assert [i for i, v in enumerate(series(nested)) if v] == [2, 5]


def test_not_takes_exactly_one_condition():
    with pytest.raises(RuleError) as exc:
        normalize_rule({"operator": "NOT", "conditions": []})
    assert "exactly one" in str(exc.value)


def test_undisabled_condition_is_ignored_and_an_empty_group_never_fires():
    rule = {
        "operator": "AND",
        "conditions": [
            {"left": "close", "operator": ">", "right": 10.5, "enabled": False},
            {"left": "rsi", "operator": "<", "right": 60, "enabled": False},
        ],
    }
    assert not any(series(rule))
    problems = validate_rule(rule, list(FEATURES))
    assert any("never produce a signal" in p for p in problems)

    empty = {"operator": "AND", "conditions": []}
    assert not any(series(empty))


def test_or_group_with_one_disabled_condition_still_uses_the_others():
    rule = {
        "operator": "OR",
        "conditions": [
            {"left": "close", "operator": ">", "right": 11.5, "enabled": False},
            {"left": "close", "operator": "<", "right": 10.5},
        ],
    }
    assert [i for i, v in enumerate(series(rule)) if v] == [0, 4, 5]


# --------------------------------------------------------------------------- #
# Missing data
# --------------------------------------------------------------------------- #
def test_none_operands_are_false_never_zero():
    rule = condition("warming", ">", 0)
    result = series(rule)
    assert result[0] is False and result[1] is False
    assert result[2] is True


def test_crosses_is_false_on_the_first_bar():
    rule = condition("close", "crosses_above", 0)
    assert series(rule)[0] is False


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def test_unknown_feature_is_reported_and_rejected_at_evaluation():
    rule = condition("not_a_feature", ">", 1)
    assert unknown_features(rule, ["close"]) == ["not_a_feature"]
    problems = validate_rule(rule, ["close"])
    assert any("Unknown feature" in p for p in problems)
    with pytest.raises(RuleError):
        series(rule)


def test_unknown_operator_is_rejected():
    with pytest.raises(RuleError) as exc:
        normalize_rule(condition("close", "approximately", 1))
    assert "operator must be one of" in str(exc.value)


def test_missing_left_or_right_is_rejected():
    with pytest.raises(RuleError):
        normalize_rule({"operator": "AND", "conditions": [{"operator": ">"}]})
    with pytest.raises(RuleError):
        normalize_rule(condition("close", ">"))


def test_explicit_operand_forms_are_equivalent():
    plain = condition("rsi", ">", 50)
    explicit = {
        "operator": "AND",
        "conditions": [
            {"left": {"feature": "rsi"}, "operator": ">", "right": {"value": 50}}
        ],
    }
    assert series(plain) == series(explicit)


def test_none_rule_produces_no_signals():
    assert not any(evaluate_series(None, FEATURES, 6))
    assert evaluate_at(None, FEATURES, 0) is False


def test_excessive_nesting_is_rejected():
    rule: dict = {"operator": "AND", "conditions": []}
    node = rule
    for _ in range(20):
        child: dict = {"operator": "AND", "conditions": []}
        node["conditions"] = [child]
        node = child
    with pytest.raises(RuleError) as exc:
        normalize_rule(rule)
    assert "nesting" in str(exc.value)


def test_rules_are_not_executable_code():
    """A rule carrying code-like text must be treated as a feature name only."""
    rule = condition("__import__('os').system('echo pwned')", ">", 1)
    with pytest.raises(RuleError):
        series(rule)
    # And it must not have executed: the module simply does not resolve it.
    assert unknown_features(rule, ["close"]) == ["__import__('os').system('echo pwned')"]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def test_describe_rule_is_human_readable():
    rule = {
        "operator": "AND",
        "conditions": [
            {"left": "fisher", "operator": "crosses_above", "right": "signal"},
            {"left": "fisher", "operator": "<", "right": -1.0},
        ],
    }
    text = describe_rule(rule)
    assert "fisher crosses_above signal" in text
    assert "AND" in text


def test_normalised_rules_are_recognised():
    rule = condition("close", ">", 1)
    normalized = normalize_rule(rule)
    assert is_normalized(normalized)
    assert not is_normalized(rule)
    assert series(normalized) == series(rule)


def test_series_evaluation_is_identical_to_point_evaluation():
    rule = condition("rsi", "crosses_above", 50)
    normalized = normalize_rule(rule)
    assert series(rule) == [evaluate_at(normalized, FEATURES, i) for i in range(6)]
