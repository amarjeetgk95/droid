"""Backward-compatible shim. Consolidated in app.signals.strategies.fisher_macd.fisher."""
from pathlib import Path
import sys

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.signals.strategies.fisher_macd.fisher import *  # noqa: F401, F403
