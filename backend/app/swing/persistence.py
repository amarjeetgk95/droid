"""
Swing Module State Persistence Layer (v6.0 Options Overhaul).
Persists active options setups, multi-day open positions, and Greeks telemetry.
Enforces schema versioning (v2) and safe migration from legacy equity state.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional
import structlog
from app.swing.models import SwingSetup, SwingPosition, MarketRegime

logger = structlog.get_logger()
SWING_STATE_FILE = Path("swing_state.json")
SWING_CANDLES_CACHE_FILE = Path("swing_candles_cache.json")
SWING_STATE_SCHEMA_VERSION = 2


def save_candles_cache(cache: dict[str, list[dict[str, Any]]]) -> bool:
    """Saves finalized daily candles cache to atomic disk file."""
    try:
        tmp_file = SWING_CANDLES_CACHE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, default=str)
        tmp_file.replace(SWING_CANDLES_CACHE_FILE)
        return True
    except Exception as e:
        logger.warning("save_candles_cache_failed", error=str(e)[:200])
        return False


def load_candles_cache() -> dict[str, list[dict[str, Any]]]:
    """Restores daily candles cache from disk."""
    if not SWING_CANDLES_CACHE_FILE.exists():
        return {}
    try:
        with open(SWING_CANDLES_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("load_candles_cache_failed", error=str(e)[:200])
        return {}


def save_swing_state(
    setups: list[SwingSetup],
    open_positions: list[SwingPosition],
    closed_positions: list[SwingPosition],
    regime: Optional[MarketRegime] = None,
) -> bool:
    """Safely saves swing state to atomic tmp file then renames."""
    try:
        payload = {
            "schema_version": SWING_STATE_SCHEMA_VERSION,
            "setups": [s.model_dump(mode="json") for s in setups],
            "open_positions": [p.model_dump(mode="json") for p in open_positions],
            "closed_positions": [p.model_dump(mode="json") for p in closed_positions],
            "regime": regime.model_dump(mode="json") if regime else None,
            "updated_at_utc": int(time.time() * 1000),
        }

        tmp_file = SWING_STATE_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        tmp_file.replace(SWING_STATE_FILE)
        return True
    except Exception as e:
        logger.warning("save_swing_state_failed", error=str(e)[:200])
        return False


def load_swing_state() -> dict[str, Any]:
    """
    Restores swing setups and positions from local state file.
    Enforces migration safety (§48): If legacy v1 equity state detected,
    archives it safely and creates clean empty options state.
    """
    if not SWING_STATE_FILE.exists():
        return {"schema_version": SWING_STATE_SCHEMA_VERSION, "setups": [], "open_positions": [], "closed_positions": [], "regime": None}

    try:
        with open(SWING_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Detect legacy equity schema (v1 or unversioned)
        version = data.get("schema_version")
        if version != SWING_STATE_SCHEMA_VERSION:
            logger.info("legacy_swing_state_detected_running_migration", current_version=version, target_version=SWING_STATE_SCHEMA_VERSION)
            # Backup legacy state
            backup_file = Path(f"swing_state_legacy_backup_{int(time.time())}.json")
            try:
                with open(backup_file, "w", encoding="utf-8") as bf:
                    json.dump(data, bf, indent=2)
                logger.info("legacy_swing_state_archived", backup_file=str(backup_file))
            except Exception as be:
                logger.warning("failed_to_backup_legacy_swing_state", error=str(be)[:200])

            # Reset to clean v2 options state
            empty_state = {
                "schema_version": SWING_STATE_SCHEMA_VERSION,
                "setups": [],
                "open_positions": [],
                "closed_positions": [],
                "regime": None,
                "updated_at_utc": int(time.time() * 1000),
            }
            with open(SWING_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(empty_state, f, indent=2)

            return empty_state

        setups = []
        for s in data.get("setups", []):
            try:
                setups.append(SwingSetup(**s))
            except Exception as e:
                logger.warning("skip_invalid_setup_record", error=str(e)[:100])

        open_pos = []
        for p in data.get("open_positions", []):
            try:
                open_pos.append(SwingPosition(**p))
            except Exception as e:
                logger.warning("skip_invalid_position_record", error=str(e)[:100])

        closed_pos = []
        for p in data.get("closed_positions", []):
            try:
                closed_pos.append(SwingPosition(**p))
            except Exception as e:
                logger.warning("skip_invalid_closed_position_record", error=str(e)[:100])

        reg = None
        if data.get("regime"):
            try:
                reg = MarketRegime(**data["regime"])
            except Exception as e:
                logger.warning("skip_invalid_regime_record", error=str(e)[:100])

        return {
            "schema_version": SWING_STATE_SCHEMA_VERSION,
            "setups": setups,
            "open_positions": open_pos,
            "closed_positions": closed_pos,
            "regime": reg,
        }
    except Exception as e:
        logger.warning("load_swing_state_failed", error=str(e)[:200])
        return {"schema_version": SWING_STATE_SCHEMA_VERSION, "setups": [], "open_positions": [], "closed_positions": [], "regime": None}

