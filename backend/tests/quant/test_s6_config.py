"""Unit tests for S6 Configuration (S6SPEC_v1.3)."""

import pytest
from app.quant.strategies.s6_config import (
    S6Config,
    S6Variant,
    S6TimeframeBranch,
    create_default_config,
)


def test_s6_config_immutability():
    config = create_default_config()
    with pytest.raises(Exception):
        config.instrument = "BANKNIFTY"  # FrozenInstanceError or dataclass error


def test_s6_config_parameter_hash_deterministic():
    config1 = create_default_config(S6Variant.S6_A, S6TimeframeBranch.T1_5M_1M, "NIFTY")
    config2 = create_default_config(S6Variant.S6_A, S6TimeframeBranch.T1_5M_1M, "NIFTY")
    assert config1.parameter_hash == config2.parameter_hash
    assert len(config1.parameter_hash) == 16


def test_s6_config_hash_changes_on_variant():
    config_a = create_default_config(S6Variant.S6_A, S6TimeframeBranch.T1_5M_1M, "NIFTY")
    config_f = create_default_config(S6Variant.S6_F, S6TimeframeBranch.T1_5M_1M, "NIFTY")
    assert config_a.parameter_hash != config_f.parameter_hash


def test_s6_config_frozen_defaults_match_spec():
    config = create_default_config()
    assert config.compression.atr_ratio_max == 0.85
    assert config.compression.range_ratio_max == 3.0
    assert config.compression.persistence_bars == 3
    assert config.breakout.min_breakout_distance_atr == 0.10
    assert config.breakout.volume_ratio_min == 1.30
    assert config.breakout.close_location_min == 0.60
    assert config.breakout.min_room_atr == 1.50
    assert config.exit.k_sl == 1.5
    assert config.exit.k_tp == 2.5
    assert config.simulation.same_bar_tie_break == "SL_FIRST"
    assert config.simulation.slippage_atr == 0.05
