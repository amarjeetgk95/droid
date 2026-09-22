"""Unit tests for S6 Experiment Registry & Trial Budget Ceiling (S6SPEC_v1.3)."""

import pytest
import shutil
from pathlib import Path

from app.quant.strategies.s6_config import create_default_config, S6Variant
from app.quant.research.s6_registry import S6ExperimentRegistry, TrialBudgetExceeded, MAX_CANDIDATE_TRIALS


class TestS6Registry:

    @pytest.fixture
    def temp_registry(self, tmp_path: Path) -> S6ExperimentRegistry:
        return S6ExperimentRegistry(base_dir=tmp_path / "s6_exp")

    def test_trial_id_generation_deterministic(self, temp_registry: S6ExperimentRegistry):
        config = create_default_config(S6Variant.S6_A)
        t_id1 = temp_registry.generate_trial_id(config, "S6A_T1", "dataset_hash_123")
        t_id2 = temp_registry.generate_trial_id(config, "S6A_T1", "dataset_hash_123")
        assert t_id1 == t_id2
        assert t_id1.startswith("S6T_NIFTY_S6A_T1_")

    def test_trial_budget_ceiling_fails_closed(self, temp_registry: S6ExperimentRegistry):
        # Simulate reaching budget ceiling
        temp_registry.data["trial_count"] = MAX_CANDIDATE_TRIALS

        config = create_default_config(S6Variant.S6_A)
        with pytest.raises(TrialBudgetExceeded):
            temp_registry.generate_trial_id(config, "S6A_T1", "brand_new_hash_999")
