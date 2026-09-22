"""Every top-level package under ``app/`` must import cleanly.

An undeclared dependency used to surface as an ImportError buried in one test
module — or not at all, when that module failed to collect quietly. The whole
``app.quant`` package imports ``polars``, which was missing from
``pyproject.toml`` and therefore only worked on a machine where someone had
installed it by hand; a fresh clone could not import it at all.

This walks ``app/`` and imports each top-level package, so a missing dependency
fails loudly and by name instead of silently shrinking the suite.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest

import app


def _top_level_packages() -> list[str]:
    return sorted(
        name for _finder, name, is_pkg in pkgutil.iter_modules(app.__path__) if is_pkg
    )


@pytest.mark.parametrize("package", _top_level_packages())
def test_top_level_package_imports(package: str) -> None:
    module_name = f"app.{package}"
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:  # pragma: no cover - failure path
        pytest.fail(
            f"{module_name} cannot be imported: {exc}. Declare the dependency in "
            "backend/pyproject.toml (`ml` extra for numpy/pandas/polars/scipy/"
            "scikit-learn/xgboost/lightgbm) and install with "
            '`pip install -e ".[dev,ml]"`.'
        )
