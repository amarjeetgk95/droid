"""HPI record store — per (derivative, category) historical record storage.

Records are compact tuples whose first element is the epoch-second timestamp:
  - candle categories:  (ts, open, high, low, close, volume)
  - scalar categories:  (ts, value)

Storage accounting uses constants.BYTES_PER_RECORD per category. Deleted
ranges are remembered permanently so the pattern engine can report
"Partial coverage / missing dataset" instead of pretending data exists (§9).
State (records, selection, policies, audit log) is persisted to a JSON file
on graceful shutdown and restored on startup.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.hpi.constants import BYTES_PER_RECORD
import structlog

logger = structlog.get_logger()

DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "hpi_state.json"


class HPIRecordStore:
    def __init__(self, state_path: Path | None = None):
        self.state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        self._records: dict[tuple[str, str], list[tuple]] = {}
        self._deleted_ranges: dict[tuple[str, str], list[list[str]]] = {}

    @staticmethod
    def _key(symbol: str, category: str) -> tuple[str, str]:
        return symbol.upper(), category

    # ------------------------------------------------------------------
    # Record operations
    # ------------------------------------------------------------------
    def append(self, symbol: str, category: str, records: list[tuple]) -> None:
        key = self._key(symbol, category)
        bucket = self._records.setdefault(key, [])
        bucket.extend(records)
        bucket.sort(key=lambda r: r[0])

    def records(self, symbol: str, category: str) -> list[tuple]:
        return self._records.get(self._key(symbol, category), [])

    def count(self, symbol: str, category: str) -> int:
        return len(self.records(symbol, category))

    def storage_bytes(self, symbol: str, category: str) -> int:
        return self.count(symbol, category) * BYTES_PER_RECORD.get(category, 32)

    def total_storage_bytes(self) -> int:
        return sum(
            len(recs) * BYTES_PER_RECORD.get(cat, 32)
            for (_sym, cat), recs in self._records.items()
        )

    def oldest_newest(self, symbol: str, category: str) -> tuple[float | None, float | None]:
        recs = self.records(symbol, category)
        if not recs:
            return None, None
        return recs[0][0], recs[-1][0]

    def delete_range(self, symbol: str, category: str, start_ts: float, end_ts: float) -> tuple[int, int]:
        """Delete records with start_ts <= ts <= end_ts. Returns (count, bytes)."""
        key = self._key(symbol, category)
        recs = self._records.get(key, [])
        keep = [r for r in recs if not (start_ts <= r[0] <= end_ts)]
        removed = len(recs) - len(keep)
        if removed:
            self._records[key] = keep
        return removed, removed * BYTES_PER_RECORD.get(category, 32)

    def mark_deleted_range(self, symbol: str, category: str, start: datetime, end: datetime) -> None:
        """Remember a deleted window so coverage reports stay honest (§9)."""
        key = self._key(symbol, category)
        self._deleted_ranges.setdefault(key, []).append([start.isoformat(), end.isoformat()])

    def deleted_ranges(self, symbol: str, category: str) -> list[list[str]]:
        return list(self._deleted_ranges.get(self._key(symbol, category), []))

    def categories_with_data(self, symbol: str) -> list[str]:
        sym = symbol.upper()
        return [cat for (s, cat), recs in self._records.items() if s == sym and recs]

    # ------------------------------------------------------------------
    # Persistence (JSON state file)
    # ------------------------------------------------------------------
    def save_state(self, extra: dict) -> None:
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "records": {
                f"{sym}|{cat}": recs
                for (sym, cat), recs in self._records.items()
                if recs
            },
            "deleted_ranges": {
                f"{sym}|{cat}": ranges
                for (sym, cat), ranges in self._deleted_ranges.items()
            },
            **extra,
        }
        try:
            tmp = self.state_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            tmp.replace(self.state_path)
            logger.info("hpi_state_saved", path=str(self.state_path))
        except Exception as e:  # pragma: no cover — defensive
            logger.error("hpi_state_save_failed", error=str(e))

    def load_state(self) -> dict:
        """Restore records/deleted-ranges. Returns any extra payload stored."""
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("hpi_state_load_failed", error=str(e))
            return {}

        for key, recs in (payload.get("records") or {}).items():
            sym, cat = key.split("|", 1)
            self._records[(sym, cat)] = [tuple(r) for r in recs]
        for key, ranges in (payload.get("deleted_ranges") or {}).items():
            sym, cat = key.split("|", 1)
            self._deleted_ranges[(sym, cat)] = ranges
        extra = {
            k: v for k, v in payload.items()
            if k not in ("records", "deleted_ranges", "saved_at")
        }
        logger.info("hpi_state_loaded", path=str(self.state_path))
        return extra
