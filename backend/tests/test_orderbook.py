import pytest
from app.services.orderbook_engine import OrderBookState, OrderBookEngine
from app.models.crypto import OrderBookSequenceStatus


def test_orderbook_snapshot_initialization():
    state = OrderBookState("BTCUSDT", "spot")
    assert not state.is_initialized
    assert state.sequence_status == OrderBookSequenceStatus.SYNCING

    bids_raw = [["90000.0", "1.5"], ["89990.0", "2.0"]]
    asks_raw = [["90010.0", "1.0"], ["90020.0", "3.0"]]
    state.set_snapshot(100, bids_raw, asks_raw)

    assert state.is_initialized
    assert state.last_update_id == 100
    assert state.sequence_status == OrderBookSequenceStatus.ACTIVE

    model = state.to_model(10)
    assert model.best_bid == 90000.0
    assert model.best_ask == 90010.0
    assert model.spread == 10.0
    assert len(model.bids) == 2
    assert len(model.asks) == 2


def test_orderbook_valid_diff_update():
    state = OrderBookState("BTCUSDT", "spot")
    state.set_snapshot(100, [["90000.0", "1.0"]], [["90010.0", "1.0"]])

    diff_event = {
        "U": 101,
        "u": 102,
        "b": [["90005.0", "2.5"]],
        "a": [["90010.0", "0.0"]],  # level removed
    }
    applied = state.apply_diff(diff_event)
    assert applied
    assert state.last_update_id == 102
    assert state.sequence_status == OrderBookSequenceStatus.ACTIVE

    model = state.to_model(10)
    assert model.best_bid == 90005.0
    assert 90010.0 not in [a.price for a in model.asks]


def test_orderbook_sequence_gap_detection():
    state = OrderBookState("BTCUSDT", "spot")
    state.set_snapshot(100, [["90000.0", "1.0"]], [["90010.0", "1.0"]])

    # Event with missing sequence (U = 105 instead of 101)
    gap_event = {
        "U": 105,
        "u": 106,
        "b": [["90005.0", "2.5"]],
        "a": [],
    }
    applied = state.apply_diff(gap_event)
    assert not applied
    assert state.sequence_status == OrderBookSequenceStatus.GAP_DETECTED


def test_orderbook_futures_pu_validation():
    state = OrderBookState("ETHUSDT", "futures")
    state.set_snapshot(500, [["2600.0", "10.0"]], [["2601.0", "10.0"]])

    # Valid futures diff: pu == 500
    valid_event = {
        "U": 501,
        "u": 502,
        "pu": 500,
        "b": [["2600.5", "5.0"]],
        "a": [],
    }
    assert state.apply_diff(valid_event)
    assert state.last_update_id == 502

    # Gap in futures: pu == 510 != 502
    broken_event = {
        "U": 511,
        "u": 512,
        "pu": 510,
        "b": [["2601.0", "5.0"]],
        "a": [],
    }
    assert not state.apply_diff(broken_event)
    assert state.sequence_status == OrderBookSequenceStatus.GAP_DETECTED


def test_orderbook_depth_imbalance():
    state = OrderBookState("BTCUSDT", "spot")
    state.set_snapshot(
        100,
        [["90000.0", "10.0"]],  # 900,000 USD notional
        [["90010.0", "2.0"]],   # 180,020 USD notional
    )
    model = state.to_model(10)
    assert model.bid_depth_total == 900000.0
    assert model.ask_depth_total == 180020.0
    assert model.depth_imbalance > 0  # more bids than asks
    assert model.depth_imbalance_pct > 0
