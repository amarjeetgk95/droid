/**
 * Chart colour source.
 *
 * Canvas-based chart libraries (Lightweight Charts, custom SVG payoff/IV
 * diagrams) cannot resolve `var(--ds-*)`, so they need literal colour strings.
 * Hardcoding a second palette is how the old "Kite-inspired" constants drifted
 * away from the design system, so instead we read the real tokens off `:root`
 * once and cache them.
 *
 * Single source of truth: `frontend/src/app/globals.css`.
 * Change a colour there and every chart follows.
 */

export type ChartTokens = {
  /** Bullish candle body / wick, take-profit, positive deltas. */
  up: string;
  /** Bearish candle body / wick, stop-loss, negative deltas. */
  down: string;
  /** Brand blue — spot price line, selection. */
  accent: string;
  /** Amber — VWAP, entry fill, caution. */
  warn: string;
  /** Faint grid lines on the canvas. */
  grid: string;
  /** Crosshair guides. */
  crosshair: string;
  /** Time / price scale borders. */
  axis: string;
  /** Axis tick labels and other faint chart text. */
  text: string;
  /** Chart background. */
  surface: string;
};

/**
 * Used during SSR and as a per-token fallback if a token is missing or empty.
 * Values mirror `:root` in globals.css — keep them in sync (design gate:
 * scripts/check-design-rules.mjs).
 */
const FALLBACK: ChartTokens = {
  up: '#4caf50',       // --ds-bull
  down: '#df5148',     // --ds-bear
  accent: '#387ed1',   // --ds-accent
  warn: '#ff9500',     // --ds-warn
  grid: 'rgba(68, 68, 68, 0.06)',      // --ds-chart-grid
  crosshair: 'rgba(68, 68, 68, 0.35)', // --ds-chart-crosshair
  axis: 'rgba(68, 68, 68, 0.12)',      // --ds-chart-axis
  text: '#9b9b9b',     // --ds-ink-3
  surface: '#ffffff',  // --ds-surface
};

const TOKEN_MAP: Record<keyof ChartTokens, string> = {
  up: '--ds-bull',
  down: '--ds-bear',
  accent: '--ds-accent',
  warn: '--ds-warn',
  grid: '--ds-chart-grid',
  crosshair: '--ds-chart-crosshair',
  axis: '--ds-chart-axis',
  text: '--ds-ink-3',
  surface: '--ds-surface',
};

let cached: ChartTokens | null = null;

/**
 * Resolved chart colours. Safe to call during SSR (returns `FALLBACK`) and in
 * the browser (reads `:root`, then caches).
 */
export function chartTokens(): ChartTokens {
  if (cached) return cached;
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return FALLBACK;
  }

  const resolved = { ...FALLBACK };
  try {
    const computed = getComputedStyle(document.documentElement);
    for (const key of Object.keys(TOKEN_MAP) as (keyof ChartTokens)[]) {
      const value = computed.getPropertyValue(TOKEN_MAP[key]).trim();
      if (value) resolved[key] = value;
    }
  } catch {
    // jsdom/happy-dom or a locked-down environment — use the CSS-mirrored
    // fallback and leave the cache empty so a later call can retry.
    return FALLBACK;
  }

  cached = resolved;
  return resolved;
}

/**
 * Escape hatch for tests and for re-reading after a runtime token change.
 * The theme is currently light-only and fixed, so nothing calls this in the app.
 */
export function resetChartTokens(): void {
  cached = null;
}
