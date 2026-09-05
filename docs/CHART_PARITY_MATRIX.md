# TradingChart Capability Parity Matrix (Phase 0 Audit)

> **Document Status**: Phase 0 Baseline  
> **Evaluation**: Custom Canvas Engine (`frontend/src/components/TradingChart/ChartCanvas.jsx`) vs. `lightweight-charts` (v5.2.1 installed).

---

## 1. Capability Parity Breakdown

| Capability Category | Feature Requirement | Current Custom Canvas (`ChartCanvas.jsx`) | `lightweight-charts` (v5.2.1) | Parity Status | Notes |
|---|---|---|---|---|---|
| **Core Rendering** | Candlestick series (OHLC) | ✅ Yes (Manual 2D Canvas) | ✅ Yes (Hardware accelerated) | **Parity: Exceeded** | `lightweight-charts` has built-in pixel ratio & sub-pixel alignment |
| | Line / Area series | ✅ Yes | ✅ Yes | **Parity: Exceeded** | |
| | HiDPI / Retina Canvas support | ⚠️ Partial (devicePixelRatio manual) | ✅ Full automated HiDPI | **Parity: Exceeded** | |
| **Viewport & Navigation** | Time Scale (X-axis) | ⚠️ Buggy (fractional bar bug in DASHBOARD_REVIEW #2.5) | ✅ Professional auto-formatting time axis | **Parity: Exceeded** | Native IST timezone support |
| | Price Scale (Y-axis) | ⚠️ Basic manual scaling | ✅ Auto-scaling, percentage, logarithmic | **Parity: Exceeded** | Native margin, formatters |
| | Mouse Drag Pan | ✅ Yes | ✅ Yes | **Parity: Full** | Smooth inertia pan |
| | Mouse Wheel Zoom | ⚠️ Buggy (unbounded zoom causing NaN bars) | ✅ Clamp-safe zoom | **Parity: Exceeded** | |
| | Keyboard Pan/Zoom (`r`, `+`, `-`, Arrows) | ⚠️ Fires while user types in text inputs (DASHBOARD_REVIEW #2.4) | ✅ API methods (`timeScale().fitContent()`, `zoom()`) | **Parity: Full** | Better input isolation via standard wrapper |
| **Real-Time Data Streaming** | Live tick bar update (`c`, `h`, `l`, `v`) | ⚠️ Staleness bug overwriting new bars with old (DASHBOARD_REVIEW #2.3) | ✅ Native `series.update(candle)` | **Parity: Exceeded** | Atomic bar merge guaranteed by TradingView engine |
| | Multi-Timeframe switching (1m, 5m, 15m, 1h, 1D) | ✅ Yes | ✅ Yes | **Parity: Full** | |
| **Theming & Aesthetics** | Dual-Theme (Light `#F8FAFC` & Dark `#0C0D10`) | ❌ Hardcoded white `#ffffff` and `#131722` | ✅ Full dynamic theme API (`applyOptions({ layout: { ... } })`) | **Parity: Exceeded** | Seamlessly synchronizes with CSS tokens |
| | Crosshairs & Tooltips | ✅ Custom `Legend.jsx` & crosshair line | ✅ Built-in crosshair + custom overlay hooks | **Parity: Full** | Tooltip events exposed via `subscribeCrosshairMove` |
| **Advanced Tools (Nice-to-Have)** | Indian Exchange Labels (`NSE · Index`) | ✅ Yes (in `TopBar.jsx`) | ✅ Retained in component TopBar shell | **Parity: Full** | Shell components (`TopBar`, `Legend`) wrap the chart canvas |
| | Drawing Tools (Trendline, rays) | ⚠️ Minimal (SideTools has stub buttons only) | ⚠️ Plugin-based or custom overlay | **Parity: Equivalent** | Existing canvas has non-functional stubs |

---

## 2. Recommendation & Migration Verdict

* **Verdict**: **PASSED (Parity Exceeded)**
* **Rationale**:
  1. `lightweight-charts` is already installed in `package.json` (`v5.2.1`).
  2. The custom canvas implementation is ~30KB of JavaScript with 3 documented high-severity bugs (stale candle corruption, typing keyboard conflicts, negative viewport pan).
  3. `lightweight-charts` natively supports instant Light/Dark theme switching, eliminating 100% of the hardcoded `#ffffff` / `#131722` color issues.
* **Migration Plan**:
  - Keep `TopBar.jsx`, symbol selector, and `Legend.jsx` layout wrapper.
  - Swap internal `ChartCanvas.jsx` with a modern TypeScript `<LightweightChartCanvas />` component.
