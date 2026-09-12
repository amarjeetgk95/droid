# UI/UX Institutional-Grade Implementation Plan — v2.1

**Project:** Droid — AI-Powered Indian F&O Market Analysis Platform
**Scope:** `frontend/src/` plus required backend contracts under `backend/app/`
**Product mode:** Light theme only, permanently (non-goal: any dark mode)
**Target:** Institutional-trading-desk UX, not merely institutional visual styling
**Estimated delivery:** ~6–8 weeks for one experienced full-stack developer; ~4–5 weeks with parallel frontend/backend execution
**Companion contract:** `docs/EXECUTION_SAFETY.md` (execution action-state machine, correlation IDs, reconciliation read endpoint — shared with `SIGNAL_INSTITUTIONAL_PLAN.md`)

---

## Errata applied in v2.1 (vs. the v2.0 draft)

1. **Execution reconciliation contract specified** — v2.0's file plan contained
   an unspecified `backend/...execution...` row. It is now written down in
   `docs/EXECUTION_SAFETY.md` §3 (read endpoint, states, polling limits) and §4
   (idempotency). Week 2's release gate is unachievable without it.
2. **`useActionState` renamed** — the repo runs React 19, which ships a built-in
   hook of that name. The plan's hook is `useExecutionState`.
3. **Doc consolidation** — five planned docs reduced to two:
   `DESIGN_LANGUAGE.md` and `EXECUTION_SAFETY.md`. DATA_TRUTH and AI_PROVENANCE
   are sections of this plan, not documents.
4. **Table-virtualization risk added** — `@tanstack/react-virtual` expects divs;
   bolting it onto semantic `<tr>` rows breaks accessibility unless the
   padding-row/`role="row"` technique is used. Added to the risk register.
5. **Cut line made explicit** — see "P0 cut line" below.
6. **Concrete token values kept from v1** — Day 1 work names files and values.
7. **Next.js notes** — `useSearchParams` requires a Suspense boundary on
   prerendered routes (Phase 5); radix Dialog is already a dependency and
   provides focus trap/return-focus/Escape, so `useOverlayA11y` is only for
   non-Radix overlays (e.g. MarketHealthModal).

**Phase 1 implementation status (started):** `lib/feedState.ts` + tests,
`FreshnessClock.tsx`, `.feed-pill` styles, `--ds-ink-3` AA contrast fix, and
FreshnessClock wiring on Markets/Options/Signals desks are **landed**.

---

## P0 cut line

**P0 is the releasable product.** If schedule pressure arrives, P1/P2 items are
deferred without gate failure; P0 items are not. Anything that would make the
interface lie about data, state, or execution consequences is P0 by definition.

- **P0:** Phases 0, 1, 2, 6 (a11y/keyboard portions), 11 (gates), and the URL
  state half of Phase 5.
- **P1:** table virtualization, workspace persistence, AI provenance/uncertainty
  polish, caching, diagnostics, visual regression, motion contract.
- **P2:** print/export, AI follow-up prompts, secondary shortcuts.

---

## 1. Product Standard

Droid must feel like a professional research and trading workstation rather than
a conventional SaaS dashboard.

> **Dense where information matters, explicit where uncertainty exists, fast
> where attention matters, and impossible to misunderstand when state changes.**

The product optimizes for:

**Truth → State → Decision → Action → Confirmation → Audit**

Not: **Decoration → Animation → Dashboard polish.**

---

## 2. Non-Goals

* No dark theme. No `color-scheme` changes. No `prefers-color-scheme` handling.
* No duplicate light/dark token systems. (Dead `dark:` Tailwind variants are
  stripped in Phase 4.8.)
* No decorative gradients or glassmorphism. No unnecessary animation.
* No hidden primary-data failures.
* No horizontal scrolling as the only way to inspect critical P&L on mobile.
* No uncontrolled styling dialects.
* No fake AI certainty.
* No execution action that can silently succeed, silently fail, or become ambiguous.

---

## 3. Definition of Institutional-Grade (six layers)

1. **Data Truth** — every value answers: what, when observed, which feed, is the
   feed healthy, live/delayed/stale/degraded/fallback/unavailable.
2. **State Truth** — every operation answers: loading, succeeded, failed,
   pending, partial, retryable, what changed.
3. **Decision Safety** — explicit intent, explicit target, visible state,
   validation before execution, confirmation for destructive actions, visible
   acknowledgement.
4. **Auditability** — `who → what → when → against which state → result` is
   reconstructable.
5. **Interaction Quality** — full workflow via mouse, keyboard, screen reader,
   touch, narrow viewport.
6. **Reproducibility** — a shared URL or persisted workspace recreates the desk.

---

## Phase 0 — Baseline, Contracts & Guardrails (2–3 days, P0)

* **Axe smoke tests** per page (home, markets, options, signals, settings,
  login). CI fails on critical/serious; warnings allowed during migration.
* **ESLint design-language rules** (warn → error after Phase 4): inline
  semantic `background`/`color`/`border`/`borderRadius`, hex literals in TSX,
  raw feature `<table>`, one-off semantic colors and typography values.
* **Screenshot baselines** (light only): 1440×900, 768×1024, 390×844 across the
  five desks. For drift detection, not pixel enforcement.
* **Performance baseline:** record LCP/INP/CLS, bundle size, table render
  duration, chain scroll fps *before* setting budgets.
* **Interaction contract:** `docs/DESIGN_LANGUAGE.md` (visual + interaction +
  state language) and `docs/INTERACTION_CONTRACT.md` merged INTO it — one doc.

## Phase 1 — Truth-of-Data UX (4–5 days, P0) — **PARTIALLY LANDED**

* **`lib/feedState.ts` — DONE.** Single vocabulary: LIVE / SYNCING / STALE /
  DEGRADED / DOWN / CLOSED. `SYNC`/`OFF`/`OFFLINE`/dot variants retire as
  surfaces adopt it. Derivation precedence: CLOSED → DOWN → DEGRADED → STALE →
  SYNCING → LIVE. LIVE requires evidence (fresh stream ticks, or a fresh
  observation on a stream-less surface) — never optimism.
* **`FreshnessClock.tsx` — DONE.** Renders state + age ("LIVE · 3s ago"),
  auto-transitions to STALE, distinct DOWN, `PAUSED · tab hidden` when
  document.hidden stops polling, sr-only status text for screen readers.
  Wired into Markets, Options, and Signals desks.
* **Backend provenance contract (remaining):** F&O responses gain optional
  `data_quality: HEALTHY|DEGRADED|FALLBACK`, `as_of` (feed observation time,
  never server response time), `source`, `snapshot_id` where applicable.
  FreshnessClock already consumes `dataQuality`.
* **Surfaced primary-data failures (remaining):** replace silent catches /
  `return null` cards with "Snapshot as of HH:MM · feed unavailable · Retry".
  Silent catches remain legal only for background prefetch.
* **Hidden-tab semantics — DONE** (pill-level). Context-level `SYNCING` re-entry
  after visibility change rides on the same state.

## Phase 2 — Execution Safety & Auditability (4–5 days, P0)

Contract: `docs/EXECUTION_SAFETY.md`. Summary of frontend work:

* Action-state machine: `IDLE → VALIDATING → AWAITING_CONFIRMATION → EXECUTING
  → SUCCESS | FAILED | UNKNOWN` (+ PARTIAL, CANCELLED). UNKNOWN never
  auto-resolves to FAILED; it renders "Execution status unknown — reconcile
  before retrying" and resolves only via the backend read endpoint.
* `useExecutionState.ts` (NOT `useActionState` — React 19 collision) +
  `lib/executionState.ts` + `components/ui/ConfirmDialog.tsx` (radix Dialog) +
  `components/ui/toast.tsx` + correlation-id header plumbing in `lib/api.ts`.
* Confirmations: delete signal, sanitize ledger, execute paper trade, bulk
  destructive ops. Copy identifies the exact target, never "Are you sure?".
* Execution intent block (instrument, direction, qty, entry, stop/targets,
  confidence, snapshot time, feed state) shown before execution; feed state
  line makes degraded-feed execution a visible operator decision.
* Backend dependencies (tracked in EXECUTION_SAFETY.md §9): execution-status
  read endpoint + `Idempotency-Key` support.

## Phase 3 — Dense Tables & Desk Ergonomics (5–6 days, P0/P1)

* Signals ledger: dense table ≥ md; < md collapses to 3-line cards (symbol·
  side·state / entry·live·net / ttl·actions). No h-scroll for P&L.
* Virtualization with `@tanstack/react-virtual` above 50 rows only — with the
  semantic-table caveat from the risk register (padding-row technique or
  `role="row"`; a plain `<table>` stays under threshold).
* Stable live updates: never move the active row, destroy focus, reset scroll,
  or reorder unexpectedly. Flash only on real value changes.
* Pinning: Symbol/Side left, Net/Realized right; documented z-index ladder
  (thead 1, pinned 2, floating 40, overlays 60).
* Keyboard: ↑/↓ or j/k row movement, Enter dossier, x execute (through
  confirmation), Esc close; `aria-activedescendant` where appropriate.
* `TableState.tsx` replaces `sg-empty` / `sig-empty` / `EmptyNote` dialects;
  loading skeletons match final geometry (zero CLS).

## Phase 4 — One Design Language (6–8 days, P1)

* Tokens: `globals.css` is the semantic source; Tailwind for layout/spacing
  only, never semantic color/typography.
* Contrast (partially done): `--ds-ink-3` #9b9b9b → **#767676** landed
  (4.6:1 AA). Remaining: `--ds-disabled` #b8b8b8 → #9a9a9a (legibility), sweep
  any residual failing pairs. Disabled-state exemption is not a license for
  illegible informational labels.
* Radius: 0/2/4/6 only; remove `borderRadius: 10/12`, map Settings'
  rounded-lg/xl to the scale. Weights: 400/500/600/700 only.
* Numeric data: tabular numerals (`.num`/`.sg-num`), ₹ + en-IN.
* Button taxonomy: `.btn` · `.btn-primary` · `.btn-buy` · `.btn-sell` ·
  `.sg-primary` · `.sg-ibtn` (consolidate `.icon-btn` into `.sg-ibtn`).
* Settings migration onto the design system (the visual outlier today).
* Inline semantic styles → 0 in production code (ESLint flips to error).
* Light-only cleanup: strip `dark:` variants (MarketTicker, CommandPalette);
  map emerald/rose/amber Tailwind chips to `--ds-*-wash` tokens.

## Phase 5 — URL State, Workspace & Reproducibility (3–4 days, P0/P1)

* URL authoritative: home `instrument`+`timeframe`; options
  `symbol`+`expiry`+`viewMode`; signals `desk`+`underlying`+`tab`; settings
  `activeTab`. Priority: URL > localStorage > defaults.
* Retire `droid:select-instrument` CustomEvent; MarketTicker writes
  `?instrument=…`. Temporary event fallback during migration, then removed.
* `lib/workspace.ts` persists `droid:workspace:v1` (instrument, timeframe,
  expiry, signals tab, sidebar collapsed, ticker visible).
* Next.js note: `useSearchParams` needs a Suspense boundary on prerendered
  routes — wrap page content or read params in a client child.
* Shareability gate: a copied URL recreates the desk in a fresh browser.

## Phase 6 — Accessibility & Keyboard-Grade UX (3–4 days, P0)

* aria-label on every icon-only control (SignalsDesk landed; remaining:
  header toggles, drawer/dialog close buttons, any new icon buttons).
  `title` stays as tooltip only, never the a11y mechanism.
* Visible 2px accent focus ring on every interactive control; focus never
  lost to live refresh.
* Overlays: use radix Dialog (already a dependency) for ConfirmDialog and new
  modals; `useOverlayA11y` only for non-Radix overlays (MarketHealthModal,
  SignalDetailDrawer if not migrated): focus trap, Escape, return focus,
  scroll lock, labelled dialog semantics.
* Keyboard-only workflow gate: palette → desk → row → dossier → execute →
  confirm → acknowledge → close.

## Phase 7 — AI Institutional Surfaces (3–4 days, P1)

* Provenance: provider, model, latency_ms, timestamp, tools_called,
  market_snapshot_as_of, snapshot_id; forecast surfaces add
  forecast_version/calibration_version when the backend provides them.
* Input provenance (P1, backend dependency): distinguish model knowledge vs
  live data vs tools/retrieval vs user context — the UI must not imply the
  model observed information it did not receive.
* One confidence scale: High ≥ 70 · Moderate 45–69 · Low < 45 everywhere.
* Uncertainty as product states: ABSTAIN / INSUFFICIENT DATA / DEGRADED INPUT /
  LOW CONFIDENCE — rendered with the DEGRADED amber treatment, never as errors.
* Markdown via `marked` + `dompurify` (escape by default, CSP-safe).
* Copilot: suggested prompts, copy response, contextual follow-ups,
  per-symbol session persistence.

## Phase 8 — Motion & Feedback Discipline (2–3 days, P1)

* Budgets: hover ~80ms · state ~120ms · drawer/modal ~200ms · meter ~300ms.
  Properties: opacity, transform, background-color, border-color, meter width.
  No bounce/blur/decorative scale. `prefers-reduced-motion` respected (already
  global; verify new animations inherit it).
* Canonical price flash (ticker pattern) extended to option premiums and
  ledger P&L; flash only on actual value changes.

## Phase 9 — Resilience, Caching & Diagnostics (3–4 days, P1)

* `ErrorBoundary.tsx` per widget — one broken widget never unmounts the desk
  (DASHBOARD_REVIEW.md §1.3). Fallback: "Widget unavailable" + Retry.
* `deskCache` extended to markets + signals, stale-while-revalidate, documented
  TTLs and caps. Cache must never falsify freshness (freshness rides on the
  source timestamp, not the cache-hit time).
* Session banner: PRE_OPEN / OPEN / EVENT / CLOSED + notices ("FII data is
  snapshot-based as of 10:05"), dismissible per day.
* ⌘⇧D diagnostics overlay: per-endpoint last success/attempt, SSE state, poll
  intervals, latency, data quality. Operator-facing, not consumer clutter.

## Phase 10 — Daily Sheet / Export (1–2 days, P2)

* Print stylesheet: hide nav/filters/AI chips; keep forecast hero, positions,
  ledger, timestamps/provenance. `window.print()` only — no PDF stack unless
  product requirements justify it.

## Phase 11 — Verification & Release Gate (3–4 days, P0)

* **A11y gate:** zero critical/serious axe violations; keyboard-only pass;
  screen-reader pass on SignalsDesk; labelled icon controls; correct
  table/dialog semantics.
* **Data-truth gate:** LIVE/SYNCING/STALE/DEGRADED/DOWN/CLOSED exercised via
  feed outage, delayed feed, fallback, hidden tab, reconnect, stale cache.
* **Execution gate:** per EXECUTION_SAFETY.md §8 — no workflow can silently
  resolve success/failure; UNKNOWN path verified against the read endpoint.
* **Performance gate:** Lighthouse ≥ 90, INP < 200ms, near-zero CLS, 120-row
  chain at 60fps on reference hardware (measured).
* **Visual regression gate:** Playwright, three viewports, thresholds tuned on
  intentional changes.
* **Deep-link gate:** every URL state opens directly, restores state, survives
  refresh, shares cleanly, no CustomEvents.

## Phase 12 — Documentation & Handover (2 days, P1)

* `docs/DESIGN_LANGUAGE.md` — tokens, button/table/state taxonomy, interaction
  and motion contracts (absorbs the former INTERACTION_CONTRACT doc).
* `docs/EXECUTION_SAFETY.md` — already written; kept current with
  SIGNAL_INSTITUTIONAL_PLAN.md.

---

## Design Language Rules

**Colors** originate from `--ds-*` tokens; no one-off semantic hex in components.
**Radius** 0/2/4/6. **Weights** 400/500/600/700. **Numbers** tabular-nums, ₹ en-IN.
**Density** — information hierarchy over decorative whitespace; never reduce
text below readable size to gain density.

## State Language Contract

| State | Meaning |
|---|---|
| LIVE | Current feed healthy, data within staleness window |
| SYNCING | Refresh in progress / awaiting first fresh data |
| STALE | Last known value older than threshold |
| DEGRADED | Data exists but quality reduced (fallback source) |
| DOWN | Feed/service unavailable |
| CLOSED | Session intentionally inactive |

Avoid ambiguous `OFF`, `SYNC`, `OK`, `BAD`. Owner: `lib/feedState.ts`.

## Action Language Contract

Communicate: what am I acting on, what am I doing, what state is it in, what
happened. Prefer Retry / Refresh / Execute / Delete / Sanitize / Open dossier;
avoid Go / Do it / Proceed unless context is explicit.

## AI Language Contract

Prefer High/Moderate/Low confidence, Insufficient data, Abstained, Degraded
inputs, Snapshot-based. Never Guaranteed / Certain / Will happen / Safe trade.

## Architecture Decisions

1. **Light theme only** — one visual system; no token duplication.
2. **Truth-of-data before polish** — a beautiful stale number is worse than an
   ugly truthful one.
3. **One styling dialect** — tokens + shared primitives + Tailwind layout only.
4. **Primary failure always visible** — silent catches only for background
   prefetch.
5. **URL is shareable desk state** — authoritative over localStorage; runtime
   events are a migration mechanism only.
6. **Execution is a state machine** — intent → validation → confirmation →
   execution → acknowledgement → reconciliation → audit.
7. **Unknown is a real state** — a timeout never becomes FAILED while the
   server may have accepted; resolve only via the reconciliation endpoint.
8. **AI meets the same provenance standard as market data.**

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Execution timeout causes duplicate action | Medium | **Critical** | UNKNOWN state + correlation ID + Idempotency-Key + reconciliation endpoint (EXECUTION_SAFETY.md) |
| Virtualization breaks table semantics/UX | Medium | Medium | >50-row threshold; padding-row/`role="row"` technique for `<table>`; keyboard/hover tests |
| Backend returns stale-but-valid data | Medium | High | `as_of` + data_quality contract; freshness from source timestamp |
| AI appears more certain than inputs justify | Medium | High | Confidence/abstain/provenance surfaces |
| Cache falsifies freshness | Medium | High | Freshness clock keyed to source timestamp, not cache-hit time |
| Live refresh steals focus | Medium | High | Stable row identity; update reconciliation; freeze-on-hover |
| Design sweep touches ~40 files | High | Medium | Token pass first; ESLint warn → error |
| Screenshot diffs noisy | Medium | Low | Tune thresholds on intentional changes |
| Contrast bump changes brand feel | Low | Medium | Visual diff review before committing |
| Markdown rendering vulnerability | Low | High | DOMPurify + CSP |
| Deep-link migration breaks ticker flow | Medium | Medium | Temporary event fallback during migration |
| Mobile table unusable | Medium | Medium | Card-collapse strategy |
| Performance budget causes premature optimization | Low | Medium | Measure baseline before enforcing |

## Success Metrics

| Metric | Baseline | Target |
|---|---|---|
| Pages with zero critical/serious axe issues | 0 | 6/6 |
| Primary surfaces with freshness state | Partial | 100% |
| Feed-state vocabularies | 4+ | 1 (`lib/feedState.ts`) |
| Primary silent catches | 2+ | 0 |
| Inline semantic styles | Dozens | 0 |
| Destructive actions without confirmation | 2 | 0 |
| Actions with explicit state machine | Partial | 100% |
| Unknown-capable actions resolved blindly | Existing | 0 |
| URL-persisted desks | 0 | 100% |
| Icon-only buttons without labels | ~8 (SignalsDesk done) | 0 |
| Mobile P&L behind h-scroll | Yes | No |
| 120-row chain performance | Untested | 60fps measured |
| AI cards with provenance | Partial | 100% relevant |
| AI surfaces with explicit uncertainty | Partial | 100% applicable |

## Delivery Sequence

| Week | Ship | Release gate |
|---|---|---|
| 1 — Trust foundation | Baselines · feedState · FreshnessClock · backend `as_of`/data_quality · surfaced failures · hidden-tab semantics | No primary surface misrepresents freshness |
| 2 — Safety foundation | Action-state machine · confirmations · UNKNOWN + reconciliation · correlation IDs · audit events | No consequential action silently resolves |
| 3 — Tables & navigation | TableState · virtualization · row nav · pinning · mobile collapse · stable live updates | Keyboard + mobile workflow passes |
| 4 — Design-system enforcement | Token cleanup · settings migration · inline-style elimination · taxonomy · light-only cleanup | Lint rules warn → error |
| 5 — State & accessibility | URL state · workspace · overlay a11y · shortcuts · deep-link verification | Copied URL reproduces desk state |
| 6 — AI + resilience | AI provenance/uncertainty · sanitized markdown · ErrorBoundary · caching · diagnostics | AI meets data-provenance standard |
| 7 — Motion, export & verification | Motion contract · print · session banner · visual regression · perf tests | Gates in §Phase 11 pass |
| 8 — Hardening buffer | Regressions, cross-browser, perf, a11y, contract reconciliation — **not to be consumed for polish** | — |

## Core Principle

> **The interface must never know more than the system actually knows, must
> never imply more certainty than the evidence supports, and must never leave
> the operator guessing what just happened.**

That principle governs market data, AI output, execution, errors, timestamps,
tables, state, accessibility, and visual design. The goal is not to make Droid
*look* institutional — it is to make Droid *behave* like an institutional
workstation, and let the visual system make that behavior immediately legible.
