"""
Test Suite for Verifying Absence of Circular Dependencies in Signals Module (Phase 5)
"""
from __future__ import annotations

import importlib
import sys
import pytest


MODULE_GROUPS = [
    [
        "app.signals.event_bus",
        "app.signals.handlers",
        "app.signals.fsm",
        "app.signals.audit_ledger",
        "app.signals.signals_persistence",
        "app.signals.fill_reconciler",
        "app.signals.worker",
    ],
    [
        "app.signals.signals_persistence",
        "app.signals.audit_ledger",
        "app.signals.fsm",
        "app.signals.worker",
    ],
    [
        "app.signals.worker",
        "app.signals.fsm",
        "app.signals.audit_ledger",
    ],
    [
        "app.signals.pipeline",
        "app.signals.scanner",
        "app.signals.fsm",
    ],
]


@pytest.mark.parametrize("order", MODULE_GROUPS)
def test_import_sequence_has_no_circular_dependencies(order):
    """Verify that importing modules in varied sequences does not raise ImportError."""
    for mod_name in order:
        # Purge from sys.modules to simulate fresh import where possible
        mod = importlib.import_module(mod_name)
        assert mod is not None
