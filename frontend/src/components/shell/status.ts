import type { MarketSessionPhase } from '@/context/MarketSessionContext';
import type { AppStreamStatus } from '@/context/AppStreamContext';
import { deriveFeedState, type FeedState } from '@/lib/feedState';

/** Terminal vocabulary for the market session phase. */
export const SESSION_PHASE_LABELS: Record<MarketSessionPhase, string> = {
  PRE_OPEN: 'PRE-OPEN',
  OPEN: 'OPEN',
  POST_CLOSE: 'POST-CLOSE',
  CLOSED: 'CLOSED',
};

/** Terminal vocabulary for the unified app-stream feed state. */
export const STREAM_STATE_LABELS: Record<FeedState, string> = {
  LIVE: 'STREAM LIVE',
  SYNCING: 'STREAM SYNC',
  STALE: 'STREAM STALE',
  DEGRADED: 'STREAM DEGRADED',
  DOWN: 'STREAM DOWN',
  CLOSED: 'STREAM IDLE',
};

/**
 * One honest feed state for the app stream.
 *
 *   - `now <= 0`: the visual clock has not mounted yet (SSR / first paint).
 *   - `!connected && reconnects === 0`: the stream has never connected and has
 *     not recorded a failed attempt — still resolving, not down.
 *
 * Both report SYNCING so the rail never flashes red before evidence of a
 * failure exists; DOWN is reserved for a stream that actually dropped.
 */
export function streamFeedState(status: AppStreamStatus, now: number): FeedState {
  if (now <= 0) return 'SYNCING';
  if (!status.connected && status.reconnects === 0) return 'SYNCING';
  return deriveFeedState({
    streamState: status.connected ? 'CONNECTED' : 'DISCONNECTED',
    ticksFresh: status.connected,
    lastAt: status.lastEventAt,
    now,
  });
}
