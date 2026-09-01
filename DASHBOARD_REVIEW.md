# Dashboard Robustness Review

Scope: `frontend/src/app/(app)/page.tsx`, `frontend/src/components/dashboard/*`, `frontend/src/context/MarketDataContext.tsx`, `frontend/src/hooks/useMarketData.ts`, `frontend/src/hooks/useMarketStream.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/TradingChart/useRealCandleData.js`, `frontend/src/components/dashboard/DashboardTradingChart.jsx`, `backend/app/api/dashboard.py`.

Legend: 🔴 Critical (wrong data / crash) · 🟠 High (reliability) · 🟡 Medium (UX/perf) · ⚪ Low (hygiene)

---

## 1. Critical issues

### 1.1 🔴 Backend serves fabricated market data on failure (`backend/app/api/dashboard.py`)
When the quote lookup fails, the endpoint silently substitutes **hardcoded fake values** and returns them as if real:

```python
except Exception:
    quote = None
    current_price = 24750      # fabricated price!
    atr = 38                   # fabricated ATR!
```

Similarly, the "quantitative" block always returns synthetic probabilities:
```python
p10, p50, p90 = current_price * 0.99, current_price, current_price * 1.01
prob_up, prob_down = 0.52, 0.48
```
For a trading dashboard this is dangerous: a user can see `24750` as the NIFTY price with a plausible-looking P10/P50/P90 band and never know the feed died.

**Suggestion**
- Return `current_price: null` plus a top-level `data_quality: "DEGRADED"` / `stale: true` flag instead of fake numbers; render an explicit "data unavailable" state in the UI.
- Keep fallbacks only for display-neutral fields, never for prices/probabilities.
- Never swallow `except Exception:` silently — at minimum `logger.exception(...)` and include the failure reason in the response (`"errors": {"quote": "..."}`).

### 1.2 🔴 All-or-nothing dashboard loading (`page.tsx` + `MarketDataContext`)
`Promise.all` over 4 endpoints means one failing endpoint (e.g. breadth 500s) blanks the **entire** dashboard behind a single error screen, even though cards/health succeeded:

```tsx
const [cardsRes, breadthRes, healthRes, statusRes] = await Promise.all([...]);
```

**Suggestion**
- Use `Promise.allSettled` and keep per-section state + per-section error banners, so a partial backend failure degrades gracefully instead of taking the whole page down.
- Add a "Retry" button to the error screen (there is currently no way to recover except waiting for the next poll).

### 1.3 🔴 Unchecked numeric fields crash cards (`MarketCard.tsx`, `MarketBreadth.tsx`)
```tsx
{card.ltp.toFixed(2)}                                  // crashes if ltp is null/undefined
{data.advance_decline_ratio.toFixed(2)}                // crashes if null
{data.sentiment.replace('_', ' ')}                     // crashes if undefined
{new Date(marketStatus.market_time).toLocaleTimeString(...)} // renders "Invalid Date"
```
One malformed tick or partial API payload can take the whole React tree down (no error boundary per card).

**Suggestion**
- Add a `safeNum(n, fallback='—')` / `safeStr()` helper in `lib/utils.ts` and use it for every displayed numeric/string.
- Wrap each dashboard card in a small `<ErrorBoundary>` so one broken widget doesn't unmount the page.
- Guard `Sparkline` against `NaN`/Infinity and non-finite min/max (`range = max - min || 1` doesn't cover `NaN`).

### 1.4 🔴 Stale live-tick merge forces `status: 'LIVE'` forever (`MarketDataContext.tsx:101-123`)
Whenever a tick exists for a symbol, the card is forced to `status: 'LIVE'`. But `latestTicks` keeps the **last ever** tick — if the stream dies at 15:35, the card claims LIVE all evening/next day.

**Suggestion**
- Store `receivedAt` with each tick and treat ticks older than N seconds (e.g. 30s) as stale → fall back to the REST-provided status.
- Only override status when `streamState === 'CONNECTED'` and the tick is fresh.
- Also fix `volume: tick.volume || card.volume` — a legitimate `0` volume silently falls back to old data.

---

## 2. High issues

### 2.1 🟠 No fetch timeout / overlap guard (`api.ts`)
`fetch()` has no `AbortSignal.timeout()`. If the Render backend hangs, every 15s poll starts a new request while old ones are still pending — requests stack up unboundedly and connections leak.

**Suggestion**
```ts
response = await fetch(url, { ...options, headers, signal: AbortSignal.timeout(10_000) });
```
- Add a single-flight guard in the polling hooks: skip `run()` if the previous fetch is still in-flight (`inFlightRef`).
- Add limited retry with exponential backoff + jitter for transient 5xx/network errors.

### 2.2 🟠 WebSocket has no liveness detection (`useMarketStream.ts`)
- No heartbeat/idle timeout: a half-open TCP connection (sleep/resume, proxy timeout) leaves `streamState === 'CONNECTED'` forever while no ticks arrive.
- Reconnects run indefinitely even when the tab is hidden — battery/quota drain on a free-tier backend.
- `NodeJS.Timeout` type used in browser code; `reconnectCount` grows unbounded with no reset on successful reconnect.

**Suggestion**
- Track `lastTickAt`; if no message for e.g. 30s, force `ws.close()` and reconnect.
- Pause reconnects when `document.hidden` (resume on visible).
- Cap backoff (already 30s ✓) and reset `backoffRef`/counter after a stable connection period; use `ReturnType<typeof setTimeout>`.


### 2.3 🟠 Candle live-poll corrupts data and refetches everything (`useRealCandleData.js`)
- The 2s poll downloads the **full candle history** every tick (comment says "refetch last candle" — it doesn't). Use `?limit=2` or a last-bar endpoint.
- Corruption bug: when `lastNew <= lastPrev` (e.g. market closed), the merge overwrites the newest local bar's `c/h/l/v` with the values of an **older** candle:
```js
const latest = mapped[mapped.length - 1];   // may be older than prev's last!
next[next.length - 1] = last;               // stale data overwrites new bar
```
  Guard with `if (latest.t >= last.t)` before merging.
- Initial fetch effect and live-poll effect both call `getCandles` on mount/symbol change → duplicate requests. Let the poll own updates after the first load, or share one AbortController.

### 2.4 🟠 Global keyboard shortcuts fire while typing (`DashboardTradingChart.jsx`)
`window.addEventListener('keydown', ...)` responds to `r`, `+`, `-`, arrow keys even when the user is typing in a search/settings input elsewhere on the page.

**Suggestion**
```js
const onKey = (ev) => {
  const t = ev.target;
  if ((t instanceof HTMLElement && /INPUT|TEXTAREA|SELECT/.test(t.tagName)) || t?.isContentEditable) return;
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  ...
};
```

### 2.5 🟠 Viewport math bugs (`DashboardTradingChart.jsx`)
- `ArrowLeft` sets `start: v.start - 3` with **no clamp** → negative start passed to the canvas.
- Zoom buttons produce **fractional bar counts** (`v.count * 0.8`); nothing rounds → off-by-one rendering drift.
- `changePct` compares against `data[len-25]` regardless of timeframe — on `1D` that's a 25-day "change" shown next to the price.

**Suggestion** — centralize one `clampView(v, dataLen)` used by every mutation (`Math.round` counts, `0 <= start <= dataLen - count`), and compute change vs. previous close (already available on index cards) or per-timeframe session open.

### 2.6 🟠 Symbol handling in the backend is fragile (`dashboard.py:28`)
```python
sym = symbol.upper().replace(" 50", "")
```
This mangles any symbol containing `" 50"` and does no validation. A wrong symbol then falls through to the fake `24750` price.

**Suggestion** — use an explicit mapping table (`NIFTY 50 → NIFTY`) and return 404/422 for unknown symbols instead of fabricating data; validate with a Pydantic response model so the shape is guaranteed.


---

## 3. Medium issues

### 3.1 🟡 Erroring cards silently disappear
`MLPredictionCard` / `FIIPositioningCard` `return null` on error — the layout just collapses and the user can't tell "failed" from "not configured". Render a compact error/retry card instead.

### 3.2 🟡 Duplicated data-fetching logic
`useMarketData.ts` and `MarketDataContext.tsx` are near-identical copies (the comment even admits it). Two implementations *will* drift — one already differs in `fetchData` (no `isMounted` guard in the context's callback version). Delete the hook copy or make it a thin wrapper over the context.

### 3.3 🟡 Polling intervals need jitter + hidden-tab backoff
Fixed 15s/30s/60s/2s/3s intervals from every client sync up (thundering herd on the free Render instance). Add ±20% jitter, and skip the 2s candle poll when `document.hidden`.

### 3.4 🟡 `MarketHealthModal`
- Telemetry polls every 3s even while requests fail (no backoff).
- No Escape-to-close, no focus trap, no click-outside close, no body scroll lock — accessibility and UX gaps.
- `health?.provider || 'Fyers'` displays a **fake provider name** when health is null — show `'—'`.

### 3.5 🟡 No response models / caching on the backend dashboard endpoint
Every call re-runs regime classification + chart analysis + portfolio summary. Add short TTL caching (e.g. 2–5s) per symbol, and define a Pydantic response model so contract drift is caught at the boundary rather than by `.toFixed()` crashes in React.

### 3.6 🟡 Dead/inconsistent code
- `useMarketData.fetchData` is exported as `refetch` but the effect re-implements the same logic — keep one implementation.
- `TF_LABEL_TO_VALUE` lacks `4h` while `VALUE_TO_LABEL` has it (`240: '4h'`) — timeframe round-trip is asymmetric.
- `FIIPositioningCard` division `(ratio / (ratio + 1))` yields `NaN` width if `fii_long_short_ratio` is null — guard it.

---

## 4. Low / hygiene

- Mixed JS/TSX in `TradingChart/*` used by the dashboard — migrate to TS for type safety on the hottest data path.
- `API_BASE` hardcodes a production Render URL as default; a missing env var silently points local dev at prod. Fail loudly (or use `localhost:8000`) in dev.
- `api.ts` sets a Bearer token but there's no global 401 handling (no token refresh/redirect to login) — polls will loop on 401 forever.
- `_meta()` in `dashboard.py` always reports `status=OFFLINE` regardless of real feed state — misleading metadata.
- Add per-widget `<ErrorBoundary>`s to the dashboard grid; only a global `error.tsx` exists today.

---

## 5. Prioritized action plan

| # | Action | Files | Effort |
|---|--------|-------|--------|
| 1 | Remove fabricated fallbacks (24750/38/0.52), return null + degraded flag | `backend/app/api/dashboard.py` | S |
| 2 | `Promise.allSettled` + per-panel errors + Retry button | `MarketDataContext.tsx`, `page.tsx` | M |
| 3 | Null-safe display helpers + per-card ErrorBoundary | `MarketCard`, `MarketBreadth`, `QuickStats`, `MarketOverview`, `lib/utils.ts` | M |
| 4 | Fetch timeout + single-flight polling guard | `api.ts`, `MarketDataContext.tsx` | S |
| 5 | WS heartbeat/idle reconnect + hidden-tab pause | `useMarketStream.ts` | M |
| 6 | Fix candle merge staleness bug + poll only last bar | `useRealCandleData.js` | S |
| 7 | Tick freshness check before forcing `LIVE` | `MarketDataContext.tsx` | S |
| 8 | Clamp/round viewport, ignore keys while typing | `DashboardTradingChart.jsx` | S |
| 9 | Symbol validation map + Pydantic response model + short cache | `dashboard.py` | M |
| 10 | Delete duplicated hook logic; error cards instead of `null` | `useMarketData.ts`, `MLPredictionCard`, `FIIPositioningCard` | S |
