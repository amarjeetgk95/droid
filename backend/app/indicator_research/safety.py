"""Research isolation guard (§43).

The Indicator Research module must never place an order, touch a live position,
or reach a broker. Architectural isolation is easy to *intend* and easy to
erode: one convenient ``from app.signals... import`` during a debugging session
and the research tree can suddenly mutate live state.

So the property is enforced statically and tested. Every module in this package
is parsed with :mod:`ast` and every import target is checked against a list of
live-trading roots. The check runs in CI via a unit test, and the API exposes
its result so the UI can state the guarantee rather than assume it.

Static analysis is used deliberately: it catches a bad import at review time,
not only on the code path that happens to execute it.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterable, Sequence

#: Import roots that must never appear anywhere in the research package.
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "app.signals",
    "app.algo.execution",
    "app.algo",
    "app.providers",
    "app.services.paper_service",
    "app.services.execution",
    "app.services.market_service",
    "app.institutional",
    "app.fno",
    "app.market_core",
    "app.api.paper",
    "app.api.trade",
    "app.paper",
)

#: Names that would indicate direct broker/order access even without an import.
FORBIDDEN_ATTRIBUTE_CALLS: tuple[str, ...] = (
    "place_order",
    "placeorder",
    "modify_order",
    "cancel_order",
    "exit_position",
    "square_off",
    "squareoff",
)


class ResearchIsolationError(RuntimeError):
    """Raised when the research package reaches into live-trading code."""


def _iter_python_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


def _imported_modules(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            # ``from . import x`` has module=None and is always internal.
            if node.module:
                yield node.module, node.lineno
            if node.level and node.module:
                yield node.module, node.lineno


def _called_names(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                yield func.attr, getattr(func, "lineno", 0)
            elif isinstance(func, ast.Name):
                yield func.id, getattr(func, "lineno", 0)


def scan_package(root: Path | None = None) -> dict[str, list[str]]:
    """Return ``{"imports": [...], "calls": [...]}`` violations found on disk."""
    package_root = root or Path(__file__).resolve().parent
    violations: dict[str, list[str]] = {"imports": [], "calls": []}
    for path in _iter_python_files(package_root):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError) as e:  # pragma: no cover - unreadable file
            violations["imports"].append(f"{path}: unparsable ({e})")
            continue
        relative = path.relative_to(package_root)
        for module, lineno in _imported_modules(tree):
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                violations["imports"].append(f"{relative}:{lineno} imports '{module}'")
        for name, lineno in _called_names(tree):
            if name.lower() in FORBIDDEN_ATTRIBUTE_CALLS:
                violations["calls"].append(f"{relative}:{lineno} calls '{name}()'")
    return violations


def assert_no_live_trading_reach(root: Path | None = None) -> None:
    """Raise :class:`ResearchIsolationError` if a violation exists."""
    violations = scan_package(root)
    if violations["imports"] or violations["calls"]:
        raise ResearchIsolationError(
            "Indicator Research must not reach live trading code: "
            + "; ".join(violations["imports"] + violations["calls"])
        )


def isolation_report(root: Path | None = None) -> dict[str, object]:
    """Serialisable isolation status for the API and the UI badge."""
    violations = scan_package(root)
    clean = not violations["imports"] and not violations["calls"]
    return {
        "isolated": clean,
        "forbidden_import_prefixes": list(FORBIDDEN_IMPORT_PREFIXES),
        "violations": violations,
        "guarantees": [
            "No broker, order-router or live-position module is imported.",
            "No order-placement function is called anywhere in this package.",
            "Research endpoints only read stored historical candles and write experiment files.",
            "Live execution remains behind the existing DROID compliance and risk gates.",
        ],
    }


__all__: Sequence[str] = (
    "FORBIDDEN_ATTRIBUTE_CALLS",
    "FORBIDDEN_IMPORT_PREFIXES",
    "ResearchIsolationError",
    "assert_no_live_trading_reach",
    "isolation_report",
    "scan_package",
)
