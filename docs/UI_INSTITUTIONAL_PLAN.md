# UI/UX Institutional-Grade Implementation Plan

**Project:** Droid — AI-Powered Indian F&O Market Analysis Platform
**Scope:** `frontend/src/` (all pages, components, design system)
**Explicit non-goal:** No dark theme. No `color-scheme` changes. The product stays light-only, permanently.
**Goal:** Raise the existing Kite-inspired light system to institutional-trading-desk standard — truth-of-data surfaces, dense deterministic tables, one enforced design language, keyboard-grade ergonomics, audit-friendly interactions.

---

## Executive Summary

The frontend already has institutional bones: a flat token system (`globals.css`), tabular numerals everywhere, honest v2 badges on the forecast card, zero-CLS ticker skeletons, a command palette, and dirty-tracking settings. What keeps it below institutional standard is unevenness — freshness is communicated on one page but not others, three styling dialects coexist, page state isn't deep-linkable, destructive actions are unconfirmed, and several grays fail WCAG AA at the 9–10px sizes the design uses.

This plan fixes the unevenness in 7 phases (~4.5 weeks), ordered by trust-impact per hour of work. New dependencies are limited to `@tanstack/react-virtual` (Phase 2) and `marked` + `dompurify` (Phase 3/6). Phases 1–3 change what the user sees daily; Phases 4–7 are the polish that separates "looks institutional" from "is institutional."

---

## Phase 0 — Baseline & Guardrails (2 days)

### Objective
Make the institutional bar enforceable by CI, so regressions don't silently erode the standard later.

### Tasks

**0.1 Axe smoke test on every page**
```
- Add vitest + axe-core smoke tests: mount each page (forecast home, markets,
  options, signals, settings, login) and assert zero critical/serious violations.
- Start permissive; tighten to zero violations at end of Phase 4.
```

**0.2 ESLint rules for design-language drift**
```
- Flag inline `style={{ background|color|borderRadius|border : ... }}` in
  components/app TSX (a class or token must exist instead). Add as `warn` now;
  flip to `error` after the Phase 3 sweep.
- Flag hex color literals (`#rgb`, `#rrggbb`) in TSX — must use var(--ds-*) tokens.
- Flag raw `<table>` in feature components without the shared `tbl`/`sg-table` class.
```

**0.3 Screenshot baselines (light only)**
```
- Playwright screenshot script for: home, markets, options, signals desk, settings.
- Viewports: 1440×900, 768×1024, 390×844. Light theme only — no dark baselines ever.
- Baselines serve as visual diff for Phases 1–6 refactors.
```

**0.4 A11y target declared**
```
- Definition of done for Phases 3–4: all text ≥ 4.5:1 contrast; all icon-only
  controls labeled; full keyboard operability on all desks.
```

### Verification
```bash
cd frontend && npx vitest run
```

---

## Phase 1 — Truth-of-Data UX (Week 1, ~4 days)

### Objective
Every number on screen must carry its own provenance: age, feed, and quality. This is the single biggest institutional tell — real terminals surface staleness more prominently than freshness.

### Tasks

**1.1 Create `components/common/FreshnessClock.tsx` — reusable freshness surface**
```
Props: lastAt: Date | null, state: 'LIVE' | 'SYNCING' | 'STALE' | 'DOWN', pollLabel.
Renders: "LIVE · 3s ago" pill using existing .sg-live styles.
- Age ticks every 1s; no update for > 30s → auto-morph to STALE (warn tone).
- DOWN reuses .down-dot semantics from the home page feed logic.
- Adopted by: ForecastCard, MarketsPage, OptionsPage, SignalsDesk, ticker status chip.
```

**1.2 Thread `lastAt` through each page's fetch state**
```
- MarketsPage / OptionsPage / SignalsDesk already know when a fetch last
  succeeded — store it. ForecastCard already has updatedAt.
- Expose lastSuccessfulFetchAt from MarketDataContext / LiveMarketContext.
```

**1.3 Backend: propagate `data_quality` on F&O endpoints**
```
- Extend response models with optional data_quality: HEALTHY|DEGRADED|FALLBACK
  and as_of (feed timestamp, not server time) on dashboard/regime/chain/ledger.
- Frontend renders DEGRADED with the amber treatment ForecastCard already uses.
```

**1.4 Silent failure → surfaced failure**
```
- BreadthFlowsStrip's silent catch becomes "snapshot as-of · feed unavailable"
  inline text (not a red banner). Same for cards that `return null` on error.
- Rule: silent catch allowed only for background prefetch, never primary data.
```

**1.5 Unify the feed-state vocabulary**
```
- One enum everywhere: LIVE / SYNCING / STALE / DOWN / CLOSED. Today there are
  four variants (live-dot/stale-dot/down-dot, LIVE/SYNC/OFF, LIVE/OFFLINE, …).
- `lib/feedState.ts` is the single owner; all variants map through it.
```

**1.6 Tab-visibility pause badge**
```
- Polls already pause when document.hidden. FreshnessClock shows "auto-refresh
  paused while tab hidden" so the resumed clock doesn't jump 0s → 4m silently.
```

### Verification
```bash
cd frontend && npm run build && npx vitest run
```

---

## Phase 2 — Dense Tables & Layout Rigor (Week 1–2, ~5 days)

### Objective
Institutional desks are judged on their tables. Ours are good but break on mobile and are raw at 11 columns.

### Tasks

**2.1 Signals ledger responsive strategy**
```
- ≥ md: keep the 11-column dense table with sticky headers (already good).
- < md: collapse each row to a 3-line card (symbol·side·state / entry·live·net /
  ttl·actions). Do NOT hide columns behind horizontal scroll — an institutional
  tool must not require horizontal scrolling to see P&L.
```

**2.2 Virtualize the option chain and ledger**
```
- OptionChainTable and the signals ledger render 100+ rows; virtualize with
  @tanstack/react-virtual. Add `.row-virtual { contain: layout paint; }`.
- Verify a 120-row chain scrolls at 60fps; add a perf test with React Profiler.
- Only virtualize above 50 rows — keep the plain table for small lists.
```

**2.3 Column-pinning contract**
```
- Pin Symbol and Side left; Net/Realized right-pinned on the ledger.
- position: sticky; left: 0 with a documented z-index ladder (thead=1, pinned=2, overlay=60).
```

**2.4 Keyboard row navigation**
```
- j/k or ↑/↓ moves the active row; Enter opens the dossier; x executes (with confirm).
- aria-activedescendant on the table container; visible ring via :focus-visible token.
```

**2.5 Table freeze during live updates**
```
- Live P&L updates must not shift focus/scroll while the user interacts with a row.
- Pause visual updates on row hover; resume on mouse-leave.
- Price changes flash ± washes (reuse the MarketTicker flash pattern).
```

**2.6 Empty/error states per table**
```
- One `TableState` component replaces the three dialects (sg-empty, sig-empty, EmptyNote):
  loading (skel rows matching final layout — zero CLS), empty (icon+copy+CTA),
  error (message+RetryButton).
```

### Verification
```bash
cd frontend && npx vitest run && npm run build
# Manual: 120-row chain scrolls at 60fps on a mid-tier laptop.
```

---

## Phase 3 — Design-Language Enforcement Sweep (Week 2–3, ~6 days)

### Phase 3.1 — Token fixes (Day 1)

**3.1.1 Contrast to WCAG AA**
```
- --ds-ink-3: #9b9b9b → #767676 (2.8:1 → 4.6:1 on white) — used for every 9–10px
  uppercase label in the system.
- --ds-disabled: #b8b8b8 → #9a9a9a (legibility; disabled-state exemption noted).
- Screenshot diff review before committing — should be imperceptible except faint labels.
```

**3.1.2 Radius + weight scale reconciliation**
```
- Remove inline borderRadius: 10/12 (AICopilotChat bubbles, ForecastCard details).
- Map to --radius-md (4px) / --radius-lg (6px). Settings page rounded-lg/xl remap to the 2–6px scale.
- ForecastCard fontWeight 750 → 600/700 (scale is 400/500/600/700).
```

**3.1.3 Numeric typography contract**
```
- Every displayed number uses .num / .sg-num (tabular). Sweep stragglers.
- Currency always ₹ + en-IN locale (already consistent) — enforced by ESLint rule 0.2.
```

### Phase 3.2 — Component sweep (Days 2–6)

**3.2.1 Settings page migration**
```
- Migrate to design-system classes: .card/.card-hd/.card-bd, .tabbar/.tab, .sg-live.
- Settings becomes the 6th desk in the same language (today it is the visual outlier:
  8–12px radii, tailwind grays, different density).
```

**3.2.2 Inline-style elimination**
```
- AICopilotChat: bubbles → classes, input → .input class.
- ForecastCard: targets row → Stat/Card primitives; verdict row → classes.
- Flip ESLint rule 0.2 from warn → error at the end of this phase.
```

**3.2.3 Empty-state and button taxonomy**
```
- One empty-state component (TableState from 2.6); retire sg-empty / sig-empty variants.
- Button taxonomy doc: .btn (default) · .btn-primary (primary CTA) · .btn-buy/.btn-sell
  (directional) · .sg-primary (desk CTA) · .sg-ibtn (icon-only). Consolidate .icon-btn → .sg-ibtn.
```

**3.2.4 Dead dark-mode variants removed**
```
- Product is light-only: strip all `dark:` Tailwind variants (MarketTicker, CommandPalette).
- Palette color chips (emerald-50/rose-50/amber-50 …) map to wash tokens
  (--ds-bull-wash / --ds-bear-wash / --ds-warn-wash) — one source of semantic color truth.
```

**3.2.5 Deep-linking + workspace state**
```
- Sync to search params via useSearchParams + router.replace:
  instrument + timeframe (home), symbol + expiry + viewMode (options),
  desk + underlying + tab (signals), activeTab (settings).
- Kills the droid:select-instrument window CustomEvent (MarketTicker writes
  ?instrument=…; home reads the param). Keep the event as fallback during migration,
  remove it in the same phase.
```

**3.2.6 Accessibility fixes**
```
- aria-label on every icon-only button (execute, delete, dossier, sanitize, refresh,
  header toggles). Keep title as visual tooltip.
- Verify sg-seg/sg-tools label association programmatically (axe covers this).
- Focus ring contrast check (2px --ds-accent on white passes).
```

**3.2.7 Keyboard shortcuts sheet**
```
- "?" opens a sheet listing: ⌘K palette · ⌘B sidebar · ⌘1–9 desks · ⌘, settings ·
  ⌘S save · j/k row nav · Esc close overlays. Rendered in the palette's visual language.
```

**3.2.8 Toasts + destructive-action confirmation**
```
- Tiny toast host (no dependency, ~60 lines): .sg-live styling, 4s auto-dismiss,
  aria-live=polite. Success/error/info tones.
- Delete signal → ConfirmDialog ("Delete NIFTY 15m LONG signal? Removes it from the desk.")
- Sanitize audit ledger → ConfirmDialog (it rewrites the ledger).
- Execute paper trade → optimistic row state + toast on success/error.
```

**3.2.9 AI Copilot upgrade**
```
- Markdown rendering for assistant messages (marked + dompurify, escape by default).
- Suggested-prompt chips on empty state ("Is this breakout real?", "PCR + OI walls?",
  "What invalidated yesterday's forecast?").
- Copy-message button; conversation persists per symbol in sessionStorage.
```

**3.2.10 ErrorBoundary per widget**
```
- Per-card ErrorBoundary so one broken widget never unmounts the page
  (DASHBOARD_REVIEW.md §1.3). Fallback: card chrome + "Widget unavailable" + RetryButton.
```

### Verification
```bash
cd frontend && npx vitest run && npm run build && npm run lint
# Axe smoke tests now tightened to zero critical/serious.
```

---

## Phase 4 — Motion & Feedback Discipline (Week 3, ~2 days)

### Objective
Institutional motion = feedback, not decoration: ≤ 120ms for state, opacity/transform only, reduced-motion respect (already global).

### Tasks

**4.1 Motion contract**
```
- Durations: 80ms hover · 120ms state change · 200ms drawer/dialog · 300ms meter width.
- Properties: opacity, transform, background-color, border-color, width (meters only).
- No scale/bounce/blur. Verify all new animations inherit prefers-reduced-motion.
```

**4.2 Price-flash consistency**
```
- MarketTicker flash (bull/bear wash, 850ms) is canonical. Extend to option chain
  premiums and ledger P&L cells. Flash only on real value changes, never refetch-same.
```

**4.3 Loading feedback**
```
- Busy state on all action buttons (Refresh already does; extend to Execute/Sanitize/Create).
- Skeleton → data with zero layout shift (CLS contract from 2.6).
```

**4.4 Focus management in overlays**
```
- useOverlayA11y hook extracted from CommandPalette's pattern: focus trap,
  Escape-to-close, return-focus-to-trigger, body scroll lock.
- Apply to SignalDetailDrawer, SignalCreateDialog, MarketHealthModal
  (DASHBOARD_REVIEW.md §3.4 lists these gaps today).
```

### Verification
```bash
cd frontend && npx vitest run
# Manual: keyboard-only walkthrough — palette → desk → row nav → execute → dossier → close.
```

---

## Phase 5 — Operational Polish (Week 3, ~2 days)

### Objective
Small features that read as institutional: workspace persistence, print export, session awareness, self-diagnostics.

### Tasks

**5.1 Workspace persistence**
```
- Persist workspace (instrument, timeframe, expiry, signals tab, sidebar collapsed,
  ticker visible) to localStorage under droid:workspace:v1; restore on load.
- Precedence: URL params > localStorage > defaults (shareable links authoritative).
```

**5.2 Print/PDF export of the daily sheet**
```
- @media print stylesheet: hide sidebar/ticker/filters/AI chips; show forecast hero,
  positions, ledger. Header button "Export daily sheet (PDF)" → window.print().
- Institutional users print/forward the desk view daily.
```

**5.3 Session/event banner**
```
- Global banner for market session (PRE_OPEN/CLOSED/EVENT) and critical notices
  ("FII data is snapshot-based as of 10:05", "AI engine on local fallback").
- Sits below ticker; dismissible per day via localStorage.
```

**5.4 Operator diagnostics overlay**
```
- ⌘⇧D overlay: last fetch time per endpoint, SSE state, poll intervals, backend latency.
- Data already exists in MarketDataContext/health — surface it. The tool tells you about itself.
```

**5.5 Client caching (stale-while-revalidate)**
```
- Extend deskCache (already used by options) to markets + signals with per-desk TTLs,
  50-entry cap. Swaps cold-load skeletons for instant paint + background refresh.
```

### Verification
```bash
cd frontend && npm run build && npx vitest run
```

---

## Phase 6 — Institutional-Grade AI Surfaces (Week 4, ~2 days)

### Objective
AI is the product's differentiator; its surfaces must look as rigorous as the quant surfaces.

### Tasks

**6.1 Provenance lines on AI cards**
```
- Every AI card header shows provider:model, latency_ms, tools-called flag, timestamp.
  Same treatment as ForecastCard's model/calibrator line (already good).
```

**6.2 Confidence language standard**
```
- One scale everywhere: High ≥ 70 · Moderate 45–70 · Low < 45 (matches ForecastCard).
- Signals confidence bars and AI cards adopt the same thresholds + tone classes.
```

**6.3 Uncertainty as first-class UI**
```
- AIDeepInsightCard renders uncertainty/abstain with the DEGRADED treatment
  (amber border + badge) — never fake certainty. Mirrors ForecastCard abstain.
```

**6.4 Structured markdown + copy**
```
- marked + dompurify for AI long-form in AIDeepInsightCard and AIAnalysisCard.
- Copy button on all AI cards, not just copilot messages.
```

**6.5 Follow-up prompts**
```
- After each copilot answer, 2 contextual follow-ups ("What changed since this?",
  "Size this position", "Show invalidation logic").
```

### Verification
```bash
cd frontend && npx vitest run
# Manual: markdown renders, copy works, abstain/uncertain states show amber treatment.
```

---

## Phase 7 — Verification & Handover (Week 4, ~2 days)

### Tasks

**7.1 Full a11y audit**
```
- Axe on every page: zero critical/serious. Keyboard-only walkthrough of every desk.
- Screen-reader pass on SignalsDesk semantics (th scope, caption, aria-live updates).
```

**7.2 Perf budgets**
```
- Lighthouse ≥ 90 perf per desk, zero CLS on ticker + tables, INP < 200ms on row actions.
- Virtualized 120-row chain at 60fps — measured, not assumed.
```

**7.3 Visual regression suite**
```
- Playwright screenshots (light only) across 1440×900 / 768×1024 / 390×844.
- PRs shifting pixels > threshold fail CI — institutional consistency becomes machine-enforced.
```

**7.4 Documentation**
```
- docs/DESIGN_LANGUAGE.md: tokens, button taxonomy, table contract, motion contract,
  feed-state vocabulary, a11y rules. This doc remains the plan of record.
```

---

## Implementation Timeline

| Phase | Duration | Dependencies | Risk |
|---|---|---|---|
| Phase 0: Baseline & guardrails | 2 days | None | Low |
| Phase 1: Truth-of-data UX | 4 days | Phase 0 | Low |
| Phase 2: Dense tables | 5 days | Phase 0 | Medium — virtualization regressions |
| Phase 3: Design-language sweep | 6 days | Phase 0 (0.2) | Medium — sweep breadth (~40 files) |
| Phase 4: Motion & feedback | 2 days | Phases 2–3 | Low |
| Phase 5: Operational polish | 2 days | Phase 3.2.5 | Low |
| Phase 6: AI surfaces | 2 days | Phase 3 | Low |
| Phase 7: Verification | 2 days | All | Low |
| **Total** | **~25 working days ≈ 5 weeks** | | |

---

## Key Architectural Decisions

### 1. Light theme only, forever
**Decision:** No dark theme, no color-scheme toggle, no prefers-color-scheme handling.
**Rationale:** Explicit product decision. Dark mode would double the token surface for zero institutional value. All `dark:` Tailwind variants are dead code and are stripped in Phase 3.2.4.

### 2. Truth-of-data over polish
**Decision:** Freshness/provenance indicators ship before visual polish phases.
**Rationale:** For a trading tool, a beautifully-styled stale price is worse than an ugly live one. Institutional = the desk tells you when it doesn't know.

### 3. One styling dialect, enforced by CI
**Decision:** globals.css design-system classes + desk.tsx primitives for semantic styling; Tailwind for layout/spacing only; inline styles eliminated.
**Rationale:** Three dialects coexist today (CSS classes, Tailwind components, inline styles) and have already drifted (radii, grays, empty states). ESLint rule 0.2 keeps it fixed.

### 4. Degrade gracefully, never silently
**Decision:** Silent catches allowed only for background prefetch; primary data surfaces always show state.
**Rationale:** Silent failure is the #1 trust-killer on a trading desk. ForecastCard already demonstrates the pattern — extend it.

### 5. Dense but responsive
**Decision:** Dense tables on desktop; card-collapse on mobile; horizontal scroll never required to see P&L.
**Rationale:** Institutional ≠ desktop-only. The ledger's 11 columns must survive a phone.

### 6. URL is the desk's state
**Decision:** Page state lives in search params; localStorage is a convenience cache; window CustomEvents retire.
**Rationale:** Shareable desk views ("BANKNIFTY 15m chain, greeks view") are table-stakes for team workflows, and event-bus coupling between ticker and page is fragile.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Screenshot diffs are noisy | Medium | Low | Start with 3 key pages; tune threshold before expanding |
| Virtualization regresses chain UX (hover, keyboard nav) | Medium | Medium | Virtualize only above 50 rows; keep plain table fallback |
| Design sweep touches ~40 files | High | Medium | Split: token fixes (1 day) then component sweep; ESLint warns before erroring |
| Contrast bump changes brand feel | Low | Medium | Screenshot diff review before committing the token change |
| marked renders AI output unsafely | Low | High | Pair with dompurify; escape by default; CSP-safe |
| Deep-linking breaks ticker→home flow | Medium | Medium | Keep event fallback during migration; remove in same phase |
| Print stylesheet maintenance burden | Low | Low | Scope to forecast hero + ledger only |

---

## Success Metrics

| Metric | Baseline | Target |
|---|---|---|
| Pages passing axe with 0 critical/serious | 0 | All 6 |
| Text contrast failures | --ds-ink-3 at 2.8:1 | All text ≥ 4.5:1 |
| Feed-state vocabulary variants | 4 | 1 (lib/feedState.ts) |
| Inline style objects in components | dozens | 0 (ESLint-enforced) |
| Destructive actions without confirm | 2 | 0 |
| Pages with URL-persisted state | 0 | All 6 |
| Ledger at 390px | horizontal scroll | card-collapse, no h-scroll |
| Option chain 120-row scroll | untested | 60fps measured |
| Silent catches on primary data | 2 | 0 |
| Icon-only buttons without aria-label | ~8 | 0 |

---

## Files Modified Summary

| File | Action | Phase |
|---|---|---|
| `frontend/src/components/common/FreshnessClock.tsx` | Create | 1 |
| `frontend/src/lib/feedState.ts` | Create | 1 |
| `frontend/src/lib/workspace.ts` | Create | 3.2.5, 5.1 |
| `frontend/src/components/ui/TableState.tsx` | Create | 2.6 |
| `frontend/src/components/ui/toast.tsx` | Create | 3.2.8 |
| `frontend/src/components/ui/ConfirmDialog.tsx` | Create (radix dialog already a dependency) | 3.2.8 |
| `frontend/src/components/ui/ErrorBoundary.tsx` | Create | 3.2.10 |
| `frontend/src/components/layout/Header/ShortcutsSheet.tsx` | Create | 3.2.7 |
| `frontend/src/hooks/useOverlayA11y.ts` | Create | 4.4 |
| `frontend/src/components/options/OptionChainTable.tsx` | Virtualize | 2.2 |
| `frontend/src/components/signals/SignalsDesk.tsx` | Row nav, mobile collapse, confirms, toasts | 2.1, 2.4, 3.2.8 |
| `frontend/src/components/research/ForecastCard.tsx` | Primitives migration | 3.2.2 |
| `frontend/src/components/ai/AICopilotChat.tsx` | Markdown, chips, persistence, copy | 3.2.9, 6 |
| `frontend/src/app/(app)/settings/page.tsx` | Design-language migration | 3.2.1 |
| `frontend/src/app/(app)/page.tsx` | URL state | 3.2.5 |
| `frontend/src/app/(app)/markets/page.tsx` | lastAt, surfaced errors, URL state | 1.2, 1.4, 3.2.5 |
| `frontend/src/app/(app)/options/page.tsx` | lastAt, URL state | 1.2, 3.2.5 |
| `frontend/src/app/globals.css` | Token fixes, print styles, motion contract, row-virtual | 3.1, 4, 5.2 |
| `frontend/src/context/MarketDataContext.tsx` | lastSuccessfulFetchAt exposure | 1.2 |
| `frontend/src/context/LiveMarketContext.tsx` | lastSuccessfulFetchAt exposure | 1.2 |
| `frontend/src/components/layout/MarketTicker.tsx` | feedState mapping, URL write, dark-variant strip | 1.5, 3.2.4, 3.2.5 |
| `frontend/eslint.config.mjs` | Design-language rules | 0.2 |
| `backend/app/api/*.py` | data_quality + as_of fields | 1.3 |
| `frontend/src/tests/a11y-smoke.test.tsx` | Create | 0.1 |
| `docs/DESIGN_LANGUAGE.md` | Create | 7.4 |

---

*Companion doc to `SIGNAL_INSTITUTIONAL_PLAN.md` (backend hardening). Phases 1–3 are user-visible daily; Phases 4–7 are the polish that separates "looks institutional" from "is institutional."*
