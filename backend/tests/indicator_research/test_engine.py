"""Engine tests against hand-calculated prices.

Every scenario here has a single arithmetic answer that can be worked out on
paper. That is deliberate: the build order says the engine must be validated
against manually calculated cases *before* optimization is allowed, and a
targeted 5-bar fixture is the only way to see an off-by-one-bar fill, a slipped
stop, or a double-charged cost.
"""

from __future__ import annotations

import pytest

from app.indicator_research.backtesting.costs import REFERENCE_COSTS_V1, ZERO_COSTS, CostModel
from app.indicator_research.backtesting.engine import BacktestEngine
from app.indicator_research.backtesting.models import (
    BacktestSettings,
    ExecutionSettings,
    ExitSettings,
)
from app.indicator_research.backtesting.validation import structural_checks
from tests.indicator_research.conftest import build_candles

LONG_ABOVE_100 = {
    "operator": "AND",
    "conditions": [{"left": "close", "operator": "crosses_above", "right": 100}],
}
SHORT_BELOW_100 = {
    "operator": "AND",
    "conditions": [{"left": "close", "operator": "crosses_below", "right": 100}],
}

# Signal fires on bar 1 (close 100.5 crosses above 100 from 99).
BASE_ROWS = [
    (99.0, 100.0, 98.0, 99.0),
    (99.5, 101.0, 99.0, 100.5),
    (101.0, 102.0, 100.5, 101.5),
    (101.5, 103.0, 101.0, 102.5),
    (102.5, 103.0, 102.0, 102.5),
]


def settings(
    *,
    units: float = 1.0,
    capital: float = 100_000.0,
    costs: CostModel = ZERO_COSTS,
    **exits,
) -> BacktestSettings:
    return BacktestSettings(
        execution=ExecutionSettings(
            entry_fill="next_open",
            size_mode="fixed_units",
            fixed_units=units,
            initial_capital=capital,
        ),
        exits=ExitSettings(**exits),
        costs=costs,
    )


def run(rows=BASE_ROWS, *, long_rule=LONG_ABOVE_100, short_rule=None, cfg=None, warmup=0, features=None):
    candles = build_candles(rows)
    # Only the extra feature columns: the engine adds the price columns itself
    # and refuses a feature map that tries to redefine them.
    return BacktestEngine().run(
        candles=candles,
        features=dict(features or {}),
        long_rule=long_rule,
        short_rule=short_rule,
        settings=cfg or settings(max_bars_held=1),
        timeframe="5m",
        warmup_bars=warmup,
    )


# --------------------------------------------------------------------------- #
# Execution model
# --------------------------------------------------------------------------- #
def test_entry_is_the_next_bar_open_and_pnl_matches_hand_arithmetic():
    result = run()
    assert result.ok, result.error
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side == "LONG"
    assert trade.signal_index == 1, "signal must be attributed to the bar that produced it"
    assert trade.entry_index == 2, "next_open means entry on the following bar"
    assert trade.entry_price == pytest.approx(101.0)
    assert trade.exit_index == 3
    assert trade.exit_price == pytest.approx(102.5)
    assert trade.exit_reason == "max_bars"
    assert trade.bars_held == 1
    # (102.5 - 101.0) * 1 unit = 1.5
    assert trade.gross_pnl == pytest.approx(1.5)
    assert trade.costs == pytest.approx(0.0)
    assert trade.net_pnl == pytest.approx(1.5)
    assert trade.equity_after == pytest.approx(100_001.5)


def test_signal_close_fill_is_flagged_and_fills_on_the_signal_bar():
    cfg = settings(max_bars_held=1)
    cfg.execution.entry_fill = "signal_close"
    result = run(cfg=cfg)
    trade = result.trades[0]
    assert trade.entry_index == trade.signal_index == 1
    assert trade.entry_price == pytest.approx(100.5)  # the signal bar's close
    assert any("optimistic fill model" in a for a in result.assumptions)


def test_a_signal_on_the_final_bar_never_fills():
    # Only bars 0 and 1 present, signal at the last bar -> no next open exists.
    rows = BASE_ROWS[:2]
    result = run(rows, cfg=settings())
    assert result.ok
    assert result.trades == []
    assert result.signals["long"] == [1]


def test_short_entries_mirror_long_entries():
    rows = [
        (101.0, 102.0, 100.0, 101.0),
        (100.5, 101.0, 99.5, 99.5),  # close crosses below 100
        (99.5, 100.0, 98.5, 99.0),
        (99.0, 99.5, 97.0, 97.5),
        (97.5, 98.0, 97.0, 97.5),
    ]
    result = run(rows, long_rule=None, short_rule=SHORT_BELOW_100)
    trade = result.trades[0]
    assert trade.side == "SHORT"
    assert trade.entry_index == 2
    assert trade.entry_price == pytest.approx(99.5)
    assert trade.exit_price == pytest.approx(97.5)
    # Short gains when price falls: (99.5 - 97.5) * 1 = 2.0
    assert trade.gross_pnl == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# Exits
# --------------------------------------------------------------------------- #
def test_stop_loss_triggers_intrabar_on_the_entry_bar():
    rows = list(BASE_ROWS)
    rows[2] = (101.0, 102.0, 99.5, 101.0)  # entry still at 101, low pierces the 100 stop
    result = run(rows, cfg=settings(stop_mode="points", stop_value=1.0))
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(100.0)
    assert trade.exit_index == 2
    assert trade.bars_held == 0
    assert trade.gross_pnl == pytest.approx(-1.0)


def test_take_profit_triggers_intrabar():
    rows = list(BASE_ROWS)
    rows[3] = (101.5, 103.0, 100.5, 102.5)
    result = run(rows, cfg=settings(target_mode="points", target_value=1.0))
    trade = result.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(102.0)
    assert trade.gross_pnl == pytest.approx(1.0)


def test_a_gap_through_the_stop_fills_at_the_open_not_the_stop():
    rows = list(BASE_ROWS)
    rows[3] = (99.0, 101.0, 98.0, 100.0)  # opens below the 100 stop
    result = run(rows, cfg=settings(stop_mode="points", stop_value=1.0))
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(99.0), "the open is the only tradeable price"
    assert trade.gross_pnl == pytest.approx(-2.0), "worse than the stop level, as in reality"


def test_stop_is_assumed_hit_before_target_when_a_bar_contains_both():
    rows = list(BASE_ROWS)
    # The entry bar must not touch the target, or the position closes there first.
    rows[2] = (101.0, 101.5, 100.5, 101.0)
    rows[3] = (101.5, 103.0, 99.0, 101.0)  # range covers stop 100 and target 102
    result = run(rows, cfg=settings(stop_mode="points", stop_value=1.0, target_mode="points", target_value=1.0))
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(100.0)
    assert any("stop is assumed to have been hit first" in a for a in result.assumptions)


def test_max_bars_held_closes_at_the_close():
    # Entry at bar 2, so a 2-bar time stop closes at the close of bar 4.
    rows = BASE_ROWS + [(103.0, 104.0, 102.0, 103.5)]
    result = run(rows, cfg=settings(max_bars_held=2))
    trade = result.trades[0]
    assert trade.exit_reason == "max_bars"
    assert trade.entry_index == 2
    assert trade.exit_index == 4
    assert trade.exit_price == pytest.approx(BASE_ROWS[4][3])
    assert trade.bars_held == 2


def test_end_of_data_closes_an_open_position():
    rows = BASE_ROWS[:4]  # no time stop, so the trade is still open at the end
    result = run(rows, cfg=settings())
    trade = result.trades[0]
    assert trade.exit_reason == "end_of_data"
    assert trade.exit_index == 3
    assert trade.exit_price == pytest.approx(102.5)


def test_opposite_signal_exits_at_the_next_open():
    rows = list(BASE_ROWS)
    # Bar 3 closes at 99.5, crossing below 100 -> exit at bar 4's open.
    rows[3] = (101.5, 102.0, 99.0, 99.5)
    rows[4] = (99.0, 100.0, 98.0, 99.0)
    result = run(rows, short_rule=SHORT_BELOW_100, cfg=settings())
    trade = result.trades[0]
    assert trade.exit_reason == "opposite_signal"
    assert trade.exit_index == 4
    assert trade.exit_price == pytest.approx(99.0)


def test_disabling_a_side_suppresses_its_signals():
    rows = [
        (101.0, 102.0, 100.0, 101.0),
        (100.5, 101.0, 99.5, 99.5),  # closes below 100 -> short signal
        (99.5, 100.0, 98.5, 99.0),
        (99.0, 99.5, 97.0, 97.5),
        (97.5, 98.0, 97.0, 97.5),
    ]
    result = run(rows, long_rule=None, short_rule=SHORT_BELOW_100, cfg=settings(allow_short=False))
    assert result.ok, result.error
    assert result.signals["short"] == []
    assert result.trades == []


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #
def test_costs_are_charged_separately_from_gross_pnl():
    cfg = settings(costs=REFERENCE_COSTS_V1, max_bars_held=1)
    result = run(cfg=cfg)
    trade = result.trades[0]
    assert trade.gross_pnl == pytest.approx(1.5), "gross is measured at reference prices"
    assert trade.costs > 0
    assert trade.net_pnl == pytest.approx(trade.gross_pnl - trade.costs)
    # Slippage pushes the entry fill above the reference price and the exit below.
    assert trade.entry_price > trade.entry_reference_price
    assert trade.exit_price < trade.exit_reference_price
    expected_entry = 101.0 * (1 + REFERENCE_COSTS_V1.slippage_bps / 10_000)
    assert trade.entry_price == pytest.approx(expected_entry, rel=1e-9)


def test_zero_costs_produce_equal_gross_and_net():
    result = run(cfg=settings(costs=ZERO_COSTS, max_bars_held=1))
    trade = result.trades[0]
    assert trade.costs == 0.0
    assert trade.net_pnl == pytest.approx(trade.gross_pnl)
    assert trade.entry_price == pytest.approx(trade.entry_reference_price)


def test_cost_summary_separates_gross_and_net():
    result = run(cfg=settings(costs=REFERENCE_COSTS_V1, max_bars_held=1))
    summary = result.cost_summary
    assert summary["cost_model"]["version"] == REFERENCE_COSTS_V1.version
    assert summary["total_costs"] > 0
    assert summary["net_pnl_total"] < summary["gross_pnl_total"]
    assert "reference (unslipped) prices" in summary["note"]


def test_a_tighter_slippage_assumption_moves_the_result():
    cheap = run(cfg=settings(costs=CostModel(slippage_bps=0.5, brokerage_bps=0.0, exchange_bps=0.0, sebi_bps=0.0, gst_on_fees_pct=0.0, stt_sell_bps=0.0, stamp_buy_bps=0.0), max_bars_held=1))
    dear = run(cfg=settings(costs=CostModel(slippage_bps=5.0, brokerage_bps=0.0, exchange_bps=0.0, sebi_bps=0.0, gst_on_fees_pct=0.0, stt_sell_bps=0.0, stamp_buy_bps=0.0), max_bars_held=1))
    assert dear.trades[0].net_pnl < cheap.trades[0].net_pnl


def test_gross_is_identical_regardless_of_costs():
    cheap = run(cfg=settings(costs=ZERO_COSTS, max_bars_held=1))
    dear = run(cfg=settings(costs=REFERENCE_COSTS_V1, max_bars_held=1))
    assert cheap.trades[0].gross_pnl == dear.trades[0].gross_pnl


# --------------------------------------------------------------------------- #
# Sizing, equity and drawdown
# --------------------------------------------------------------------------- #
def test_fixed_fraction_sizing_scales_with_equity():
    cfg = BacktestSettings(
        execution=ExecutionSettings(
            entry_fill="next_open",
            size_mode="fixed_fraction",
            allocation_pct=0.5,
            initial_capital=100_000.0,
            leverage=1.0,
        ),
        exits=ExitSettings(max_bars_held=1),
        costs=ZERO_COSTS,
    )
    result = run(cfg=cfg)
    trade = result.trades[0]
    # 50% of 100,000 at the 101 fill = 495.0495 units.
    assert trade.quantity == pytest.approx(50_000 / 101, rel=1e-9)
    assert trade.gross_pnl == pytest.approx((102.5 - 101.0) * 50_000 / 101, abs=1e-3)


def test_equity_curve_is_one_point_per_bar_and_tracks_position_state():
    result = run()
    assert len(result.equity_curve) == len(BASE_ROWS)
    assert result.equity_curve[1].in_position is False
    assert result.equity_curve[2].in_position is True
    assert result.equity_curve[3].in_position is False


def test_losing_trade_produces_the_expected_drawdown():
    rows = list(BASE_ROWS)
    rows[2] = (100.5, 101.0, 99.0, 99.5)  # stop at 99.5 (points 1.5) -> -1.5
    cfg = settings(capital=100.0, stop_mode="points", stop_value=1.5)
    result = run(rows, cfg=cfg)
    trade = result.trades[0]
    assert trade.net_pnl == pytest.approx(-1.5)
    assert result.equity_curve[-1].equity == pytest.approx(98.5)
    assert result.metrics["max_drawdown_pct"] == pytest.approx(1.5, rel=1e-6)
    assert result.metrics["total_return_pct"] == pytest.approx(-1.5, rel=1e-6)


def test_mae_and_mfe_record_the_excursion_in_both_directions():
    rows = [
        (99.0, 100.0, 98.0, 99.0),
        (99.5, 101.0, 99.0, 100.5),
        (101.0, 101.5, 100.5, 101.0),
        (101.0, 105.0, 100.0, 104.5),
        (104.5, 105.0, 104.0, 104.5),
    ]
    cfg = settings()  # no stop / target, exit at end of data
    result = run(rows, cfg=cfg)
    trade = result.trades[0]
    assert trade.mfe == pytest.approx(4.0), "105 ran 4.0 above the 101 entry"
    assert trade.mae == pytest.approx(1.0), "100 dipped 1.0 below the 101 entry"
    assert trade.mfe_pct == pytest.approx(100 * 4.0 / 101, rel=1e-6)
    assert trade.mae_pct == pytest.approx(100 * 1.0 / 101, rel=1e-6)


def test_no_new_position_can_open_on_the_bar_that_closed_one():
    # A stop-out on bar 2 plus a fresh signal on bar 2's close must not re-enter.
    rows = list(BASE_ROWS)
    rows[2] = (100.5, 101.0, 99.0, 100.5)  # stops out (stop 100), closes at the cross level
    cfg = settings(stop_mode="points", stop_value=1.0)
    result = run(rows, cfg=cfg)
    assert len(result.trades) == 1
    assert result.trades[0].exit_index == 2


# --------------------------------------------------------------------------- #
# Warm-up and validation
# --------------------------------------------------------------------------- #
def test_signals_inside_the_warmup_window_are_suppressed():
    result = run(warmup=5)
    assert result.signals["long"] == []
    assert result.trades == []
    assert result.ok


def test_trades_never_enter_before_the_warmup_bar():
    result = run(warmup=2)
    for trade in result.trades:
        assert trade.entry_index >= 2


def test_structural_checks_pass_on_a_real_run():
    result = run()
    report = result.validation["structural"]
    assert report["passed"], report["issues"]


def test_structural_checks_detect_a_broken_fill_model():
    result = run()
    trade = result.trades[0]
    trade.entry_index = trade.signal_index  # pretend it filled on the signal bar
    report = structural_checks(result.trades, settings(max_bars_held=1), 0, len(BASE_ROWS))
    assert not report["passed"]
    assert any("next_open" in issue for issue in report["issues"])


def test_validation_badge_is_earned_not_assumed(candles):
    # Long enough that prefix samples exist: the badge is only awarded when the
    # recomputation check actually ran.
    turns_up = {"operator": "AND", "conditions": [{"left": "close", "operator": "turns_up"}]}
    result = BacktestEngine().run(
        candles=candles,
        long_rule=turns_up,
        short_rule=None,
        settings=settings(max_bars_held=5),
        timeframe="5m",
    )
    assert result.ok, result.error
    assert result.trades, "the fixture must produce trades for the badge test to mean anything"
    assert result.validation["tested"] is True
    assert result.validation["no_lookahead"] is True
    assert result.validation["badge"].startswith("✓")


def test_short_series_withholds_the_badge():
    # 5 bars is below the minimum prefix sample, so causality cannot be proven
    # and the badge must be withheld rather than assumed.
    result = run(BASE_ROWS, cfg=settings(max_bars_held=1))
    assert result.ok
    assert result.validation["tested"] is False
    assert result.validation["no_lookahead"] is False
    assert result.validation["badge"].startswith("⚠")
    assert any("not verified" in issue for issue in result.validation["issues"])


# --------------------------------------------------------------------------- #
# Error handling (honest refusal, never a silent success)
# --------------------------------------------------------------------------- #
def test_atr_stops_refuse_to_run_without_an_atr_feature():
    result = run(cfg=settings(stop_mode="atr", stop_value=2.0))
    assert result.ok is False
    assert "ATR" in (result.error or "")


def test_atr_stops_run_when_the_feature_is_supplied():
    atr_values = [1.0] * len(BASE_ROWS)
    result = run(
        cfg=settings(stop_mode="atr", stop_value=2.0),
        features={"atr": atr_values},
    )
    assert result.ok, result.error
    trade = result.trades[0]
    assert trade.stop_price == pytest.approx(101.0 - 2.0)


def test_unknown_feature_fails_the_run_instead_of_producing_no_signals():
    result = run(long_rule={"operator": "AND", "conditions": [{"left": "ghost", "operator": ">", "right": 1}]})
    assert result.ok is False
    assert "ghost" in (result.error or "")


def test_empty_candle_series_is_an_explicit_failure():
    result = BacktestEngine().run(candles=[], long_rule=LONG_ABOVE_100, settings=settings())
    assert result.ok is False
    assert "No candles" in (result.error or "")


def test_output_length_mismatch_is_refused():
    result = BacktestEngine().run(
        candles=build_candles(BASE_ROWS),
        features={"broken": [1.0, 2.0]},
        long_rule=LONG_ABOVE_100,
        settings=settings(),
    )
    assert result.ok is False
    assert "index-aligned" in (result.error or "")


def test_output_named_like_a_price_column_is_refused():
    result = BacktestEngine().run(
        candles=build_candles(BASE_ROWS),
        features={"close": [1.0] * len(BASE_ROWS)},
        long_rule=LONG_ABOVE_100,
        settings=settings(),
    )
    assert result.ok is False
    assert "collide" in (result.error or "")


def test_unknown_entry_fill_is_refused():
    cfg = settings()
    cfg.execution.entry_fill = "next_tick"
    result = run(cfg=cfg)
    assert result.ok is False
    assert "entry_fill" in (result.error or "")


def test_negative_allocation_is_refused():
    cfg = settings()
    cfg.execution.allocation_pct = 0.0
    result = run(cfg=cfg)
    assert result.ok is False
    assert "allocation_pct" in (result.error or "")


def test_no_signal_produces_an_honest_empty_result():
    rows = [(100.0, 101.0, 99.0, 100.0) for _ in range(40)]
    result = run(rows, cfg=settings())
    assert result.ok is True
    assert result.trades == []
    assert result.metrics["n_trades"] == 0
    assert any("No signal fired" in issue for issue in result.validation["issues"])
