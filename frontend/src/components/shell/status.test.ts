import { describe, expect, it } from 'vitest';
import { SESSION_PHASE_LABELS, STREAM_STATE_LABELS, streamFeedState } from './status';

const CONNECTED = {
  connected: true,
  lastEventAt: 1_000,
  reconnects: 0,
  source: 'sse' as const,
};

const DISCONNECTED = {
  connected: false,
  lastEventAt: null,
  reconnects: 0,
  source: 'fetch' as const,
};

describe('streamFeedState', () => {
  it('never reports DOWN before the visual clock mounts', () => {
    expect(streamFeedState(CONNECTED, 0)).toBe('SYNCING');
    expect(streamFeedState(DISCONNECTED, 0)).toBe('SYNCING');
  });

  it('reports SYNCING while a connection is still being established', () => {
    expect(streamFeedState(DISCONNECTED, 1_000)).toBe('SYNCING');
  });

  it('reports DOWN once a connection attempt has failed', () => {
    expect(streamFeedState({ ...DISCONNECTED, reconnects: 1 }, 1_000)).toBe('DOWN');
  });

  it('reports LIVE for a connected stream with fresh frames', () => {
    expect(streamFeedState(CONNECTED, 5_000)).toBe('LIVE');
  });

  it('reports STALE once the last frame ages past the window', () => {
    expect(streamFeedState({ ...CONNECTED, lastEventAt: 1_000 }, 60_000)).toBe('STALE');
  });
});

describe('status vocabulary', () => {
  it('labels every session phase', () => {
    expect(SESSION_PHASE_LABELS).toEqual({
      PRE_OPEN: 'PRE-OPEN',
      OPEN: 'OPEN',
      POST_CLOSE: 'POST-CLOSE',
      CLOSED: 'CLOSED',
    });
  });

  it('labels every feed state', () => {
    expect(STREAM_STATE_LABELS).toEqual({
      LIVE: 'STREAM LIVE',
      SYNCING: 'STREAM SYNC',
      STALE: 'STREAM STALE',
      DEGRADED: 'STREAM DEGRADED',
      DOWN: 'STREAM DOWN',
      CLOSED: 'STREAM IDLE',
    });
  });
});
