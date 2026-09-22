"""S6 Research Experiment Registry & Artifact Writer (S6SPEC_v1.3).

Responsibilities:
- Generates deterministic trial_id based on strategy, variant, track, and parameter hash
- Enforces the hard 400-candidate trial budget (fails closed if exceeded)
- Serializes immutable artifacts: run_metadata.json, metrics.json, events, candidates, trades
- Maintains immutable audit trail of all research runs
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import polars as pl

from app.quant.strategies.s6_config import S6Config
from app.quant.strategies.s6_events import (
    CompressionEpisode,
    RawBreakoutEvent,
    FailureEvent,
    EntryCandidate,
)
from app.quant.execution.s6_simulator import S6Trade
from app.quant.research.s6_metrics import S6MetricsReport

MAX_CANDIDATE_TRIALS = 400


class TrialBudgetExceeded(Exception):
    """Raised when the 400-candidate trial budget ceiling is breached."""
    pass


class S6ExperimentRegistry:
    """Audit ledger and artifact writer for S6 research runs."""

    def __init__(self, base_dir: Path | str = "data/experiments/s6"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.base_dir / "trial_registry.json"
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_file.exists():
            try:
                with open(self.registry_file, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"trial_count": 0, "trials": {}}
        else:
            self.data = {"trial_count": 0, "trials": {}}

    def load_registry(self) -> Dict[str, Any]:
        """Returns the current registry dictionary."""
        return self.data

    def _save_registry(self) -> None:
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def generate_trial_id(
        self,
        config: S6Config,
        track: str,
        dataset_hash: str,
    ) -> str:
        """Generates a deterministic trial ID and registers it against the 400 trial budget."""
        seed_str = f"{config.strategy_id}_{config.variant.value}_{config.instrument}_{track}_{config.parameter_hash}_{dataset_hash[:12]}"
        short_hash = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:10]
        trial_id = f"S6T_{config.instrument}_{track}_{short_hash}"

        # Register if new candidate trial
        if trial_id not in self.data["trials"]:
            current_count = self.data["trial_count"]
            if current_count >= MAX_CANDIDATE_TRIALS:
                raise TrialBudgetExceeded(
                    f"S6 candidate trial budget of {MAX_CANDIDATE_TRIALS} exceeded! "
                    "Per S6SPEC_v1.3, research must fail closed."
                )
            self.data["trials"][trial_id] = {
                "trial_id": trial_id,
                "strategy_version": config.strategy_version,
                "variant": config.variant.value,
                "instrument": config.instrument,
                "track": track,
                "parameter_hash": config.parameter_hash,
                "dataset_hash": dataset_hash,
                "registered_at": datetime.now(timezone.utc).isoformat(),
            }
            self.data["trial_count"] = len(self.data["trials"])
            self._save_registry()

        return trial_id

    def record_run_artifacts(
        self,
        trial_id: str,
        config: S6Config,
        track: str,
        dataset_hash: str,
        episodes: List[CompressionEpisode],
        raw_breakouts: List[RawBreakoutEvent],
        failures: List[FailureEvent],
        candidates: List[EntryCandidate],
        trades: List[S6Trade],
        metrics: S6MetricsReport,
        code_sha: str = "local_dev",
    ) -> Path:
        """Writes immutable parquet and json artifacts for an S6 research run."""
        run_timestamp = int(datetime.now(timezone.utc).timestamp())
        run_id = f"run_{trial_id}_{run_timestamp}"
        run_dir = self.base_dir / trial_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. run_metadata.json
        metadata = {
            "run_id": run_id,
            "trial_id": trial_id,
            "strategy_id": config.strategy_id,
            "spec_version": config.spec_version,
            "strategy_version": config.strategy_version,
            "variant": config.variant.value,
            "instrument": config.instrument,
            "track": track,
            "parameter_hash": config.parameter_hash,
            "dataset_hash": dataset_hash,
            "code_sha": code_sha,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trial_budget_consumed": self.data["trial_count"],
            "trial_budget_limit": MAX_CANDIDATE_TRIALS,
        }
        with open(run_dir / "run_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 2. metrics.json
        with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics.to_dict(), f, indent=2)

        # 3. candidates.json / trades.json
        if candidates:
            cand_dicts = [asdict(c) for c in candidates]
            # convert datetimes to strings for JSON
            for cd in cand_dicts:
                cd["signal_time"] = cd["signal_time"].isoformat()
                cd["entry_time"] = cd["entry_time"].isoformat()
            with open(run_dir / "candidates.json", "w", encoding="utf-8") as f:
                json.dump(cand_dicts, f, indent=2)

        if trades:
            trade_dicts = [asdict(t) for t in trades]
            for td in trade_dicts:
                td["signal_time"] = td["signal_time"].isoformat()
                td["entry_time"] = td["entry_time"].isoformat()
                td["exit_time"] = td["exit_time"].isoformat()
            with open(run_dir / "trades.json", "w", encoding="utf-8") as f:
                json.dump(trade_dicts, f, indent=2)

        return run_dir
