/**
 * Single feed-state vocabulary (UI_INSTITUTIONAL_PLAN v2.1, Phase 1.2).
 *
 * Every market-data surface maps its health through this module — no more
 * ad-hoc LIVE/SYNC/OFF/OFFLINE/LIVE-dot variants scattered across pages.
 * Pure functions only: trivially unit-testable, no React imports.
 */

export type FeedState =
  | 'LIVE' // current feed healthy, data observed within staleness window
  | 'SYNCING' // refresh in progress / stream connecting, awaiting first data
  | 'STALE' // last known value older than the staleness threshold
  | 'DEGRADED' // data exists but quality reduced (fallback / synthetic source)
  | 'DOWN' // feed/service unavailable and no last-known value shown as live
  | 'CLOSED'; // market/session intentionally inactive

export const FEED_STATES: readonly FeedState[] = ['LIVE', 'SYNCING', 'STALE', 'DEGRADED', 'DOWN', 'CLOSED'];

/** Default age after which a last-known value is considered stale. */
export const DEFAULT_STALE_AFTER_MS = 30_000;

/** A pill is "aged out" when we cannot honestly claim freshness at all. */
export const UNAVAILABLE_AGE_MS = 5 * 60_000;

export type FeedStateInput = {
  /** True when the market session is closed / non-trading day. */
  marketClosed?: boolean;
  /** WebSocket/SSE stream connection state, when the surface has one. */
  streamState?: string | null;
  /** True when real data ticks (not just heartbeats) arrived recently. */
  ticksFresh?: boolean;
  /** True when a refresh request is currently in flight. */
  fetching?: boolean;
  /** Time of the last successful fetch / tick / SSE event. */
  lastAt?: Date | string | number | null;
  /** Backend-declared data quality, when the contract provides it. */
  dataQuality?: 'HEALTHY' | 'DEGRADED' | 'FALLBACK' | string | null;
  /** Reference clock, injectable for tests. */
  now?: number;
};

/**
 * Derive one honest FeedState from raw signals.
 *
 * Precedence (first match wins):
 *   1. CLOSED      — session closed (intentional, not a failure)
 *   2. DOWN        — stream exists but is disconnected/errored
 *   3. DEGRADED    — backend declared DEGRADED/FALLBACK quality
 *   4. STALE       — last observation older than the staleness window
 *   5. SYNCING     — stream up but no fresh ticks yet, or a fetch in flight
 *   6. LIVE        — fresh stream ticks (or fresh REST observation)
 */
export function deriveFeedState(input: FeedStateInput): FeedState {
  const {
    marketClosed = false,
    streamState = null,
    ticksFresh = false,
    fetching = false,
    lastAt = null,
    dataQuality = null,
    now = Date.now(),
  } = input;

  if (marketClosed) return 'CLOSED';

  const disconnected =
    streamState === 'DISCONNECTED' ||
    streamState === 'ERROR' ||
    streamState === 'FAILED' ||
    streamState === 'CLOSED';
  if (disconnected) return 'DOWN';

  if (dataQuality === 'DEGRADED' || dataQuality === 'FALLBACK') return 'DEGRADED';

  const lastMs = toMs(lastAt);
  if (lastMs !== null && now - lastMs > DEFAULT_STALE_AFTER_MS) return 'STALE';

  const connected = streamState === 'CONNECTED' || streamState === 'SSE_CONNECTED';
  // A connected stream awaiting its first fresh ticks is SYNCING — even when a
  // recent REST observation exists, because the stream itself has not yet proven
  // liveness. This keeps LIVE reserved for evidence, never optimism.
  if (connected && !ticksFresh) return 'SYNCING';
  if (fetching && lastMs === null) return 'SYNCING';

  if (connected && ticksFresh) return 'LIVE';
  // No stream (or a stream-less surface): a recent observation is honest LIVE.
  if (lastMs !== null) return 'LIVE';

  return 'SYNCING';
}

/**
 * Age label for a last-observation timestamp, e.g. "3s ago", "2m ago".
 * Returns null when there is no observation yet (render "updating…").
 */
export function ageLabel(lastAt: Date | string | number | null | undefined, now = Date.now()): string | null {
  const ms = toMs(lastAt);
  if (ms === null) return null;
  const seconds = Math.max(0, Math.round((now - ms) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}

/** Pill tone class for each state (defined in globals.css). */
export function feedPillTone(state: FeedState): 'on' | 'warn' | 'down' | 'degraded' | 'idle' {
  switch (state) {
    case 'LIVE':
      return 'on';
    case 'STALE':
    case 'SYNCING':
      return 'warn';
    case 'DOWN':
      return 'down';
    case 'DEGRADED':
      return 'degraded';
    case 'CLOSED':
      return 'idle';
  }
}

/** Honest one-line description for tooltips and aria-labels. */
export function feedStateDescription(state: FeedState): string {
  switch (state) {
    case 'LIVE':
      return 'Feed live — data current within the staleness window.';
    case 'SYNCING':
      return 'Waiting for fresh data from the feed.';
    case 'STALE':
      return 'Showing last known value — feed has not updated recently.';
    case 'DEGRADED':
      return 'Data present but quality is reduced (fallback source).';
    case 'DOWN':
      return 'Feed unavailable — values shown are last known.';
    case 'CLOSED':
      return 'Market session closed — no live updates expected.';
  }
}

function toMs(v: Date | string | number | null | undefined): number | null {
  if (v === null || v === undefined || v === '') return null;
  const ms = v instanceof Date ? v.getTime() : new Date(v).getTime();
  return Number.isFinite(ms) ? ms : null;
}
