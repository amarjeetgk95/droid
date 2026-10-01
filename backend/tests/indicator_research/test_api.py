"""API tests for the Indicator Research router."""

from __future__ import annotations

from typing import Any

import pytest

PREVIEW = "/api/v1/indicator-research/features"
BACKTEST = "/api/v1/indicator-research/backtest"
OPTIMIZE = "/api/v1/indicator-research/optimize"
WALKFORWARD = "/api/v1/indicator-research/walkforward"
COMPARE = "/api/v1/indicator-research/compare"
COMPARE_RULES = "/api/v1/indicator-research/compare-rules"
PREDICT = "/api/v1/indicator-research/predict"
EXPERIMENTS = "/api/v1/indicator-research/experiments"

DATA = {"instrument": "NIFTY", "timeframe": "5m"}
FISHER = {"indicator_id": "fisher", "params": {"length": 9}}
ATR = {"indicator_id": "atr", "params": {"length": 14}}
DEFAULT_RULES = {"use_indicator_defaults": True}


def body(indicators=None, rules=None, **extra) -> dict[str, Any]:
    payload: dict[str, Any] = {"data": DATA, "indicators": indicators or [FISHER]}
    if rules is not None:
        payload["rules"] = rules
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def test_indicators_endpoint_drives_the_ui(client):
    response = client.get("/api/v1/indicator-research/indicators")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 18
    ids = {item["id"] for item in payload["indicators"]}
    assert {"fisher", "stc", "ebsw", "rsi", "macd"} <= ids
    for item in payload["indicators"]:
        assert item["name"] and item["description"]
        assert isinstance(item["parameters"], list)
        assert isinstance(item["outputs"], list) and item["outputs"]
        for parameter in item["parameters"]:
            assert {"name", "type", "default"} <= set(parameter)
    assert payload["operators"] and payload["price_columns"]
    assert payload["research_only"] is True


def test_categories_report_counts(client):
    payload = client.get("/api/v1/indicator-research/indicators").json()
    categories = {c["id"]: c["count"] for c in payload["categories"]}
    assert categories["Momentum"] > 0
    assert categories["Cycle"] > 0
    assert categories["Trend"] > 0


def test_single_indicator_endpoint_includes_parameter_space(client):
    payload = client.get("/api/v1/indicator-research/indicators/fisher").json()
    assert payload["ok"] is True
    assert payload["metadata"]["id"] == "fisher"
    assert payload["parameter_space"]["length"]
    assert payload["default_rules"]["long"]


def test_unknown_indicator_is_404(client):
    response = client.get("/api/v1/indicator-research/indicators/nope")
    assert response.status_code == 404
    assert "Unknown indicator" in response.json()["detail"]


def test_catalog_and_isolation_endpoints(client):
    catalog = client.get("/api/v1/indicator-research/catalog").json()
    assert catalog["ok"] is True
    assert catalog["reference_costs"]["version"]
    assert {entry["id"] for entry in catalog["execution_models"]} == {"next_open", "signal_close"}
    isolation = client.get("/api/v1/indicator-research/isolation").json()
    assert isolation["isolated"] is True


# --------------------------------------------------------------------------- #
# Data availability honesty
# --------------------------------------------------------------------------- #
def test_missing_dataset_reports_a_reason_not_an_empty_success(client, empty_store):
    response = client.post(BACKTEST, json=body(rules=DEFAULT_RULES))
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert "No stored" in payload["error"]
    assert "versions on disk: none" in payload["error"]
    assert payload["data"]["available"] is False
    assert payload["data"]["availability"] == "dataset_missing"


def test_unknown_instrument_is_not_silently_substituted(client, empty_store):
    payload = client.post(
        BACKTEST, json={"data": {"instrument": "MIDCAP", "timeframe": "5m"}, "indicators": [FISHER], "rules": DEFAULT_RULES}
    ).json()
    assert payload["ok"] is False
    assert "MIDCAP" in payload["error"]


def test_empty_range_reports_no_candles(client, dataset):
    payload = client.post(
        BACKTEST,
        json=body(rules=DEFAULT_RULES, data={**DATA, "start": "2030-01-01", "end": "2030-01-31"}),
    ).json()
    assert payload["ok"] is False
    assert "no candles" in payload["error"].lower()


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #
def test_preview_returns_candles_and_aligned_outputs(client, dataset):
    payload = client.post(PREVIEW, json=body(rules=DEFAULT_RULES)).json()
    assert payload["ok"] is True, payload.get("error")
    assert len(payload["candles"]) == 400
    assert payload["outputs"]["fisher"]
    assert len(payload["outputs"]["fisher"]) == len(payload["candles"])
    assert payload["candles"][0]["index"] == 0
    assert payload["rule_summary"]["long"]
    assert payload["pane_map"]["fisher"]["outputs"]["fisher"]["pane"] == "separate"


def test_preview_window_is_applied_for_long_series(client, dataset):
    payload = client.post(PREVIEW, json=body(rules=DEFAULT_RULES, preview_bars=200)).json()
    assert payload["ok"] is True
    assert payload["window"]["bars"] <= 200
    assert len(payload["candles"]) == payload["window"]["bars"]


def test_preview_reports_a_draft_rule_referencing_a_missing_feature(client, dataset):
    draft = {
        "long": {"operator": "AND", "conditions": [{"left": "nonexistent", "operator": ">", "right": 1}]}
    }
    payload = client.post(PREVIEW, json=body(rules=draft)).json()
    assert payload["ok"] is True
    assert payload["rule_problems"]["long"]
    assert any("nonexistent" in warning for warning in payload["warnings"])
    assert payload["signals"]["long"] == []


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #
def test_backtest_runs_and_reports_validation(client, dataset):
    payload = client.post(BACKTEST, json=body(rules=DEFAULT_RULES)).json()
    assert payload["ok"] is True, payload.get("error")
    assert payload["bars"] == 400
    assert payload["validation"]["no_lookahead"] is True
    assert payload["validation"]["badge"].startswith("✓")
    assert payload["metrics"]["n_trades"] >= 0
    assert payload["cost_summary"]["cost_model"]["version"]
    assert payload["assumptions"]
    assert payload["data"]["available"] is True


def test_backtest_never_opens_before_the_signal(client, dataset):
    payload = client.post(
        BACKTEST, json=body(rules=DEFAULT_RULES, settings={"execution": {"entry_fill": "next_open"}})
    ).json()
    assert payload["ok"] is True
    for trade in payload.get("trades", []):
        assert trade["entry_index"] == trade["signal_index"] + 1


def test_overlay_indicators_extend_the_feature_set(client, dataset):
    payload = client.post(
        BACKTEST,
        json=body(
            indicators=[FISHER, ATR],
            rules=DEFAULT_RULES,
            settings={"exits": {"stop_mode": "atr", "stop_value": 2.0}},
        ),
    ).json()
    assert payload["ok"] is True, payload.get("error")
    assert payload["feature_build"]["owners"]["atr"] == "atr"
    for trade in payload["trades"]:
        assert trade["stop_price"] is not None


def test_atr_stop_without_an_atr_feature_is_refused(client, dataset):
    payload = client.post(
        BACKTEST, json=body(rules=DEFAULT_RULES, settings={"exits": {"stop_mode": "atr", "stop_value": 2.0}})
    ).json()
    assert payload["ok"] is False
    assert "ATR" in payload["error"]


def test_missing_rule_is_422_so_no_default_is_invented(client, dataset):
    response = client.post(BACKTEST, json=body())
    assert response.status_code == 422
    assert "No signal rule" in response.json()["detail"]


def test_rule_referencing_an_absent_feature_is_422(client, dataset):
    rules = {"long": {"operator": "AND", "conditions": [{"left": "vwap", "operator": ">", "right": 1}]}}
    response = client.post(BACKTEST, json=body(rules=rules))
    assert response.status_code == 422
    assert "vwap" in response.json()["detail"]


def test_vwap_rule_works_once_the_overlay_is_added(client, dataset):
    rules = {"long": {"operator": "AND", "conditions": [{"left": "close", "operator": ">", "right": "vwap"}]}}
    payload = client.post(
        BACKTEST, json=body(indicators=[FISHER, {"indicator_id": "vwap", "params": {"window": 0}}], rules=rules)
    ).json()
    assert payload["ok"] is True, payload.get("error")


def test_unknown_setting_key_is_422_not_silently_defaulted(client, dataset):
    response = client.post(BACKTEST, json=body(rules=DEFAULT_RULES, settings={"exits": {"stopMode": "atr"}}))
    assert response.status_code == 422
    assert "stopMode" in response.json()["detail"]


def test_unknown_indicator_in_the_request_is_reported(client, dataset):
    payload = client.post(BACKTEST, json=body(indicators=[{"indicator_id": "nope"}], rules=DEFAULT_RULES)).json()
    assert payload["ok"] is False
    assert "nope" in payload["error"]


def test_extra_request_field_is_rejected(client, dataset):
    response = client.post(BACKTEST, json=body(rules=DEFAULT_RULES, nonsense=True))
    assert response.status_code == 422


def test_zero_costs_option_changes_only_the_net_figure(client, dataset):
    # Fixed units, so the position size does not move with the fill price and
    # gross P&L is comparable between the two runs.
    units = {"execution": {"size_mode": "fixed_units", "fixed_units": 1}}
    with_costs = client.post(BACKTEST, json=body(rules=DEFAULT_RULES, settings=units)).json()
    without = client.post(
        BACKTEST,
        json=body(
            rules=DEFAULT_RULES,
            settings={
                **units,
                "costs": {
                    "slippage_bps": 0,
                    "brokerage_bps": 0,
                    "exchange_bps": 0,
                    "sebi_bps": 0,
                    "gst_on_fees_pct": 0,
                    "stt_sell_bps": 0,
                    "stamp_buy_bps": 0,
                }
            },
        ),
    ).json()
    assert with_costs["metrics"]["total_costs"] > 0
    assert without["metrics"]["total_costs"] == 0
    assert with_costs["metrics"]["gross_profit_before_costs"] == without["metrics"]["gross_profit_before_costs"]


def test_absurd_cost_value_is_refused(client, dataset):
    response = client.post(BACKTEST, json=body(rules=DEFAULT_RULES, settings={"costs": {"slippage_bps": 5000}}))
    assert response.status_code == 422
    assert "unit error" in response.json()["detail"]


def test_regime_and_time_of_day_analysis_are_present(client, dataset):
    payload = client.post(BACKTEST, json=body(rules=DEFAULT_RULES)).json()
    assert isinstance(payload["by_regime"], dict)
    assert isinstance(payload["by_time_of_day"], dict)
    assert isinstance(payload["by_side"], dict)


def test_equity_curve_can_be_thinned(client, dataset):
    payload = client.post(BACKTEST, json=body(rules=DEFAULT_RULES, max_equity_points=50, include_trades=False)).json()
    assert payload["ok"] is True
    assert "trades" not in payload
    assert len(payload["equity_curve"]) <= 51


# --------------------------------------------------------------------------- #
# Optimize / walk-forward / compare
# --------------------------------------------------------------------------- #
def test_optimize_returns_ranked_in_sample_rows(client, dataset):
    payload = client.post(
        OPTIMIZE,
        json=body(rules=DEFAULT_RULES, max_combinations=6, min_trades=1, objective="total_return_pct"),
    ).json()
    assert payload["ok"] is True, payload.get("error")
    assert payload["in_sample_only"] is True
    assert payload["causality_verified"] is False
    assert payload["combinations_evaluated"] <= 6
    assert payload["parameter_space"]["length"]
    assert any("In-sample only" in w for w in payload["warnings"])


def test_optimize_rejects_an_unknown_objective(client, dataset):
    response = client.post(OPTIMIZE, json=body(rules=DEFAULT_RULES, objective="vibes"))
    assert response.status_code == 422


def test_walkforward_reports_leakage_audit(client, dataset):
    payload = client.post(WALKFORWARD, json=body(rules=DEFAULT_RULES, folds=3, max_combinations=3, min_trades=1)).json()
    assert payload["ok"] is True, payload.get("error")
    assert payload["leakage_audit"]["chronological"] is True
    assert payload["leakage_audit"]["no_shuffle"] is True
    assert isinstance(payload["fold_reports"], list) and payload["fold_reports"]


def test_walkforward_refuses_a_range_that_is_too_short(client, dataset):
    response = client.post(
        WALKFORWARD,
        json=body(rules=DEFAULT_RULES, folds=20, data={**DATA, "start": "2026-01-05", "end": "2026-01-05"}),
    )
    assert response.status_code == 422


def test_compare_ranks_indicators_and_states_its_caveats(client, dataset):
    payload = client.post(
        COMPARE,
        json={
            "data": DATA,
            "indicator_ids": ["fisher", "rsi", "macd"],
            "rules": DEFAULT_RULES,
            "use_default_rules": True,
        },
    ).json()
    assert payload["ok"] is True, payload.get("error")
    assert payload["objective"]
    assert payload["rows"]
    assert payload["warnings"]
    for row in payload["rows"]:
        assert "indicator_id" in row


def test_compare_needs_at_least_two_indicators(client, dataset):
    response = client.post(COMPARE, json={"data": DATA, "indicator_ids": ["fisher"]})
    assert response.status_code == 422


def test_compare_reports_an_indicator_without_directional_defaults_as_not_comparable(client, dataset):
    payload = client.post(
        COMPARE,
        json={"data": DATA, "indicator_ids": ["fisher", "atr"], "use_default_rules": True},
    ).json()
    atr_row = next(row for row in payload["rows"] if row["indicator_id"] == "atr")
    assert atr_row["comparable"] is False
    assert "no default signal rule" in atr_row["reason"]


def test_compare_rules_measures_the_spread_across_definitions(client, dataset):
    payload = client.post(
        COMPARE_RULES,
        json={
            "data": DATA,
            "indicator_id": "fisher",
            "rule_sets": [
                {
                    "label": "cross both ways",
                    "long": {"operator": "AND", "conditions": [{"left": "fisher", "operator": "crosses_above", "right": "signal"}]},
                    "short": {"operator": "AND", "conditions": [{"left": "fisher", "operator": "crosses_below", "right": "signal"}]},
                },
                {
                    "label": "extremes only",
                    "long": {"operator": "AND", "conditions": [{"left": "fisher", "operator": "<", "right": -1.5}]},
                    "short": {"operator": "AND", "conditions": [{"left": "fisher", "operator": ">", "right": 1.5}]},
                },
            ],
        },
    ).json()
    assert payload["ok"] is True, payload.get("error")
    assert len(payload["rows"]) == 2
    assert payload["spread"]["n"] >= 1


# --------------------------------------------------------------------------- #
# Prediction analysis
# --------------------------------------------------------------------------- #
def test_predict_reports_horizons_with_an_unconditional_baseline(client, dataset):
    payload = client.post(PREDICT, json=body(rules=DEFAULT_RULES, horizons=[1, 3, 5])).json()
    assert payload["ok"] is True, payload.get("error")
    study = payload["studies"]["long"]
    assert study["signal_definition"]
    assert set(study["horizons"]) == {"1", "3", "5"}
    for horizon in study["horizons"].values():
        assert "unconditional" in horizon
        assert "signal" in horizon
        assert horizon["signal"]["n"] >= 0
    for field in ("instrument", "timeframe", "date_range", "costs_applied", "sample_status"):
        assert field in study


def test_predict_states_the_overlap_caveat_for_multi_bar_horizons(client, dataset):
    payload = client.post(PREDICT, json=body(rules=DEFAULT_RULES, horizons=[1, 5])).json()
    assert payload["studies"]["long"]["horizons"]["1"]["overlapping_windows"] is False
    assert payload["studies"]["long"]["horizons"]["5"]["overlapping_windows"] is True


def test_predict_rejects_an_empty_horizon_list(client, dataset):
    response = client.post(PREDICT, json=body(rules=DEFAULT_RULES, horizons=[0]))
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Experiments
# --------------------------------------------------------------------------- #
def _experiment_payload() -> dict[str, Any]:
    return {
        "name": "NIFTY 5m Fisher length 9",
        "notes": "first pass",
        "tags": ["momentum"],
        "config": {
            "instrument": "NIFTY",
            "timeframe": "5m",
            "date_range": {"start": "2026-01-05"},
            "indicators": [{"indicator_id": "fisher", "params": {"length": 9}}],
            "rules": {"long": {"operator": "AND", "conditions": []}},
            "settings": {"execution": {"entry_fill": "next_open"}},
        },
        "result_summary": {"n_trades": 12, "total_return_pct": 4.2, "max_drawdown_pct": 1.1},
        "validation": {"no_lookahead": True, "repaint_free": True, "badge": "NO LOOKAHEAD", "scope": "full_recompute"},
    }


def test_experiment_round_trip(client):
    saved = client.post(EXPERIMENTS, json=_experiment_payload()).json()["experiment"]
    assert saved["id"].startswith("exp_")
    assert saved["name"] == "NIFTY 5m Fisher length 9"
    assert saved["indicator_id"] == "fisher"

    listed = client.get(EXPERIMENTS).json()
    assert any(item["id"] == saved["id"] for item in listed["experiments"])

    fetched = client.get(f"{EXPERIMENTS}/{saved['id']}").json()["experiment"]
    assert fetched["config"]["indicators"][0]["params"]["length"] == 9

    renamed = client.patch(f"{EXPERIMENTS}/{saved['id']}", json={"name": "renamed", "notes": "v2"}).json()
    assert renamed["experiment"]["name"] == "renamed"
    assert renamed["experiment"]["notes"] == "v2"

    assert client.delete(f"{EXPERIMENTS}/{saved['id']}").json()["deleted"] == saved["id"]
    assert client.get(f"{EXPERIMENTS}/{saved['id']}").status_code == 404


def test_experiment_default_name_is_suggested_when_omitted(client):
    payload = _experiment_payload()
    payload.pop("name")
    saved = client.post(EXPERIMENTS, json=payload).json()["experiment"]
    assert "NIFTY" in saved["name"] and "fisher" in saved["name"]


def test_experiment_export_as_csv_and_json(client):
    saved = client.post(EXPERIMENTS, json=_experiment_payload()).json()["experiment"]
    csv_response = client.get(f"{EXPERIMENTS}/{saved['id']}/export?format=csv")
    assert csv_response.status_code == 200
    text = csv_response.text
    assert "section,key,value" in text
    assert "total_return_pct" in text
    assert "no_lookahead" in text
    json_response = client.get(f"{EXPERIMENTS}/{saved['id']}/export?format=json")
    assert json_response.status_code == 200
    assert json_response.json()["id"] == saved["id"]


def test_experiment_export_format_is_validated(client):
    saved = client.post(EXPERIMENTS, json=_experiment_payload()).json()["experiment"]
    assert client.get(f"{EXPERIMENTS}/{saved['id']}/export?format=xlsx").status_code == 422


def test_experiment_id_cannot_escape_the_storage_directory(client):
    # Traversal attempts must not resolve to a readable path.
    assert client.get(f"{EXPERIMENTS}/..%2F..%2Fsecrets").status_code == 404
    assert client.get(f"{EXPERIMENTS}/a/b").status_code == 404


def test_deleting_an_unknown_experiment_is_404(client):
    assert client.delete(f"{EXPERIMENTS}/exp_missing").status_code == 404


def test_experiment_requires_a_config(client):
    assert client.post(EXPERIMENTS, json={"config": {}}).status_code == 422


# --------------------------------------------------------------------------- #
# Canonical Presets, Selectivity, Robustness, Ablation endpoints
# --------------------------------------------------------------------------- #
def test_presets_api(client):
    res = client.get("/api/v1/indicator-research/presets")
    assert res.status_code == 200
    presets = res.json()["presets"]
    assert len(presets) == 6

    single = client.get("/api/v1/indicator-research/presets/ehlers_cycle_reversal")
    assert single.status_code == 200
    assert single.json()["preset"]["name"] == "Ehlers Cycle Reversal (Fisher 9 + EBSW)"

    unknown = client.get("/api/v1/indicator-research/presets/non_existent")
    assert unknown.status_code == 404


def test_selectivity_endpoint(client, dataset):
    payload = {
        "data": DATA,
        "indicators": [FISHER],
        "feature": "fisher",
        "operator": ">",
        "thresholds": [-1.0, 0.0, 1.0],
        "direction": "long",
    }
    res = client.post("/api/v1/indicator-research/selectivity", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["rows"]) == 3
    assert "optimal_point" in data


def test_robustness_endpoint(client, dataset):
    payload = {
        "data": DATA,
        "indicators": [FISHER],
        "rules": {
            "long": {
                "operator": "AND",
                "conditions": [{"left": "fisher", "operator": "crosses_above", "right": -1.5}],
            },
            "short": {
                "operator": "AND",
                "conditions": [{"left": "fisher", "operator": "crosses_below", "right": 1.5}],
            },
        },
        "perturbation_pcts": [-0.10, 0.10],
        "cost_multipliers": [1.0, 1.5],
    }
    res = client.post("/api/v1/indicator-research/robustness", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["verdict"] in ("ROBUST", "MODERATELY_FRAGILE", "HIGHLY_FRAGILE")
    assert len(data["cost_stress_results"]) == 2


def test_ablation_endpoint(client, dataset):
    ebsw = {"indicator_id": "ebsw", "params": {"hp_period": 48, "ssf_period": 10}}
    payload = {
        "data": DATA,
        "indicators": [FISHER, ebsw],
        "rules": {
            "long": {
                "operator": "AND",
                "conditions": [
                    {"left": "fisher", "operator": "crosses_above", "right": -1.5},
                    {"left": "ebsw", "operator": "turns_up"},
                ],
            },
            "short": {
                "operator": "AND",
                "conditions": [
                    {"left": "fisher", "operator": "crosses_below", "right": 1.5},
                    {"left": "ebsw", "operator": "turns_down"},
                ],
            },
        },
    }
    res = client.post("/api/v1/indicator-research/ablation", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert len(data["ablations"]) == 2


def test_optimize_random_search_api(client, dataset):
    payload = {
        "data": DATA,
        "indicators": [FISHER],
        "rules": DEFAULT_RULES,
        "search_mode": "random",
        "seed": 42,
        "max_combinations": 5,
        "min_trades": 1,
    }
    res = client.post("/api/v1/indicator-research/optimize", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["search_mode"] == "random"
    assert "multiple_testing_penalty" in data

