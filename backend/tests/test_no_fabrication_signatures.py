"""Truth-of-Wall CI gate: no fabrication signatures in runtime code.

No data is better than fake data. This test makes that principle mechanical:
it scans runtime code (backend/app, frontend/src) for the *signatures* of
fabricated market data and fails the build when one appears without a
reasoned allowlist entry.

Scope notes:
- Tests are exempt by construction (this file scans only runtime dirs).
- Structural comments (`#` / `//` lines) are skipped: mentioning a number in
  prose is not fabricating it. Code that *computes or returns* a hardcoded
  spot is.
- Structural metadata is legitimate (expiry calendars, strike ladders,
  payoff math over caller-supplied inputs) and lives on the allowlist with a
  written reason. Every allowlist entry must carry one.
- The `market_data_valid=True`-inside-`except` inversion is a *structural*
  pattern, not a token — it is covered by degraded-path tests
  (test_degraded_paths_fail_honest.py), not by grep.

To silence a hit: fix the fabrication (preferred), or add an allowlist entry
below WITH a reason. Allowlist entries without reasons are treated as
violations by this test itself.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_APP = REPO_ROOT / "backend" / "app"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

SKIP_DIRS = {"__pycache__", "node_modules", ".next", ".git"}

# (rule name, regex, scope) — scope is "backend", "frontend" or "both"
RULES: list[tuple[str, str, str]] = [
    # The synthetic-options fallback mode that once returned fabricated
    # option contexts (spot 52000/24500, IV 14.5, OI 1.25M) must never return.
    ("fallback_calibrated", r"FALLBACK_CALIBRATED", "both"),
    # Mock AI injection is only legal inside the §77-gated door itself.
    ("mock_ai_response", r"mock_ai_response", "backend"),
    # Hardcoded spot levels — the classic fabrication. Non-comment lines only.
    (
        "hardcoded_spot_backend",
        r"\b(24500|24800|24812|24850|52000)(?:\.0+)?\b",
        "backend",
    ),
    (
        "hardcoded_spot_frontend",
        r"\b(24500|24800|24812|24850|52000)(?:\.0+)?\b",
        "frontend",
    ),
    # Hardcoded IV tables contradict the "no simulated data" banner.
    ("instrument_iv_map", r"\bINSTRUMENT_IV\b", "frontend"),
]

# path-suffix (posix) -> list of {rule, reason}. Entries without a "reason"
# key are themselves a failure (enforced below).
ALLOWLIST: dict[str, list[dict[str, str]]] = {
    "backend/app/api/institutional.py": [
        {
            "rule": "mock_ai_response",
            "reason": "The §77-gated injection door itself: the request model, "
            "the _mock_injection_blocked() gate and its 403 sites must name "
            "the parameter to refuse it. Gate must stay fail-closed.",
        },
    ],
    "backend/app/services/ai_strategy_service.py": [
        {
            "rule": "hardcoded_spot_backend",
            "reason": "Strike 24800 appears inside an LLM prompt as a JSON "
            "schema EXAMPLE (illustrative shape), not a claimed market "
            "value; no price path reads it.",
        },
    ],
    "frontend/src/lib/api/institutional.ts": [
        {
            "rule": "mock_ai_response",
            "reason": "Frontend passes the test-injection query param for the "
            "same dev/test purpose; the backend §77 gate is the enforcement "
            "point and refuses it in live mode.",
        },
    ],
}

_COMMENT_PREFIXES = ("#", "//")


def _iter_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        # Test files are a legitimate fake-data zone (exception #1): fixture
        # numbers there never reach runtime. Also skip type declarations.
        name = p.name
        if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".d.ts")):
            continue
        out.append(p)
    return sorted(out)


def _scan(root: Path, scope: str) -> list[str]:
    violations: list[str] = []
    allow_by_rule: dict[str, dict[str, str]] = {}
    for path_suffix, entries in ALLOWLIST.items():
        for entry in entries:
            allow_by_rule.setdefault(path_suffix, {})[entry["rule"]] = entry.get("reason", "")

    for rule_name, pattern, rule_scope in RULES:
        if rule_scope not in ("both", scope):
            continue
        rx = re.compile(pattern)
        for f in _iter_files(root):
            rel = f.relative_to(REPO_ROOT).as_posix()
            allowed_reason = allow_by_rule.get(rel, {}).get(rule_name)
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if line.strip().startswith(_COMMENT_PREFIXES):
                    continue
                if rx.search(line):
                    if allowed_reason:
                        continue
                    violations.append(
                        f"{rel}:{lineno} [{rule_name}] {line.strip()[:140]}"
                    )

    # Self-guard: allowlist entries that name an unknown rule or carry no
    # reason are dead weight / future confusion — flag them too.
    valid_rules = {name for name, _, _ in RULES}
    for path_suffix, entries in ALLOWLIST.items():
        for entry in entries:
            if entry.get("rule") not in valid_rules:
                violations.append(
                    f"<allowlist> {path_suffix} [{entry.get('rule')}] rule does not exist"
                )
            if not entry.get("reason", "").strip():
                violations.append(
                    f"<allowlist> {path_suffix} [{entry.get('rule')}] allowlist entry has no reason"
                )
    return violations


def test_no_fabrication_signatures_backend() -> None:
    hits = _scan(BACKEND_APP, "backend")
    assert not hits, (
        "Truth-of-Wall violation: fabricated-data signatures found in backend/app.\n"
        "Fix the fabrication (preferred) or add a reasoned allowlist entry.\n"
        + "\n".join(hits)
    )


def test_no_fabrication_signatures_frontend() -> None:
    hits = _scan(FRONTEND_SRC, "frontend")
    assert not hits, (
        "Truth-of-Wall violation: fabricated-data signatures found in frontend/src.\n"
        "Fix the fabrication (preferred) or add a reasoned allowlist entry.\n"
        + "\n".join(hits)
    )


def test_scan_detects_planted_violation(tmp_path: Path) -> None:
    """Test-of-the-test: the scanner catches a planted fabricated spot."""
    planted = tmp_path / "sneaky.py"
    planted.write_text('SPOT = 24850.0  # totally real\n', encoding="utf-8")
    # Scan the planted file directly by pointing the scanner at tmp_path and
    # treating it as the repo root is fragile (relpath math); instead run the
    # rule regex against the planted content the same way _scan does.
    rx = dict((name, re.compile(pat)) for name, pat, _ in RULES)["hardcoded_spot_backend"]
    line = planted.read_text(encoding="utf-8").splitlines()[0]
    assert not line.strip().startswith(_COMMENT_PREFIXES)
    assert rx.search(line), "scanner regex must catch a planted hardcoded spot"


def test_allowlist_paths_exist() -> None:
    """A allowlist entry pointing at a deleted file is stale — flag it."""
    stale = []
    for path_suffix in ALLOWLIST:
        if not (REPO_ROOT / path_suffix).exists():
            stale.append(path_suffix)
    assert not stale, f"Stale allowlist paths (file gone): {stale}"
