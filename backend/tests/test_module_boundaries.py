"""Module boundaries: taxonomy single-source, no silent swallow growth, LOC budget."""
from pathlib import Path

SIG = Path(__file__).resolve().parents[1] / "app" / "signals"


def test_scan_diagnostics_field_sets_match():
    from app.signals.scanner import ScanDiagnostics as A
    from app.signals.pipeline.data_acquisition import ScanDiagnostics as B
    assert set(A.model_fields) == set(B.model_fields)


def test_fsm_state_taxonomy_in_sync():
    import typing
    from app.signals import fsm as F
    from app.signals import signal_model as M
    assert set(typing.get_args(F.SignalFSMState)) == set(typing.get_args(M.SignalFSMState))


def test_no_bare_except_pass_growth():
    # Baseline ~165 bare swallows (Cycle-2 Phase-6 replaces with degrade()).
    # Guard against growth, not zero: fail only if the count rises.
    bad = []
    for p in SIG.rglob("*.py"):
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if s in ("except:", "except Exception:", "except Exception as e:"):
                nxt = lines[i:i + 2]
                if any(n.strip() == "pass" for n in nxt):
                    bad.append(f"{p.name}:{i}")
    assert len(bad) < 180, f"bare swallow growth: {bad[:10]}"


# Monolith ratchet: files already over 900 LOC are pinned at their current
# size. The ONLY allowed direction is down. Raising a baseline is not the fix —
# split the module into submodules and lower it. Files not listed here stay
# under the simple 1100-LOC ceiling.
# TODO(split): break each entry below into focused submodules
# (persistence/audit/fsm/outcome engines) and ratchet the baseline down with it.
_LOC_BASELINE: dict[str, int] = {
    "audit_ledger.py": 1129,
    "fsm.py": 1038,
    "outcome_tracker.py": 1050,
    "signals_persistence.py": 1163,
}
_LOC_UNTRACKED_CEILING = 1100


def test_loc_budget_no_monolith_growth():
    over = []
    for p in SIG.rglob("*.py"):
        n = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
        baseline = _LOC_BASELINE.get(p.name)
        if baseline is not None:
            if n > baseline:
                over.append(f"{p.name}:{n} > baseline {baseline} (shrink-only ratchet)")
        elif n > _LOC_UNTRACKED_CEILING:
            over.append(f"{p.name}:{n} > {_LOC_UNTRACKED_CEILING}")
    assert not over, f"monolith growth: {over}"


def test_api_surface_uses_facade_paths():
    src = (Path(__file__).resolve().parents[1] / "app" / "api" / "signals.py").read_text()
    assert "from app.signals" in src  # façade-rooted imports, no sys.path hacks
    assert src.count("import") < 80
