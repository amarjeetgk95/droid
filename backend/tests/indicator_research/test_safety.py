"""Isolation guard tests (§43).

The claim "research cannot place live orders" is only worth making if it is
enforced. These tests check that the guard is clean on the real package and that
it actually fires on a violation, so a future edit cannot silently erode it.
"""

from __future__ import annotations

from pathlib import Path

from app.indicator_research.safety import (
    FORBIDDEN_IMPORT_PREFIXES,
    assert_no_live_trading_reach,
    isolation_report,
    scan_package,
)


def test_the_real_package_never_reaches_live_trading():
    report = scan_package()
    assert report["imports"] == [], report["imports"]
    assert report["calls"] == [], report["calls"]
    assert_no_live_trading_reach()


def test_isolation_report_states_the_guarantee():
    report = isolation_report()
    assert report["isolated"] is True
    assert report["violations"] == {"imports": [], "calls": []}
    assert any("order" in g.lower() for g in report["guarantees"])
    assert "app.signals" in report["forbidden_import_prefixes"]


def test_a_forbidden_import_is_detected(tmp_path):
    module = tmp_path / "leaky.py"
    module.write_text(
        "from app.signals.worker import automated_signal_worker\n", encoding="utf-8"
    )
    report = scan_package(tmp_path)
    assert len(report["imports"]) == 1
    assert "app.signals" in report["imports"][0]


def test_a_forbidden_import_inside_a_nested_package_is_detected(tmp_path):
    nested = tmp_path / "deep" / "nested"
    nested.mkdir(parents=True)
    (nested / "broker.py").write_text("import app.algo\n", encoding="utf-8")
    report = scan_package(tmp_path)
    assert any("app.algo" in item for item in report["imports"])


def test_a_plain_submodule_import_is_detected(tmp_path):
    (tmp_path / "mod.py").write_text("from app import signals\n", encoding="utf-8")
    # ``from app import signals`` names 'app'; the attribute usage is not an
    # import violation, but importing app.signals directly is.
    (tmp_path / "mod2.py").write_text("from app.signals import worker\n", encoding="utf-8")
    report = scan_package(tmp_path)
    assert any("app.signals" in item for item in report["imports"])


def test_an_order_placement_call_is_detected(tmp_path):
    (tmp_path / "trading.py").write_text(
        "def go(broker):\n    broker.place_order('NIFTY', 50)\n", encoding="utf-8"
    )
    report = scan_package(tmp_path)
    assert len(report["calls"]) == 1
    assert "place_order" in report["calls"][0]


def test_assertion_raises_on_a_violation(tmp_path):
    (tmp_path / "bad.py").write_text("import app.algo.execution.broker\n", encoding="utf-8")
    try:
        assert_no_live_trading_reach(tmp_path)
    except Exception as exc:  # ResearchIsolationError
        assert "must not reach live trading" in str(exc)
    else:  # pragma: no cover - the guard must raise here
        raise AssertionError("the isolation guard failed to raise")


def test_forbidden_prefixes_cover_the_order_paths():
    for prefix in ("app.signals", "app.algo", "app.providers", "app.services.paper_service"):
        assert prefix in FORBIDDEN_IMPORT_PREFIXES


def test_the_api_module_does_not_import_broker_code():
    api_source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "indicator_research"
        / "api.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("app.signals", "app.providers", "app.algo", "paper_service"):
        assert forbidden not in api_source, f"api.py references {forbidden}"
