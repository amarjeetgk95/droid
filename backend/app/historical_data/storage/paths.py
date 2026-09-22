"""Canonical Directory Resolution for Historical Market Data."""

from __future__ import annotations
import os
from pathlib import Path


def resolve_historical_data_dir() -> Path:
    """Resolve the canonical base directory for historical data and Parquet storage.
    
    Checks environment variable, backend/data/historical relative to module location,
    and current working directory, ensuring consistent path resolution regardless of
    whether the backend is launched from the workspace root or the backend folder.
    """
    env_dir = os.getenv("HISTORICAL_DATA_DIR")
    if env_dir:
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Canonical backend data path relative to this file:
    # app/historical_data/storage/paths.py -> 4 parents up is backend/
    backend_root = Path(__file__).resolve().parents[3]
    backend_data = backend_root / "data" / "historical"
    if backend_data.exists():
        return backend_data

    # Check cwd / data / historical
    cwd_data = Path.cwd() / "data" / "historical"
    if cwd_data.exists():
        return cwd_data

    # Check cwd / backend / data / historical
    cwd_backend_data = Path.cwd() / "backend" / "data" / "historical"
    if cwd_backend_data.exists():
        return cwd_backend_data

    # Fallback and create if needed
    backend_data.mkdir(parents=True, exist_ok=True)
    return backend_data
