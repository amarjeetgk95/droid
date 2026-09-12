# Execution Safety Contract

**Status:** Plan of record (pending implementation)
**Consumed by:** `docs/UI_INSTITUTIONAL_PLAN.md` (Phase 2, frontend) and `SIGNAL_INSTITUTIONAL_PLAN.md` (Phase 2/3, backend: execution guard, CAS, reconciliation)
**Principle:** No consequential action can silently succeed, silently fail, or become ambiguous without a reconciliation path.

---

## 1. Action state machine (frontend-owned)

Every consequential action (execute paper trade, delete signal, sanitize ledger) moves through:

```
IDLE → VALIDATING → AWAITING_CONFIRMATION → EXECUTING → SUCCESS
                                                     → FAILED
                                                     → UNKNOWN
optional: PARTIAL, CANCELLED
```

Rules:

- `UNKNOWN` is a first-class terminal-pending state. If the client loses the
  response (timeout, network drop, tab close), the UI must render
  **"Execution status unknown — reconcile before retrying"** and must NOT map
  the timeout to `FAILED`.
- Buttons are disabled from `EXECUTING` until a terminal state resolves
  (double-submit prevention). The existing per-signal `executingId` guard in
  `SignalsDesk` satisfies the UI half; idempotency at the API is still required
  (§4).
- Optimistic UI is allowed only for reversible state (e.g. removing a row from
  a filter view), never for execution acknowledgement.

Frontend owner: `frontend/src/lib/executionState.ts` + `useExecutionState.ts`
(named to avoid collision with React 19's built-in `useActionState`).

---

## 2. Correlation ID (frontend → API)

Every consequential request carries:

```
X-Correlation-Id: EXEC-YYYYMMDD-HHMMSS-<4 hex>
```

- Generated client-side at intent creation, never reused across attempts.
- Sent on the execution/delete/sanitize request; echoed back in the response
  body as `correlation_id` and in all audit events.
- A retry after `UNKNOWN` sends a **new** correlation id with
  `retry_of: <previous correlation id>` so the backend can link attempts
  without treating them as duplicates.

---

## 3. Execution-status read endpoint (backend-owned)

The piece the frontend cannot implement unilaterally. The backend exposes:

```
GET /api/signals/execution-status/{signal_id}
```

Response:

```json
{
  "signal_id": "…",
  "execution_intent_id": "…",
  "correlation_id": "EXEC-20260912-104213-8F21 | null",
  "status": "RECONCILED | EXECUTION_PENDING | BROKER_TIMEOUT | AMBIGUOUS | RECONCILIATION_REQUIRED | REJECTED | NOT_FOUND",
  "observed_at": "2026-09-12T10:42:20+05:30",
  "detail": "human-readable explanation or null"
}
```

Semantics:

- `NOT_FOUND` — no execution intent was ever created for this signal. Safe to
  re-execute from scratch. The UI may clear the UNKNOWN state on this answer.
- `EXECUTION_PENDING` — intent created, broker answer not yet final. UI keeps
  the pending state and may re-poll (≤ 1 req / 2s, max 30s, then escalate).
- `AMBIGUOUS` / `RECONCILIATION_REQUIRED` — partial fill, qty mismatch, or
  broker timeout. UI must block re-execution and surface the dossier with the
  backend `detail`. Only the sanitize/reconcile flow (operator action) clears it.
- `RECONCILED` / `REJECTED` — terminal; UI maps them to SUCCESS / FAILED with
  the `detail` as the error message.

This endpoint is the frontend's only permitted way to resolve `UNKNOWN`.
Mapping a timeout to FAILED without querying it is a contract violation.

Backend side this maps onto the existing `SIGNAL_INSTITUTIONAL_PLAN.md`
Phase 3.2 reconciliation states (RECONCILED / BROKER_TIMEOUT / API_ERROR /
AMBIGUOUS / RECONCILIATION_REQUIRED) — the read endpoint is a projection of
that reconciler's state, not a new subsystem.

---

## 4. Idempotency (backend-owned)

The execute endpoint accepts an `Idempotency-Key` header (the correlation id
from §2). Replays of the same key within the signal's TTL return the original
result instead of creating a second order. This is the belt to the §1
suspenders: even a client that ignores the UNKNOWN rule cannot double-execute.

---

## 5. Confirmation contract (frontend-owned)

Required confirmation for: delete signal, sanitize audit ledger, execute paper
trade, bulk destructive operations, any future live-trading action.

Confirmation copy must identify the exact target:

> Delete NIFTY 15m LONG signal? This removes it from the active desk.

Never generic "Are you sure?". The confirm dialog shows the same intent block
as §6 before `AWAITING_CONFIRMATION → EXECUTING`.

---

## 6. Execution intent block (display contract)

Before execution the UI renders, and the confirm dialog restates:

```
Instrument       NIFTY
Direction        LONG · 15m
Mode             Paper trade
Entry            25,120.00
Stop / Targets   25,020.00 · 25,320 / 25,520
Confidence       78
Market snapshot  10:42:13 IST
Feed state       LIVE (from lib/feedState.ts — never execute against STALE/DOWN without an explicit override)
```

The feed-state line is deliberate: executing against a degraded feed is a
decision the operator must see, not a silent default.

---

## 7. Audit events

Consequential actions emit (frontend → backend; backend persists via the
existing `audit_unified` record):

```ts
type AuditEvent = {
  eventType: 'EXECUTE_INTENT' | 'EXECUTE_CONFIRM' | 'EXECUTE_RESULT'
           | 'SIGNAL_DELETE' | 'LEDGER_SANITIZE';
  timestamp: string;          // ISO 8601, IST
  actor: string | null;       // user id when auth provides one
  signalId?: string;
  instrument?: string;
  correlationId: string;
  stateBefore?: unknown;
  stateAfter?: unknown;
  result?: 'SUCCESS' | 'FAILED' | 'UNKNOWN';
};
```

`who → what → when → against which state → result` must be reconstructable
from these events plus the FSM audit trail.

---

## 8. Verification gates (both plans)

Frontend (`frontend/src/tests/execution-state.test.tsx`):

- normal success · validation failure · backend rejection · duplicate click
  (disabled during EXECUTING) · timeout → UNKNOWN · retry-after-UNKNOWN queries
  §3 first · confirmation cancel · UNKNOWN → RECONCILED/AMBIGUOUS/NOT_FOUND
  rendering.

Backend (extends `test_signal_hardening.py`):

- idempotency-key replay returns original result
- reconciliation states project correctly onto the read endpoint
- correlation ids flow into audit records

---

## 9. Open items

- [ ] Backend: implement §3 endpoint + §4 idempotency (belongs to
      SIGNAL_INSTITUTIONAL_PLAN Phase 2/3 work; frontend ships against a stub
      that always returns NOT_FOUND, which is safe but disables the UNKNOWN
      resolution path).
- [ ] Frontend: `executionState.ts`, `useExecutionState.ts`, `ConfirmDialog.tsx`,
      correlation-id header in `lib/api.ts` (UI plan Phase 2).
- [ ] Both: agree on auth identity source for `actor` once Supabase auth is
      wired into execution endpoints.
