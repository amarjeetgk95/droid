# Signal Module — Institutional-Grade Implementation Plan

**Project:** Droid — AI-Powered Indian F&O Market Analysis Platform  
**Scope:** `backend/app/signals/` (main F&O Signal Centre) + `backend/app/institutional/`  
**Goal:** Unify both signal systems into a single production-grade, audit-compliant, multi-instrument signal platform.

---

## Executive Summary

There are currently **two parallel, divergent signal systems**:

| System | Location | Status |
|---|---|---|
| **Main F&O Signal Centre** | `app/signals/` | Production-facing, 11 strategies, 13-state FSM, but **no distributed safety** |
| **Institutional Pipeline** | `app/institutional/` | 19-stage pipeline, 16-state FSM, CAS atomicity, feed circuit breaker — but **isolated, no broker integration, not used by UI** |

The institutional module has the right **patterns** (control hierarchy, CAS, clock validation, 12-check guard, circuit breaker) but is incomplete. The main signal centre has the **features** (strategies, paper trading, SSE, outcome tracking) but lacks institutional rigour.

**This plan unifies both, elevating the main signal centre to institutional grade by importing and extending the institutional patterns.**

---

## Phase 0 — Foundation: Unified Signal Model (Week 1)

### Objective
Replace the diverging `SignalInstance` (Pydantic) and `Signal` (dataclass) with a single canonical signal model.

### Tasks

**0.1 Create `app/signals/models.py` — Canonical Signal Model**
```
- Merge SignalInstance fields (options, Greeks, breakeven ratchet, staged targets, friction)
- Merge institutional Signal fields (execution_intent_id, ttl_ms, fsm_state enum)
- Use Pydantic v2 BaseModel for validation + serialization
- Add computed fields for UI display
- Add `to_audit_dict()` method for structured logging
- Preserve ALL existing fields — no data loss
```

**0.2 Create `app/signals/fsm_unified.py` — Unified FSM**
```
- States: DETECTED → VALIDATED → ARMED → TRIGGERED → CONFIRMED → T1/T2/SL/TIME_STOP/EXPIRED/INVALIDATED → CLOSED
- ALLOWED_TRANSITIONS dict (same as current fsm.py)
- Thread-safe in-memory with threading.RLock (step 0)
- CAS stub for RISK_APPROVED → EXECUTION_PENDING (returns NotImplementedError until Phase 3)
- All existing transition side-effects (ratchet, TTL, timestamps, friction, audit append)
- Backward-compatible: SignalFSMManager interface unchanged
```

**0.3 Migrate `app/signals/fsm.py` → `app/signals/fsm_legacy.py`**
```
- Rename current fsm.py to fsm_legacy.py
- Update all imports in worker.py, scanner.py, etc. to fsm_unified
- Keep fsm_legacy.py until all tests pass, then delete
```

**0.4 Create `app/signals/audit_unified.py` — Unified Audit Record**
```
- Merge FSMTransitionAudit + AuditRecord fields
- Fields: signal_id, from_state, to_state, market_price, reason_code, guard_snapshot
          pipeline_stage, feed_health, clock_drift_ms, sequence_id, risk_decision
          execution_intent_id, broker_order_id, ai_status, cross_market_status
- Append-only list with 2000-entry cap (up from 1000)
- Write-through to PostgreSQL via existing signals_persistence
```

### Verification
```bash
pytest backend/tests/test_signal_* -x --tb=short
# All existing signal tests must pass with zero changes
```

---

## Phase 1 — Control Hierarchy: Institutional Pipeline for F&O (Week 2)

### Objective
Wrap the main F&O signal scanner in a 10-stage control hierarchy identical to the institutional pattern, but adapted for F&O options.

### Tasks

**1.1 Create `app/signals/control_hierarchy.py` — 10-Stage F&O Pipeline**
```
Stage 1: MARKET SESSION CHECK        → blocks outside NSE hours
Stage 2: QUOTE FRESHNESS GATE        → reject fallback/stale quotes (>15s)
Stage 3: FEED CIRCUIT BREAKER        → sequence gaps, clock drift, stale suppression
Stage 4: CONTRACT NORMALIZATION      → ATM resolver, tick-size validation
Stage 5: TIME-SYNC SNAPSHOT          → synchronized spot + options + OI snapshot
Stage 6: MARKET INTELLIGENCE          → multi-domain scoring (technical + MTF + F&O + regime)
Stage 7: STRATEGY EVALUATION          → 11 strategies → SignalCandidates
Stage 8: CONFLUENCE + SECURITY GATES  → score ≥70, 4-gate filter
Stage 9: RISK ENVELOPE                → position sizing, margin, correlation
Stage 10: ATOMIC FSM REGISTER         → DETECTED with CAS-ready transition
```

**1.2 Integrate Feed Circuit Breaker from institutional module**
```
- Import FeedCircuitBreaker from app.institutional.feed_circuit
- Instantiate per-instrument in scanner startup
- Call feed_circuit.on_sequence_result() in Stage 3
- Suppress new candidates when feed_circuit.suppresses(instrument_id) is True
- Add EOD resync: feed_circuit.reset(instrument_id) at market open
```

**1.3 Integrate Clock Validation from institutional module**
```
- Import EventClock, MarketSessionClock from app.institutional.clocks
- In Stage 1: check session_clock.current_state() instead of calendar_service.can_trade_now()
- In Stage 3: check clock drift > 2000ms → reject with CLOCK_DRIFT
- Log drift_ms to audit record
```

**1.4 Create `app/signals/snapshot_buffer.py` — F&O Synchronized Snapshot**
```
- Import synchronized_buffer from app.institutional.snapshot_buffer
- At Stage 5: ingest spot quote + ATM option chain + OI + VWAP into synchronized_buffer
- For NIFTY/BANKNIFTY: produce cross-instrument snapshot (NIFTY ↔ BANKNIFTY)
- If snapshot.status == "CROSS_MARKET_DATA_NOT_SYNCHRONIZED" → log to audit but continue
- Snapshot stored in SignalInstance.synchronized_snapshot field
```

**1.5 Update Scanner to use Control Hierarchy**
```
In scanner.py _scan_instrument():
  1. Replace direct market_service.get_quote() with Stage 1-2 gates
  2. After getting quote: call control_hierarchy.process_scan_request(instrument, quote, candles)
  3. If any stage returns REJECTED/FEED_DEGRADED → log and skip
  4. Only proceed to strategy evaluation if all 10 stages pass
  5. On DETECTED: signal_fsm.register() with enriched audit record
```

### Verification
```bash
pytest backend/tests/test_signal_hardening.py -x --tb=short
pytest backend/tests/test_signal_scanner*.py -x --tb=short
```

---

## Phase 2 — Execution Guard & Atomicity (Week 3)

### Objective
Replace the current simple trigger gate with the institutional 12-check final execution guard, and implement CAS atomicity for the ARMED → TRIGGERED → EXECUTION_PENDING flow.

### Tasks

**2.1 Create `app/signals/execution_guard.py` — 12-Check Final Execution Guard**
```
Import and adapt from app.institutional.signal final_execution_guard()

12 Checks:
  1.  Signal state is CONFIRMED or ARMED
  2.  Execution intent is unique (no duplicate order)
  3.  TTL not exceeded (recheck at guard time)
  4.  Feed health is HEALTHY
  5.  Market session is OPEN
  6.  Slippage within tolerance (entry_price vs spot_price)
  7.  Contract spec present and valid
  8.  Quantity is positive and within limits
  9.  Price quantized to tick size
  10. Risk approved (portfolio risk check)
  11. No duplicate order in last 60s
  12. Setup not invalidated since risk approval

Return: (passed: bool, failed_check: str | None, reason: str)
```

**2.2 Implement CAS Atomicity — Phase 2A (In-Memory)**
```
In app/signals/fsm_unified.py:

Add to SignalFSMManager:
  def cas_to_execution_pending(self, signal_id: str, now_ms: int) -> tuple[bool, str | None]:
      """CAS: only transition from ARMED/CONFIRMED to EXECUTION_PENDING if state matches."""
      with self._lock:
          sig = self._signals.get(signal_id)
          if not sig:
              return False, "Signal not found"
          if sig.fsm_state not in ("ARMED", "CONFIRMED"):
              return False, f"Illegal CAS from {sig.fsm_state}"
          # CAS check: expected state must be ARMED or CONFIRMED
          if sig.fsm_state == "EXECUTION_PENDING":
              return True, None  # idempotent — already transitioned
          ok, err = self.transition(signal_id, "EXECUTION_PENDING", now_ms=now_ms, reason="CAS_EXECUTION_INTENT")
          if not ok:
              return False, err
          sig.execution_intent_id = str(uuid.uuid4())
          return True, None

Add execution_intent_id field to SignalInstance (already exists in institutional Signal)
```

**2.3 Implement CAS Atomicity — Phase 2B (Redis, Post-Deployment)**
```
Add optional Redis CAS backend:
  - Config flag: SIGNAL_FSM_BACKEND = "memory" | "redis"
  - If redis: use Redis SET NX with state as value, TTL = signal.ttl_ms
  - CAS: WATCH signal_id, check state, MULTI/EXEC transition
  - Fallback to memory if Redis unavailable (logged warning)
  - Redis connection via existing app Redis config
```

**2.4 Update Risk Loop to Use Execution Guard**
```
In worker.py _run_position_risk_loop():
  - Before calling evaluate_tick() → transition to TRIGGERED:
    Call execution_guard.check_all(signal, latest_price, ...)
  - Only trigger if ALL 12 checks pass
  - Record guard_snapshot in FSMTransitionAudit
  - If any check fails → transition to INVALIDATED with reason
```

**2.5 Add Repeated TTL Checks**
```
- check_ttl() at: signal creation, AI completion, validation, risk approval,
                 execution intent creation, final guard, broker submission
- Each check appends TTL audit entry with remaining_ms
- If expired at ANY stage → force EXPIRED state, log, stop pipeline
```

### Verification
```bash
pytest backend/tests/test_signal_hardening.py -x --tb=short
# Add new tests: test_execution_guard_12_checks.py, test_cas_atomicity.py
```

---

## Phase 3 — State Recovery & Reconciliation (Week 4)

### Objective
Implement crash-safe state recovery, broker reconciliation with ambiguity detection, and the institutional shadow mode.

### Tasks

**3.1 Create `app/signals/state_recovery.py` — Crash Recovery**
```
- On startup: load signals from PostgreSQL WHERE fsm_state NOT IN (CLOSED, EXPIRED, INVALIDATED)
- Rebuild in-memory SignalFSMManager from DB state
- For each recovered signal:
  - Check if TTL exceeded → force EXPIRED
  - Check if market is closed → force EXPIRED/CLOSED
  - Re-evaluate against latest quote → INVALIDATED if setup broken
- Log recovery summary: recovered_count, expired_count, invalidated_count
- Hook into FastAPI lifespan startup event
```

**3.2 Create `app/signals/reconciliation.py` — Broker Reconciliation**
```
States:
  - RECONCILED: broker confirms order, matches execution intent
  - BROKER_TIMEOUT: no response within 10s
  - API_ERROR: HTTP error from broker
  - AMBIGUOUS: partial fill, quantity mismatch
  - RECONCILIATION_REQUIRED: manual intervention needed

Flow:
  - On EXECUTION_PENDING: start 10s broker timer
  - On broker response: match execution_intent_id → order_id
    - If match: RECONCILED, record broker_order_id
    - If partial fill: AMBIGUOUS, record actual_qty vs intended_qty
    - If timeout: BROKER_TIMEOUT → retry once, then RECONCILIATION_REQUIRED
  - All outcomes → AuditRecord + Telegram notification
```

**3.3 Implement Shadow Mode for Paper Trading**
```
- Add APP_MODE = "SHADOW" | "PAPER" | "LIVE" to config
- In SHADOW: execute pipeline through all 10 stages, generate execution_intent,
             but NEVER call paper_engine.place_order()
             → log as SHADOW_EXECUTION in audit
- In PAPER: call paper_engine.place_order() with simulated fills
- In LIVE: call broker API (future)
- Paper engine uses fill_reconciler with Black76 + charges (already exists)
```

**3.4 Create `app/signals/decimal_safety.py` — Decimal Types for F&O**
```
- Import D, Price, Quantity, Money from app.institutional.decimal_types
- Replace all float arithmetic in:
  - fsm.py (risk_r, breakeven trigger, friction)
  - risk_engine.py (position sizing)
  - paper_engine.py (P&L calculation)
  - fill_reconciler.py (charges, slippage)
- Add validate_quantity() and normalize_price_to_tick() to signal creation
```

### Verification
```bash
# Simulate crash: kill worker mid-scan, restart, verify state recovery
pytest backend/tests/test_signals_ghost_open_settlement.py -x --tb=short
# Add: test_state_recovery.py, test_reconciliation.py
```

---

## Phase 4 — Dual Persistence & Transaction Safety (Week 5)

### Objective
Replace dual-write with atomic dual-persistence (PostgreSQL primary + local JSON fallback with transaction safety).

### Tasks

**4.1 Atomic Dual-Write in `app/signals/signals_persistence.py`**
```
Current: PostgreSQL upsert + local JSON write happen independently → risk of divergence

Fix:
  - Write to PostgreSQL FIRST (primary source of truth)
  - On DB success: write local JSON (temp file → atomic rename)
  - On DB failure: raise exception, do NOT write local JSON
  - On local JSON failure: log warning, DB is authoritative
  - Add persist_executed_signal() return value: (success, error)
  - Caller logs but does not swallow exceptions silently
```

**4.2 PostgreSQL as Single Source of Truth**
```
- On startup: rebuild in-memory FSM from DB (Phase 3.1)
- Every FSM transition: write to DB, then update in-memory
- Every 30s: reconcile in-memory vs DB → log discrepancies
- signals_state.json becomes CACHE only, never authoritative
- Add migration to add new columns: execution_intent_id, synchronized_snapshot, feed_health
```

**4.3 Instrument Registry Integration**
```
- Import asset_registry from app.institutional.instrument_registry
- Replace APPROVED_UNDERLYINGS in contract_resolver.py with registry lookup
- Add contract_spec validation (tick_size, lot_size, min_qty) at signal creation
- Add asset_class field to SignalInstance: "INDIAN_EQUITY_OPTIONS" | "CRYPTO"
```

### Verification
```bash
# Simulate DB outage during write → verify no partial state
pytest backend/tests/test_signals_persistence_resilience.py -x --tb=short
```

---

## Phase 5 — Scoring Engine Unification (Week 6)

### Objective
Merge `SignalFusion` and `ConfluenceEngine` into a single institutional-grade scoring engine with dynamic weight renormalization.

### Tasks

**5.1 Create `app/signals/scoring_engine.py` — Unified Scorer**
```
- Merge: SignalFusion (app/signals/signal_fusion.py) + ConfluenceEngine (app/signals/confluence.py)
- Input dimensions:
  1. Technical (40% default): trend, momentum, volume, volatility, patterns
  2. Multi-Timeframe (20%): alignment across 1M/5M/15M/1H
  3. F&O Context (15%): PCR, OI buildup, max pain, IV rank
  4. Regime (10%): trending/ranging/volatile classification
  5. AI Advisory (10%): OpenRouter/NVIDIA/Gemini/local model
  6. Event Risk (5%): expiry, budget, elections (from event_engine)

- Dynamic weight renormalization:
  - If AI unavailable: redistribute AI 10% across other dimensions proportionally
  - If F&O degraded: redistribute F&O 15% to technical + MTF
  - If VWAP degraded: reduce MTF weight, increase technical

- Output: Score 0-100, ARMED if ≥70, CONFLICTED if opposing signals
- Config-driven weights from scoring_weights.json (already exists)
```

**5.2 AI Timeout & Degradation**
```
- AI call timeout: 2s max (configurable via AI_PROVIDER_TIMEOUT_MS)
- On timeout: mark AI as DEGRADED, renormalize weights, continue
- On AI error: mark AI as UNAVAILABLE, renormalize weights, continue
- Never block signal creation on AI availability
```

**5.3 Conflict Resolution**
```
- If two strategies emit opposing signals (LONG + SHORT):
  - Check regime: if trending, follow regime direction
  - If ranging, require higher confluence threshold (80 vs 70)
  - Log conflict in audit record with both candidates
```

### Verification
```bash
pytest backend/tests/test_signal_win_rate_and_persistence_fix.py -x --tb=short
# Add: test_scoring_engine_unified.py, test_weight_renormalization.py
```

---

## Phase 6 — Multi-Instrument & Multi-Asset Expansion (Week 7)

### Objective
Extend the unified signal system beyond NIFTY/BANKNIFTY/SENSEX to crypto and multi-instrument portfolios.

### Tasks

**6.1 Crypto Signal Engine Integration**
```
- Import CryptoSignalEngine from app.services.crypto_signal_engine
- Register BTCUSD, ETHUSD in asset_registry with CRYPTO asset_class
- Extend control hierarchy Stage 1 (session check) → 24x7 for CRYPTO
- Extend Stage 3 (feed circuit) → funding rate + liquidation feeds
- Add crypto-specific dimensions to scoring engine:
  - Funding squeeze (5% weight redistribution)
  - Basis divergence (5% weight redistribution)
  - Depth imbalance flow (technical dimension)
- Crypto signals use separate strategy registry: depth_imbalance, funding_squeeze, basis_divergence
```

**6.2 Multi-Instrument Correlation Guard**
```
- In portfolio risk engine: add correlation matrix for NIFTY/BANKNIFTY/SENSEX
- If two correlated instruments both ARMED within 5 min → raise correlation penalty
- Max correlated exposure: 40% of portfolio notional
- Log correlation events in audit trail
```

**6.3 Portfolio-Level Greeks Aggregation**
```
- Import portfolio_greeks from app.signals.portfolio_greeks
- On each new ARMED signal: compute portfolio delta, gamma, theta, vega
- Block signal if:
  - Net delta > ±500 (NIFTY lot equivalent)
  - Net gamma > ±2000
  - Theta burn > ₹5000/day
- Greeks recalculated every 3s in risk loop
```

### Verification
```bash
pytest backend/tests/test_crypto_signals.py -x --tb=short
# Add: test_multi_instrument_correlation.py, test_portfolio_greeks.py
```

---

## Phase 7 — Observability, Alerting & Monitoring (Week 8)

### Objective
Add institutional-grade observability: structured logging, metrics, alerting, and dashboards.

### Tasks

**7.1 Structured Logging (Already Using structlog — Enhance)**
```
- All signal lifecycle events: structured JSON with signal_id, instrument, state, price, timestamp
- Pipeline stage transitions: log stage_in, stage_out, duration_ms
- FSM transitions: log from_state, to_state, reason, guard_snapshot
- Feed circuit events: log degradation, resync, recovery
- AI calls: log prompt, response, latency_ms, status
- Risk decisions: log all check results, portfolio state
- Broker reconciliation: log order_id, fill_qty, fill_price, status
```

**7.2 Metrics (Prometheus / StatsD)**
```
Counters:
  - signals_detected_total, signals_armed_total, signals_confirmed_total
  - signals_expired_total, signals_invalidated_total, signals_rejected_total
  - fsm_transitions_total{from,to}, feed_degraded_total, feed_resync_total
  - ai_calls_total, ai_timeouts_total, ai_errors_total
  - broker_orders_total, broker_fills_total, broker_timeouts_total
  - paper_pnl_total, paper_trades_total, paper_win_rate

Gauges:
  - active_signals, scanner_cadence_seconds, risk_loop_latency_ms
  - portfolio_delta, portfolio_gamma, portfolio_theta, portfolio_vega
  - feed_health{instrument}, fsm_state{signal_id}

Histograms:
  - signal_lifetime_seconds, time_to_trigger_seconds, time_to_t1_seconds
  - scanner_cycle_duration_seconds, risk_cycle_duration_seconds
  - ai_latency_seconds, broker_latency_seconds
```

**7.3 Alerting Rules**
```
Critical:
  - Feed circuit degraded for >60s on any instrument
  - Clock drift > 2000ms on any instrument
  - Broker timeout rate > 10% over 5min
  - State recovery count > 5 in last hour
  - PostgreSQL persistence failure

Warning:
  - Signal expiry rate > 30% (indicates scanner quality issue)
  - AI timeout rate > 20%
  - Risk rejection rate > 40%
  - Scanner cycle overruns budget (>2500ms)
  - Memory usage > 80% (in-memory signal count approaching cap)
```

**7.4 Dashboard (Grafana / Custom)**
```
Panels:
  - Signal lifecycle funnel: DETECTED → ARMED → CONFIRMED → T1/T2/SL
  - Win rate by strategy (rolling 7d, 30d)
  - Scanner cycle time (p50, p95, p99)
  - Feed health status per instrument
  - Portfolio Greeks over time
  - AI latency + timeout rate
  - Broker reconciliation status
  - Paper trading P&L curve
```

### Verification
```bash
# Verify structlog output is valid JSON
# Verify Prometheus metrics endpoint returns expected metrics
# Manual: check Grafana dashboard renders correctly
```

---

## Phase 8 — Testing at Scale (Week 9)

### Objective
Add end-to-end, load, and chaos tests to validate institutional-grade reliability.

### Tasks

**8.1 End-to-End Signal Lifecycle Test**
```
test_e2e_signal_lifecycle.py:
  1. Mock market data feed (synthetic ticks for NIFTY)
  2. Run scanner → signal DETECTED
  3. Run risk loop → signal CONFIRMED
  4. Run risk loop with T1 hit → TARGET_1_HIT
  5. Run risk loop with T2 hit → TARGET_2_HIT → CLOSED
  6. Assert: all FSM transitions valid, all audit records written, P&L correct
  7. Assert: PostgreSQL has correct final state
```

**8.2 Load Test: Scanner Under Stress**
```
test_scanner_load.py:
  - 1000 synthetic ticks/sec for 5 minutes
  - Assert: no memory leaks, scanner cycle p95 < budget
  - Assert: feed circuit activates correctly under load
  - Assert: no duplicate signals, no illegal FSM transitions
  - Assert: PostgreSQL write queue does not back up
```

**8.3 Chaos Test: Feed Degradation**
```
test_feed_chaos.py:
  1. Normal scanning → signals detected
  2. Inject 5 sequence gaps → feed circuit degrades
  3. Assert: no new signals generated during degradation
  4. Inject 20s of clean data → feed circuit resyncs
  5. Assert: scanning resumes, no stale signals used
```

**8.4 Chaos Test: Crash Recovery**
```
test_crash_recovery.py:
  1. Create 10 active signals (CONFIRMED, TARGET_1_HIT, ARMED)
  2. Kill worker process (simulate SIGKILL)
  3. Restart worker
  4. Assert: state_recovery rebuilds FSM from DB
  5. Assert: expired signals → EXPIRED, open signals → re-evaluated
  6. Assert: no duplicate execution intents
```

**8.5 Property-Based Test: FSM Invariants**
```
test_fsm_invariants.py (hypothesis):
  - Generate random sequence of valid transitions
  - Assert: ALLOWED_TRANSITIONS never violated
  - Assert: terminal states (CLOSED, EXPIRED, INVALIDATED) have no outgoing transitions
  - Assert: TTL never negative
  - Assert: breakeven ratchet only activates in CONFIRMED or TARGET_1_HIT
  - Assert: friction calculation never produces negative P&L for a winning trade
```

### Verification
```bash
pytest backend/tests/ -x --tb=short -m "not slow"   # Unit tests
pytest backend/tests/ -x --tb=short -m "slow"        # E2E + load tests
```

---

## Phase 9 — Production Hardening (Week 10)

### Objective
Add production-grade operational concerns: health checks, graceful shutdown, config management, secrets hygiene.

### Tasks

**9.1 Health Check Endpoints**
```
GET /healthz/live     → 200 if process is alive
GET /healthz/ready    → 200 if:
  - PostgreSQL reachable
  - Redis reachable (if configured)
  - Market data feed connected
  - FSM state recovery complete
  - Scanner loop running
GET /healthz/signal   → Detailed:
  - active_signal_count
  - feed_health per instrument
  - scanner_cadence
  - last_successful_scan timestamp
  - AI provider status
```

**9.2 Graceful Shutdown**
```
- On SIGTERM/SIGINT:
  1. Set _running = False
  2. Wait for current risk cycle to complete (max 5s)
  3. Cancel scanner loop
  4. Flush all pending audit records to PostgreSQL
  5. Save signals_state.json
  6. Close DB connections
  7. Log shutdown summary
```

**9.3 Configuration Management**
```
- Move all hardcoded values to config:
  - Scanner intervals: SCALP_INTERVAL_S, INTRADAY_INTERVAL_S
  - Risk loop interval: RISK_LOOP_INTERVAL_S, RISK_CYCLE_BUDGET_MS
  - TTL defaults: SIGNAL_TTL_S, RUNNER_TTL_S
  - Confluence threshold: ARMED_THRESHOLD (70)
  - Breakeven ratchet: BREAKEVEN_RATCHET_R (0.8)
  - Broker timeout: BROKER_ORDER_TIMEOUT_S (10)
  - Feed circuit thresholds: CLOCK_DRIFT_MS (2000), STALE_QUOTE_S (15)
- Config sources (priority order):
  1. Environment variables
  2. .env file
  3. config/*.json
  4. Hardcoded defaults
```

**9.4 Secrets Hygiene**
```
- Audit all files for hardcoded API keys, JWT secrets, DB credentials
- Move to environment variables or Supabase Vault
- Add pre-commit hook to detect new hardcoded secrets
- Verify no secrets in git history (git log --all -- Secrets filter)
```

**9.5 Rate Limiting & Backpressure**
```
- AI provider: max 1 call per 2s per instrument (prevent API exhaustion)
- Broker API: max 10 orders/min (Fyers limits)
- Telegram notifications: max 1 message per 30s per signal
- Scanner: if PostgreSQL write queue > 100, slow down scanner
- Risk loop: if cycle > budget, log warning, skip non-critical steps
```

### Verification
```bash
# Health checks
curl http://localhost:8000/healthz/ready
# Graceful shutdown
kill -SIGTERM <pid> && wait
# Secrets audit
grep -r "api_key\|secret\|password\|token" backend/app/ --include="*.py" | grep -v "os.environ\|\.env"
```

---

## Implementation Timeline

| Phase | Duration | Dependencies | Risk |
|---|---|---|---|
| Phase 0: Unified Model | Week 1 | None | Low — internal refactor |
| Phase 1: Control Hierarchy | Week 2 | Phase 0 | Medium — scanner integration |
| Phase 2: Execution Guard + CAS | Week 3 | Phase 0 | Medium — FSM changes |
| Phase 3: State Recovery | Week 4 | Phase 2 | Low — new code |
| Phase 4: Persistence Safety | Week 5 | Phase 3 | Medium — DB migration |
| Phase 5: Scoring Unification | Week 6 | Phase 0 | Low — merge existing |
| Phase 6: Multi-Asset | Week 7 | Phase 1 | Medium — crypto integration |
| Phase 7: Observability | Week 8 | All prior | Low — additive |
| Phase 8: Testing | Week 9 | All prior | Low — additive |
| Phase 9: Production Hardening | Week 10 | All prior | Low — additive |

**Total: 10 weeks, 2.5 months**

---

## Key Architectural Decisions

### 1. Unified FSM Over Parallel Systems
**Decision:** Migrate the main signal centre to use institutional FSM patterns, retire the isolated institutional pipeline as a separate system.  
**Rationale:** Two parallel systems cause code duplication, divergent behaviour, and doubled maintenance cost. The institutional pipeline's patterns (CAS, circuit breaker, 12-check guard) are extracted into shared modules used by the unified F&O signal centre.

### 2. In-Memory FSM with DB Write-Through (Not Distributed Lock Yet)
**Decision:** Keep in-memory FSM for single-worker deployment, add CAS stub, implement Redis CAS in Phase 2B.  
**Rationale:** Current deployment is single-process (FastAPI + one worker). Distributed locks add complexity. CAS stub ensures the interface is ready for Redis without blocking current deployment.

### 3. PostgreSQL as Single Source of Truth
**Decision:** DB is authoritative; local JSON is cache only.  
**Rationale:** Dual-write without transactions causes state divergence. PostgreSQL already exists; making it authoritative eliminates divergence and enables state recovery.

### 4. Institutional Pipeline Patterns Extracted as Shared Modules
**Decision:** Feed circuit breaker, clock validation, snapshot buffer, decimal types, execution guard become shared `app/signals/` modules (or `app/shared/`).  
**Rationale:** Avoid importing from `app.institutional` into `app.signals` (circular dependency risk). Extract shared primitives to a neutral location.

### 5. Control Hierarchy Is Mandatory, Not Advisory
**Decision:** No signal can bypass any stage. Each stage returns PASS/REJECT. REJECT stops the pipeline.  
**Rationale:** The current system has optional gates (scalp confirmation, trigger gate). Making them mandatory stages eliminates bypass paths.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Phase 0 breaks existing scanner | Medium | High | Keep fsm_legacy.py, dual-run until tests pass |
| Phase 1 slows scanner beyond budget | Medium | High | Benchmark before/after, parallelize stages |
| Phase 2 CAS race condition in multi-worker | High | High | Phase 2B Redis CAS before enabling multi-worker |
| Phase 4 DB migration data loss | Low | Critical | Full backup before migration, rollback script |
| Phase 6 crypto integration destabilizes F&O | Medium | Medium | Separate strategy registry, isolated asset_class checks |
| Phase 9 secrets already in git history | High | High | git-filter-repo or BFG Repo-Cleaner, rotate all exposed keys |

---

## Success Metrics

| Metric | Baseline | Target |
|---|---|---|
| Signal expiry rate (pre-trigger) | ~30% | < 15% |
| Win rate (T1+T2 combined) | Current | +5pp |
| False positive rate (invalidated post-ARM) | Current | -50% |
| Scanner cycle p95 latency | ~2s | < 2.5s |
| FSM illegal transition rate | 0 | 0 (maintain) |
| PostgreSQL divergence incidents | Unknown | 0 |
| Feed degradation recovery time | Manual | < 30s automatic |
| State recovery completeness | ~70% | 100% |
| AI timeout rate | Unknown | < 5% |
| Paper P&L tracking accuracy | ~90% | 100% |

---

## Files Modified Summary

| File | Action | Phase |
|---|---|---|
| `app/signals/fsm.py` | Rename → `fsm_legacy.py` | 0 |
| `app/signals/fsm_unified.py` | Create | 0 |
| `app/signals/models.py` | Create | 0 |
| `app/signals/audit_unified.py` | Create | 0 |
| `app/signals/control_hierarchy.py` | Create | 1 |
| `app/signals/snapshot_buffer.py` | Create | 1 |
| `app/signals/execution_guard.py` | Create | 2 |
| `app/signals/state_recovery.py` | Create | 3 |
| `app/signals/reconciliation.py` | Create | 3 |
| `app/signals/decimal_safety.py` | Create | 3 |
| `app/signals/scoring_engine.py` | Create | 5 |
| `app/signals/signals_persistence.py` | Modify | 4 |
| `app/signals/worker.py` | Modify | 1, 2 |
| `app/signals/scanner.py` | Modify | 1 |
| `app/signals/confluence.py` | Deprecate → merge | 5 |
| `app/signals/signal_fusion.py` | Deprecate → merge | 5 |
| `app/signals/risk_engine.py` | Modify | 2 |
| `app/signals/paper_engine.py` | Modify | 3 |
| `app/signals/fill_reconciler.py` | Modify | 3 |
| `app/institutional/pipeline.py` | Deprecate (patterns extracted) | 1 |
| `app/institutional/signal.py` | Deprecate (patterns extracted) | 0 |
| `backend/config/scoring_weights.json` | Extend | 5 |
| `backend/config/risk_envelopes.json` | Extend | 2 |
| `backend/tests/test_*` | Add 8 new test files | 2-8 |
