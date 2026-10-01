# DROID Indicator Research: Baseline Test Suite

**Baseline Date:** 2026-09-30  
**Baseline Test Count:** 167 tests  
**Status:** All 167 passing in 6.84s  
**Rule:** Existing tests MUST NOT be edited, skipped, or weakened to make new code pass. After every implementation phase, the full regression suite must pass with $\ge 167$ tests.

---

## Registered Baseline Tests (167)

### `tests/indicator_research/test_api.py` (22 tests)
- `test_list_indicators_returns_registered_metadata`
- `test_get_one_indicator_metadata`
- `test_unknown_indicator_returns_404`
- `test_catalog_returns_configured_instruments_and_timeframes`
- `test_isolation_endpoint_asserts_guarantee`
- `test_features_endpoint_returns_candles_and_primary_outputs`
- `test_features_endpoint_refuses_empty_indicator_list`
- `test_features_endpoint_refuses_unknown_indicator`
- `test_features_endpoint_refuses_unknown_parameters`
- `test_features_endpoint_handles_unavailable_data_honestly`
- `test_backtest_runs_and_returns_causal_result`
- `test_backtest_with_indicator_defaults`
- `test_backtest_rejects_unknown_feature_in_rules`
- `test_optimize_runs_grid_and_ranks_candidates`
- `test_walkforward_runs_sequential_windows`
- `test_compare_runs_multiple_indicators_through_one_harness`
- `test_compare_rules_ranks_alternative_definitions`
- `test_predict_reports_forward_returns_and_baselines`
- `test_experiment_lifecycle_save_list_read_rename_delete`
- `test_experiment_export_csv`
- `test_experiment_export_json`
- `test_experiment_export_markdown`

### `tests/indicator_research/test_causality.py` (9 tests)
- `test_every_shipped_indicator_is_strictly_causal_prefix_invariant`
- `test_causality_holds_across_multiple_cut_points`
- `test_every_rule_operator_is_strictly_causal`
- `test_rule_evaluation_is_prefix_invariant`
- `test_known_lookahead_indicator_is_detected_by_the_fixture`
- `test_indicator_feature_builder_preserves_prefix_invariance`
- `test_backtest_signals_are_strictly_causal`
- `test_prediction_forward_windows_do_not_leak_into_signals`
- `test_randomized_future_bars_cannot_alter_past_features`

### `tests/indicator_research/test_engine.py` (37 tests)
- `test_empty_rules_produce_no_trades`
- `test_signal_close_vs_next_open_execution_timing`
- `test_entry_fill_at_next_open_fills_at_the_open`
- `test_stop_loss_triggers_intrabar_on_the_entry_bar`
- `test_take_profit_triggers_intrabar`
- `test_a_gap_through_the_stop_fills_at_the_open_not_the_stop`
- `test_stop_is_assumed_hit_before_target_when_a_bar_contains_both`
- `test_max_bars_held_closes_at_the_close`
- `test_end_of_data_closes_an_open_position`
- `test_opposite_signal_exits_at_the_next_open`
- `test_disabling_a_side_suppresses_its_signals`
- `test_costs_are_charged_separately_from_gross_pnl`
- `test_zero_costs_produce_equal_gross_and_net`
- `test_cost_summary_separates_gross_and_net`
- `test_a_tighter_slippage_assumption_moves_the_result`
- `test_gross_is_identical_regardless_of_costs`
- `test_fixed_fraction_sizing_scales_with_equity`
- `test_equity_curve_is_one_point_per_bar_and_tracks_position_state`
- `test_losing_trade_produces_the_expected_drawdown`
- `test_mae_and_mfe_record_the_excursion_in_both_directions`
- `test_no_new_position_can_open_on_the_bar_that_closed_one`
- `test_signals_inside_the_warmup_window_are_suppressed`
- `test_trades_never_enter_before_the_warmup_bar`
- `test_structural_checks_pass_on_a_real_run`
- `test_structural_checks_detect_a_broken_fill_model`
- `test_validation_badge_is_earned_not_assumed`
- `test_short_series_withholds_the_badge`
- `test_atr_stops_refuse_to_run_without_an_atr_feature`
- `test_atr_stops_run_when_the_feature_is_supplied`
- `test_unknown_feature_fails_the_run_instead_of_producing_no_signals`
- `test_empty_candle_series_is_an_explicit_failure`
- `test_output_length_mismatch_is_refused`
- `test_output_named_like_a_price_column_is_refused`
- `test_unknown_entry_fill_is_refused`
- `test_negative_allocation_is_refused`
- `test_no_signal_produces_an_honest_empty_result`
- `test_backtest_preserves_position_state_cleanly`

### `tests/indicator_research/test_indicator_math.py` (36 tests)
- `test_sma_matches_hand_calculation`
- `test_sma_restarts_after_a_gap`
- `test_ema_is_seeded_on_the_sma`
- `test_wilder_smoothing_recursion`
- `test_stdev_is_population_deviation`
- `test_highest_and_lowest_windows`
- `test_linreg_slope_of_a_perfect_line`
- `test_true_range_includes_the_previous_close`
- `test_atr_is_wilder_smoothed_true_range`
- `test_vwap_uses_typical_price_and_volume`
- `test_registry_discovers_every_shipped_indicator`
- `test_every_indicator_declares_coherent_metadata`
- `test_every_indicator_computes_on_a_real_series`
- `test_outputs_are_never_zero_filled_during_warmup`
- `test_sma_indicator_matches_the_helper`
- `test_rsi_on_a_monotonic_rise_is_one_hundred`
- `test_rsi_on_a_monotonic_fall_is_zero`
- `test_macd_equals_the_difference_of_its_emas`
- `test_bollinger_bands_are_symmetric_around_the_middle`
- `test_williams_r_bounds_and_orientation`
- `test_donchian_channel_brackets_price`
- `test_supertrend_direction_is_plus_or_minus_one`
- `test_adx_is_bounded_and_positive`
- `test_ebsw_wave_is_normalised_into_minus_one_to_one`
- `test_mama_alpha_respects_the_configured_limits`
- `test_dominant_cycle_stays_inside_the_requested_band`
- `test_stc_is_bounded_zero_to_one_hundred`
- `test_unknown_parameters_are_rejected`
- `test_parameters_are_clamped_into_their_declared_range`
- `test_parameters_are_coerced_to_their_declared_type`
- `test_choice_parameters_reject_values_outside_their_options`
- `test_undeclared_outputs_are_a_hard_error`
- `test_output_length_must_match_the_candle_series`
- `test_concrete_indicators_must_declare_metadata`
- `test_adding_an_indicator_file_is_enough`
- `test_nan_and_inf_handling_in_math_helpers`

### `tests/indicator_research/test_rules.py` (33 tests)
- `test_comparison_operators[>-10.5-expected_indexes0]`
- `test_comparison_operators[<-10.5-expected_indexes1]`
- `test_comparison_operators[>=-10.0-expected_indexes2]`
- `test_comparison_operators[<=-10.0-expected_indexes3]`
- `test_comparison_operators[==-10.0-expected_indexes4]`
- `test_comparison_operators[!=-10.0-expected_indexes5]`
- `test_crosses_above_is_strict_and_needs_a_previous_bar`
- `test_crosses_below_is_strict`
- `test_crosses_treats_equal_previous_as_crossing`
- `test_turns_up_requires_a_strict_trough`
- `test_turns_down_requires_a_strict_peak`
- `test_slope_operators_read_the_requested_lag`
- `test_in_and_outside_range`
- `test_range_operand_must_be_a_pair`
- `test_all_documented_operators_are_implementable`
- `test_and_or_not`
- `test_nested_groups`
- `test_not_takes_exactly_one_condition`
- `test_undisabled_condition_is_ignored_and_an_empty_group_never_fires`
- `test_or_group_with_one_disabled_condition_still_uses_the_others`
- `test_none_operands_are_false_never_zero`
- `test_crosses_is_false_on_the_first_bar`
- `test_unknown_feature_is_reported_and_rejected_at_evaluation`
- `test_unknown_operator_is_rejected`
- `test_missing_left_or_right_is_rejected`
- `test_explicit_operand_forms_are_equivalent`
- `test_none_rule_produces_no_signals`
- `test_excessive_nesting_is_rejected`
- `test_rules_are_not_executable_code`
- `test_describe_rule_is_human_readable`
- `test_normalised_rules_are_recognised`
- `test_series_evaluation_is_identical_to_point_evaluation`
- `test_complex_conjunction_evaluation`

### `tests/indicator_research/test_safety.py` (9 tests)
- `test_the_real_package_never_reaches_live_trading`
- `test_isolation_report_states_the_guarantee`
- `test_a_forbidden_import_is_detected`
- `test_a_forbidden_import_inside_a_nested_package_is_detected`
- `test_a_plain_submodule_import_is_detected`
- `test_an_order_placement_call_is_detected`
- `test_assertion_raises_on_a_violation`
- `test_forbidden_prefixes_cover_the_order_paths`
- `test_the_api_module_does_not_import_broker_code`
