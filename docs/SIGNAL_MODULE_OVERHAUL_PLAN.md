# Signal Module Overhaul Plan — Cycle 2 (Post Phase 0–6 Hardening)

Status: Draft
Owner: `backend/app/signals/**`, `backend/app/api/signals.py`, `frontend/src/components/signals/**`
Date: 2026-09-14
Baseline commit: `2e9827c` — "feat: complete signal module overhaul (phases 0-6), swing engine, and institutional flow"
Related: `docs/SIGNAL_GENERATION_PROCEDURE.md`, `docs/EXECUTION_SAFETY.md`, `docs/SETTINGS_OVERHAUL_PLAN.md` (format convention)

## 0. Summary

Cycle 1 (commit `2e9827c`) landed the structural refactor: `pipeline/`, `handlers/`, `safety/`, `event_bus`, `validation/`, domain models, and a dual-cadence worker.

Cycle 2 is the **hardening and reconciliation pass**: make the test suite deterministic and green again, collapse drifted duplicate safety logic into one policy module, resolve the aspirational domain-model layer (adopt or delete), decompose the monoliths that survived Cycle 1, and replace silent failure with observable degradation. Implemented in 8 phases (0–7), each independently shippable.

## 1. Baseline Measured Today

| Metric | Value |
|---|---|
| `app/signals/` modules | 79 |
| `app/signals/` LOC | 18,142 |
| `app/signals/` def/class declarations (incl. nested) | 466 |
| `app/api/signals.py` | 927 LOC, 33 routes |
| Signal test files | 13 (`backend/tests/test_signal*.py`) |
| **Test baseline** | **74 passed, 5 failed** (8.85s) |
| Module-level singletons in `app/signals/` | ~25, no reset seam |
| Silent `except ...: pass` in `app/signals/` | ~60 |

Frontend surface: `SignalsDesk.tsx` 728 LOC, `SignalDetailDrawer.tsx` 477, `useSignalsData.ts` 467, `signalsNormalize.ts` 304, `useSignalsStream.ts` 174, `src/lib/api/signals.ts` 154.

## 2. Problems Observed

### Group A — Correctness (P0)

**A1. `backend/app/institutional/scheduler.py:17` is a `SyntaxError`.**
Line 17 reads `from typing Any` instead of `from typing import Any`. The nightly FII/DII ingest + drift job therefore never imports, and because the import site is wrapped in `try/except`, nothing fails loudly. Observed live during the test run:

```
[warning] flow_scheduler_start_failed  error='invalid syntax (scheduler.py, line 17)'
```

**A2. The signal suite is red, from a single root cause.**
All 5 failures are `POST /api/v1/signals/generate` returning HTTP 400 because the manual-price drift guard rejects the tests' hard-coded index prices against the ambient feed:

```
{"detail":"Price 24870.0 deviates by 6.3% from live market LTP 23398.1. Max allowed drift is 5.0%."}
```

| Failing test | Symptom |
|---|---|
| `test_signal_centre_overhaul.py:160` | 400 (drift) |
| `test_signal_fixes_and_features.py:190` (`test_put_signal_math`) | 400 (drift) |
| `test_signal_fixes_and_features.py:216` (`test_signal_delete`) | `KeyError: 'signal'` — downstream of the same 400 |
| `test_signals_automated_audit.py:269` | 400 (drift) |
| `test_signals_paper_api.py:69` | 400 (drift) |

Guard: `manual_signal_service.py:140` (`MAX_QUOTE_DRIFT = 0.05`, line 41). `tests/conftest.py` offers only `client`, `mock_market_open`, and `isolate_signals_state` — **no fixture pins the market-data feed**, so every API test silently depends on whatever the local snapshot/provider returns. Note also `instrument_id` / `candle_timeframe` / `trigger_level` / `status` are *legacy* request fields still used by tests while the service now prefers `underlying` / `timeframe` / `trigger` (`manual_signal_service.py:82-88`) — the contract has drifted.

**A3. Quote-quality policy has drifted across 4 copies — a safety-relevant divergence.**
The same "is this quote a fallback?" rule is implemented four times, with **different semantics**:

| Location | Status tokens treated as fallback |
|---|---|
| `pipeline/data_acquisition.py:57` `is_fallback_quote` | `OFFLINE, DEGRADED, STALE, CLOSED, INVALID` |
| `scanner.py:100` `_is_fallback_quote` | `OFFLINE, DEGRADED, STALE, CLOSED, INVALID` |
| `manual_signal_service.py:67` `_quote_is_fallback` | `OFFLINE` only |
| `api/signals.py:116` `_quote_is_fallback` | `OFFLINE` only |

Consequence: the automatic scanner refuses to trade on a `STALE`/`DEGRADED` feed, but the **manual generate path accepts it** and can register a signal off a stale quote. This is exactly the class of bug the `EXECUTION_SAFETY` work exists to prevent.

### Group B — Duplication

- **B1.** `ScanDiagnostics` is defined twice: `scanner.py:57` and `pipeline/data_acquisition.py:37`. The scanner copy lacks the `CLOSED` data-quality value and must be hand-synced.
- **B2.** `SignalFSMState` `Literal` is declared twice: `fsm.py:20-34` and `signal_model.py:19-33`. Adding a state to one silently diverges from the other.
- **B3.** Tick/min-gap constants duplicated: `trigger_gate.py:16-25` (`TICK`, `MIN_GAP_PCT`, `MIN_GAP_RISK_FRACTION`, `MIN_RISK_PCT`, `MAX_ENTRY_WIDTH_R`) vs `manual_signal_service.py:40-41` (`TICK`, `MAX_QUOTE_DRIFT`).

Tooling: `backend/pyproject.toml` — `pytest` (`testpaths=["tests"]`, `asyncio_mode="auto"`), FastAPI + Pydantic v2 + structlog. No ruff config file in repo (a `.ruff_cache` exists, so ruff is used ad-hoc). No CI workflow runs pytest.

### Group C — Dead / aspirational layer

**C1. `signal_model.py` domain models have zero production consumers.**

The five models are reachable only through `SignalInstance` projection properties in `fsm.py:301-390` (`.definition`, `.risk_sizing`, `.confluence_typed`, `.execution_state`, `.outcome_typed`), and a full-repo grep shows those properties are consumed **only** by `tests/test_signal_model_immutability.py` (lines 57, 64, 70, 79, 94, 107). Nothing in `app/`, the API layer, the worker, or the persistence path reads them.

Meanwhile `SignalInstance` itself carries **79 fields**. The domain layer is a parallel taxonomy that costs maintenance and drift risk while providing no runtime value today. Cycle 2 must either wire it in (API/wire/audit serialisation) or delete it.

### Group D — Boundaries & composition

- **D1.** `api/signals.py` is 927 LOC / 33 routes with 9 function-level imports (lines 373, 423, 451-452, 475, 881, 888, 898, 912-913) — classic circular-import avoidance, and it means the API layer reaches directly into `fsm`, `paper_engine`, `position`, `execution_intent`, and `signals_persistence`.
- **D2.** `app/signals/__init__.py` is a 5-line docstring. There is no public façade, so consumers import deep paths (`from app.signals.signals_persistence import ...`).
- **D3.** ~25 module-level singletons (`signal_fsm`, `scanner_engine`, `outcome_tracker`, `signal_audit_ledger`, `signal_paper_engine`, `confluence_engine`, `signal_event_bus`, `central_risk_engine`, `kill_switch`, `feed_circuit`, `live_contract_cache`, …). None exposes a reset/DI seam; `tests/conftest.py` compensates by poking private internals (`signal_fsm._lock`, `signal_fsm._signals`).
- **D4.** `handlers/__init__.py:53` auto-registers handlers on import, while `fsm.py:78-82` imports it inside `try/except: pass`. If registration ever fails, persistence, audit, SSE, and Telegram side-effects disappear **silently**.

### Group E — Observability

~60 silent `except ...: pass`, concentrated in `signals_persistence.py` (9), `pipeline/enrichment.py` (9), `fsm.py` (6), `explain.py` (6), `pipeline/data_acquisition.py` (5), `outcome_tracker.py` (4), `audit_ledger.py` (4). Degraded *execution* and degraded *code paths* are currently indistinguishable to an operator.

### Group F — Monoliths that survived Cycle 1

| LOC | File |
|---|---|
| 973 | `signals_persistence.py` |
| 930 | `fsm.py` |
| 928 | `audit_ledger.py` |
| 885 | `outcome_tracker.py` |
| 678 | `explain.py` |
| 591 | `paper_engine.py` |
| 452 | `manual_signal_service.py` |
| 437 | `contract_resolver.py` |
| 424 | `scanner.py` |

Frontend: `SignalsDesk.tsx` 728 LOC (4 tabs, filters, tables, KPIs in one component), `SignalDetailDrawer.tsx` 477 LOC, `useSignalsData.ts` 467 LOC.

## 3. Goals / Non-Goals

**Goals**
- Signal test suite deterministic and fully green (0 failures) with a pinned market-data fixture; no test reads the ambient feed or private singleton state.
- Exactly **one** quote-quality policy module, used by scanner, manual service, and API.
- The domain layer is either the real taxonomy or deleted — no second dead copy.
- No `app/signals/` file above ~400 LOC; clear public façade `app.signals` with explicit exports.
- Handler wiring fails loud; silent swallows become counted, logged degradation.
- Frontend desk split so no component exceeds ~350 LOC.

**Non-Goals (this cycle)**
- Changing strategy logic, scoring weights, `scoring_weights.json`, or FSM transition matrix semantics.
- Real-money execution (systems stay research/paper-only).
- Database schema or Alembic changes.
- Rewriting `paper_engine` fill economics or `audit_ledger` P&L definitions.
- Touching the `swing/` or `research/` modules.

## 4. Target Architecture

```text
backend/app/signals/
  __init__.py                 # public façade: explicit re-exports + __all__ (no logic)
  container.py                # composition root + reset_for_tests()  (Phase 5)

  domain/                     # single source of truth for taxonomies & types  (Phase 2)
    states.py                 # SignalFSMState, ALLOWED_TRANSITIONS, TERMINAL_STATES
    models.py                 # signal_model.py moved here — OR deleted (§10 Q1)
    diagnostics.py            # ONE ScanDiagnostics                      (Phase 3)

  quote_quality.py            # is_fallback_quote / is_live_quote / quality tier  (Phase 1)
  constants.py                # TICK, min-gap + risk-corridor constants  (Phase 1)

  lifecycle/                  # was fsm.py (930)                        (Phase 4)
    instance.py               # SignalInstance (79-field state object)
    transitions.py            # pure transition fn + matrix + guards
    registry.py               # SignalFSMManager (locking, sweep, evaluate_tick)

  persistence/                # was signals_persistence.py (973)        (Phase 4)
    __init__.py               # back-compat shim (old import path keeps working)
    file_store.py             # SIGNALS_STATE_FILE snapshot read/write
    db_sync.py                # Supabase/async-session upserts
    sanitizer.py              # legacy repair, status mapping, test-row purge

  audit/                      # was audit_ledger.py (928)               (Phase 4)
    ledger.py                 # SignalAuditLedger
    costing.py                # cost breakdown / R-attribution

  outcome/                    # was outcome_tracker.py (885)            (Phase 4)
    tracker.py                # price-update loop
    exits.py                  # T1/T2/SL/time-stop/runner rules
    pnl.py                    # realised R & rupee maths

  explain/                    # was explain.py (678)                    (Phase 4)
    bundle.py                 # immutable explainability assembly (pure)
    render.py                 # frontend-facing key mapping

  pipeline/                   # unchanged shape; consumes quote_quality + diagnostics
  handlers/                   # fail-loud registration                  (Phase 5)
  safety/  risk/  strategies/  features/  validation/  options_intelligence/
  worker.py                   # cadences injectable for tests           (Phase 6)
```

```text
backend/app/api/
  signals.py                  # thin: keeps prefix + tags, includes sub-routers
  signals/                    # was 927 LOC / 33 routes                  (Phase 7)
    __init__.py               # aggregate APIRouter
    _deps.py                  # shared auth + market-guard deps (no lazy imports)
    read.py                   # /active /history /{id} /{id}/deep-dive /performance /status
    lifecycle.py              # /generate /execute-paper /auto-detect /bulk-delete /{id}
    audit.py                  # /audit /audit/void /audit/sanitize /{id}/audit
    controls.py               # /kill-switch /feed-health /paper-wallet /portfolio-strategies
    catalog.py                # /engines /preview /scanner /stream
```

Principles: **one policy in one place** (quote quality, constants, state taxonomy), **no deep imports from `api/`** (route through services), **explicit composition** (container over import-time globals), **fail loud over fail silent**.

## 5. Phases

| Phase | Deliverable | Verify |
|-------|-------------|--------|
| 0 Stop the bleeding | Fix `scheduler.py:17`; add pinned market-data fixture; repair/re-pin the 5 red tests | Signal suite → **0 failed**; `python -c "import app.institutional.scheduler"` exits 0 |
| 1 One quote policy | `quote_quality.py` + `constants.py`; delete 4 fallback helpers & duplicated constants | Unit matrix over status/provider combos; grep proves a single definition |
| 2 Domain taxonomy | `domain/states.py`; resolve C1 (adopt or delete `signal_model.py`) | `pytest`; no duplicate `SignalFSMState`; immutability test updated |
| 3 Diagnostics unify | single `ScanDiagnostics` in `domain/diagnostics.py` | Field-set equality test; `/signals/scanner` contract unchanged |
| 4 Decompose monoliths | `lifecycle/`, `persistence/`, `audit/`, `outcome/`, `explain/` with back-compat shims | `pytest` (old import paths still work); LOC budget check |
| 5 Composition + fail-loud | `container.py`, `reset_for_tests()`, loud handler registration, real `app.signals` façade | conftest drops private-attr poking; registration-failure test raises |
| 6 Observability + worker | `degrade()` + counters replace silent swallows; injectable cadences | Grep-guard test (no `except: pass`); handler-failure counter test |
| 7 API + frontend split | `api/signals/` sub-routers; `SignalsDesk` component split | OpenAPI route-parity test (33 routes); `npm run build` |

## 6. Phase Detail

### Phase 0 — Stop the bleeding
1. `app/institutional/scheduler.py:17`: `from typing Any` → `from typing import Any`. Confirm no other module has the same typo (`grep "from typing [A-Z]"`).
2. Add `tests/conftest.py` fixture `mock_market_feed` (or extend `mock_market_open`) that patches the market service used by `manual_signal_service._resolve_spot` to return a deterministic LIVE quote, and delete the ambient-feed dependency. Point the fixture's LTP at the same level the tests assert (24,800–24,950 band) so drift is 0%.
3. Re-pin the 5 red tests to the current contract (`underlying` / `timeframe` / `trigger`), or keep the legacy aliases *and* add a regression test asserting the alias mapping in `manual_signal_service.py:82-88`.
4. Add an explicit **drift-guard contract test**: manual price 6% off LTP → 400 with the documented message; 3% off → 200.

Exit criteria: `pytest tests -k signal` → 74+ passed, 0 failed; scheduler import clean; no test depends on ambient data.

### Phase 1 — One quote-quality policy
- New `app/signals/quote_quality.py`: `QuoteQuality` (`LIVE | DEGRADED | STALE | CLOSED | OFFLINE`), `classify_quote(quote)`, `is_fallback_quote(quote)`, `is_live_quote(quote)`. Canonical token set = the union already used by the scanner (`OFFLINE, DEGRADED, STALE, CLOSED, INVALID`) so behaviour only ever *tightens* for the manual path (documented, intentional).
- New `app/signals/constants.py`: `TICK`, `MIN_GAP_PCT`, `MIN_GAP_RISK_FRACTION`, `MIN_RISK_PCT`, `MAX_ENTRY_WIDTH_R`, `MAX_QUOTE_DRIFT`.
- Rewire `scanner.py`, `pipeline/data_acquisition.py`, `manual_signal_service.py`, `api/signals.py` to import from the new modules; delete all four helpers and both constant blocks.
- Behaviour note for reviewers: the manual path becomes **stricter** (a `STALE`/`DEGRADED` feed now blocks manual generation with a 400/503 instead of registering a signal). That is the intended safety fix; call it out in the PR description.

### Phase 2 — Domain taxonomy decision
- Create `app/signals/domain/states.py` holding the single `SignalFSMState` literal, `ALLOWED_TRANSITIONS`, and `TERMINAL_STATES`. `fsm.py` imports it; delete the duplicate declaration.
- Resolve C1 with an explicit decision (§10 Q1):
  - **Adopt:** make `domain/models.py` the serialisation contract — wire `to_wire_dict`/`to_audit_dict`/`to_research_dict` (fsm.py:257-297) and the API response models through it, so the models earn their place.
  - **Delete:** remove `signal_model.py` and the five projection properties, and retarget `test_signal_model_immutability.py` at the real contract (`to_wire_dict` field stability across transitions). Removing 131 LOC and 5 import sites is the lower-risk default.

### Phase 3 — Diagnostics unification
- Move `ScanDiagnostics` to `domain/diagnostics.py`; `scanner.py` imports it instead of redefining. Keep field sets identical; if the `CLOSED` data-quality value must be visible to the scanner, keep it in the shared model.

### Phase 4 — Decompose monoliths
- Split per §4. **Every split ships a back-compat shim**: `signals_persistence.py`, `fsm.py`, `audit_ledger.py`, `outcome_tracker.py`, and `explain.py` remain as thin re-export modules (`from app.signals.lifecycle.registry import signal_fsm  # noqa: F401`) so the 13 signal test files, `app/api/*`, and `app/main.py` keep working untouched.
- Constraint: preserve the FSM transition matrix and P&L maths **byte-for-byte**; this phase is a move, not a rewrite. `tests/test_fsm_transition_matrix.py` (all 169 pairs) is the guard.
- LOC budget: no file > 400 LOC; `worker.py` split out of the cadence loop in Phase 6.

### Phase 5 — Composition + fail-loud wiring
- `app/signals/container.py`: constructs/serves the singletons (`signal_fsm`, `scanner_engine`, `outcome_tracker`, `signal_audit_ledger`, `signal_paper_engine`, `signal_event_bus`, `kill_switch`, `feed_circuit`, …) plus `reset_for_tests()`. Module-level singletons stay as aliases for back-compat but resolve through the container.
- `handlers/__init__.py`: keep auto-registration but make failure **raise** during startup and log an error in degraded mode — no more `try/except: pass` at `fsm.py:78-82`.
- `tests/conftest.py`: replace private-state poking (`signal_fsm._lock`, `signal_fsm._signals`) with `container.reset_for_tests()`.
- `app/signals/__init__.py`: real façade with explicit `__all__`; `api/` imports from the façade, not deep paths.

### Phase 6 — Observability + worker testability
- Add a small `degrade(component, reason, **ctx)` helper in `app/signals/observability.py` that logs at warning with structured context and increments a per-component counter. Replace the ~60 silent swallows, prioritising `persistence/`, `outcome/`, `lifecycle/transitions.py`, and `pipeline/enrichment.py`.
- Expose counters on the existing `/api/v1/signals/feed-health` (or a new `/signals/health`) so degraded code paths are visible next to degraded feeds.
- `worker.py`: make `risk_interval_seconds` / `scalp_scan_interval_seconds` / `intraday_scan_interval_seconds` fully injectable and expose a single-cycle `run_once()` coroutine so cadence logic is unit-testable without sleeping.

### Phase 7 — API + frontend split
- Split `api/signals.py` into the sub-routers in §4; remove all 9 function-level imports by moving shared dependencies into `_deps.py`.
- Frontend: split `SignalsDesk.tsx` into `desk/` (tabs, tables, filters, KPI header); split `useSignalsData.ts` into fetch + derive hooks; keep `signalsNormalize.ts` as the single normaliser. No visual/behavioural change.

## 7. Migration & Compatibility

- **Import paths:** every split keeps a re-export shim at the historical path (`app.signals.signals_persistence`, `app.signals.fsm`, `app.signals.audit_ledger`, `app.signals.outcome_tracker`, `app.signals.explain`). Shims are marked deprecated and removed in a later cycle.
- **State-file format:** `signals_state.json` schema is unchanged; `persistence/file_store.py` reads the same keys. Sanitizer behaviour (`signals_persistence.py:663`, `:849`) is preserved verbatim.
- **API contract:** 33 routes, same paths/methods/response envelopes. Phase 7 ships an OpenAPI route-parity test so the split is provably transparent.
- **Quote-quality tightening (Phase 1)** is the one intentional behaviour change: manual generate on a `STALE`/`DEGRADED` feed now fails closed. Documented in `EXECUTION_SAFETY.md` and flagged in the PR.
- **No DB/schema migration** required this cycle.

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Splitting `fsm.py`/`outcome_tracker.py` changes trading/P&L maths | Move-only phase, no logic edits; `test_fsm_transition_matrix.py` (169 pairs) + audit/P&L suites must pass unmodified |
| Phase 1 tightening blocks operators who manually enter during degraded feeds | Deliberate fail-closed change; explicit 400/503 message naming the feed status; covered by a contract test |
| Back-compat shims hide the new structure and never get removed | Shims carry a deprecation marker + tracked follow-up; `__init__.py` façade is the documented entry point |
| Container/DI refactor disturbs import-time singletons used by `main.py` lifecycle | Singletons stay module-level aliases resolving through the container; startup/shutdown order in `core/service_lifecycle.py` verified by an app-boot smoke test |
| Replacing ~60 silent swallows surfaces hidden failures as noise | `degrade()` logs at warning with counters and never raises; counters visible in the health endpoint for triage |
| Test re-pinning masks a genuine product bug (A2) | The drift guard is *correct*, the tests were wrong — add the explicit drift-guard contract test (400 at 6%, 200 at 3%) so the guard is positively covered |
| Frontend split causes visual regressions | No styling/behaviour changes; manual check of the tabbed desk + `npm run build` |

## 9. Verification Harness

Fixtures/tests this plan adds:

1. `tests/conftest.py::mock_market_feed` — deterministic LIVE quote, removes ambient-feed coupling.
2. `tests/test_quote_quality_policy.py` — matrix over `(status, provider)` → expected quality/fallback flag, covering all four former call sites.
3. `tests/test_manual_signal_drift_guard.py` — 6% drift → 400; 3% drift → 200; degraded feed → fail closed.
4. `tests/test_signal_diagnostics_contract.py` — one `ScanDiagnostics`, field-set equality, `/signals/scanner` shape unchanged.
5. `tests/test_signal_module_boundaries.py` — no `app/api/**` deep import into `app.signals.*` internals; no duplicate `SignalFSMState`; no `except ...: pass` left in `app/signals/`; no file > 400 LOC.
6. `tests/test_signal_container_reset.py` — `reset_for_tests()` restores clean state; handler-registration failure is loud.
7. `tests/test_signals_openapi_parity.py` — 33 routes present with unchanged paths/methods.

Commands:

```powershell
# backend
cd backend
.venv\Scripts\python.exe -m pytest tests -q                 # full suite
.venv\Scripts\python.exe -m pytest tests -k signal -q       # signal module

# frontend
cd frontend
npm run build
```

Baseline to beat: **74 passed / 5 failed** → target **0 failed**, with the signal suite green even when the market is closed and the local feed is stale.

## 10. Open Questions (resolve before Phase 2)

- **Q1 (blocking Phase 2):** Adopt `signal_model.py` as the serialisation contract, or delete it with the five `SignalInstance` projection properties? *Recommendation: delete* — zero production consumers, and `to_wire_dict` / `to_audit_dict` already own the external shape.
- **Q2:** Should manual generation fail closed on `DEGRADED` feeds, or warn-and-allow behind an explicit flag? *Recommendation: fail closed by default, with an opt-in `allow_degraded_feed` flag for desk operators.*
- **Q3:** Is a 400-LOC per-file budget workable for `lifecycle/transitions.py` and `audit/costing.py`, or should the ceiling be 500?
- **Q4:** Fully container-manage the ~25 singletons (bigger diff) or keep module-level aliases with a reset seam (smaller diff)? *Recommendation: aliases + reset seam this cycle.*
- **Q5:** Is legacy request-field support in `manual_signal_service.py:82-88` (`instrument_id`, `candle_timeframe`, `trigger_level`) still required, or can it be dropped once tests are re-pinned?

## 11. File References

| Concern | Location |
|---|---|
| Broken scheduler module | `backend/app/institutional/scheduler.py:17` |
| Drift guard (root cause of red suite) | `backend/app/signals/manual_signal_service.py:41`, `:128-145` |
| Manual pipeline steps | `backend/app/signals/manual_signal_service.py:7-18` |
| Duplicate fallback helpers | `pipeline/data_acquisition.py:57`, `scanner.py:100`, `manual_signal_service.py:67`, `api/signals.py:116` |
| Duplicate `ScanDiagnostics` | `scanner.py:57`, `pipeline/data_acquisition.py:37` |
| Duplicate `SignalFSMState` | `fsm.py:20-34`, `signal_model.py:19-33` |
| Domain models + projections | `signal_model.py:1-131`, `fsm.py:301-390` |
| Handler registration | `handlers/__init__.py:53`, `fsm.py:78-82` |
| Event bus | `event_bus.py:40-169` |
| Worker cadences | `worker.py:43-53`, `:280-338` |
| API surface | `backend/app/api/signals.py:125-905` |
| Test fixtures | `backend/tests/conftest.py:10-36` |
| Frontend desk | `frontend/src/components/signals/SignalsDesk.tsx`, `SignalDetailDrawer.tsx`, `useSignalsData.ts` |
| Procedural reference | `docs/SIGNAL_GENERATION_PROCEDURE.md` |
| Safety reference | `docs/EXECUTION_SAFETY.md` |