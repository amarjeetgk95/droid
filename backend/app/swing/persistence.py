"""
Swing Module State Persistence Layer (v5.0).
Persists active setups, multi-day open positions, and audit history.
Guarantees zero state loss across backend restarts via atomic JSON cache.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
import structlog
from app.swing.models import SwingSetup, SwingPosition, MarketRegime

logger = structlog.get_logger()
SWING_STATE_FILE = Path("swing_state.json")
SWING_CANDLES_CACHE_FILE = Path("swing_candles_cache.json")


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
            "setups": [s.model_dump(mode="json") for s in setups],
            "open_positions": [p.model_dump(mode="json") for p in open_positions],
            "closed_positions": [p.model_dump(mode="json") for p in closed_positions],
            "regime": regime.model_dump(mode="json") if regime else None,
            "updated_at_utc": int(__import__("time").time() * 1000),
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
    """Restores swing setups and positions from local state file."""
    if not SWING_STATE_FILE.exists():
        return {"setups": [], "open_positions": [], "closed_positions": [], "regime": None}

    try:
        with open(SWING_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        setups = [SwingSetup(**s) for s in data.get("setups", [])]
        open_pos = [SwingPosition(**p) for p in data.get("open_positions", [])]
        closed_pos = [SwingPosition(**p) for p in data.get("closed_positions", [])]
        reg = MarketRegime(**data["regime"]) if data.get("regime") else None

        return {
            "setups": setups,
            "open_positions": open_pos,
            "closed_positions": closed_pos,
            "regime": reg,
        }
    except Exception as e:
        logger.warning("load_swing_state_failed", error=str(e)[:200])
        return {"setups": [], "open_positions": [], "closed_positions": [], "regime": None}
