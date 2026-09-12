import { describe, it, expect } from 'vitest';
import {
  deriveFeedState,
  ageLabel,
  feedPillTone,
  feedStateDescription,
  FEED_STATES,
  DEFAULT_STALE_AFTER_MS,
  type FeedState,
} from './feedState';

const NOW = 1_800_000_000_000; // fixed reference clock

describe('deriveFeedState', () => {
  it('returns CLOSED when the market session is closed regardless of other signals', () => {
    expect(deriveFeedState({ marketClosed: true, streamState: 'DISCONNECTED', now: NOW })).toBe('CLOSED');
    expect(deriveFeedState({ marketClosed: true, streamState: 'CONNECTED', ticksFresh: true, now: NOW })).toBe('CLOSED');
  });

  it('returns DOWN when the stream is disconnected/errored', () => {
    expect(deriveFeedState({ streamState: 'DISCONNECTED', now: NOW })).toBe('DOWN');
    expect(deriveFeedState({ streamState: 'ERROR', now: NOW })).toBe('DOWN');
    expect(deriveFeedState({ streamState: 'FAILED', now: NOW })).toBe('DOWN');
  });

  it('returns DEGRADED when the backend declares reduced data quality', () => {
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: true, dataQuality: 'DEGRADED', now: NOW })).toBe('DEGRADED');
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: true, dataQuality: 'FALLBACK', now: NOW })).toBe('DEGRADED');
  });

  it('does not treat HEALTHY quality as degraded', () => {
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: true, dataQuality: 'HEALTHY', now: NOW })).toBe('LIVE');
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: true, dataQuality: null, now: NOW })).toBe('LIVE');
  });

  it('returns STALE once the last observation exceeds the staleness window', () => {
    // Stream-less surface: freshness rides entirely on the last observation.
    const justWithin = deriveFeedState({
      streamState: null,
      lastAt: NOW - (DEFAULT_STALE_AFTER_MS - 1000),
      now: NOW,
    });
    expect(justWithin).toBe('LIVE');

    const beyond = deriveFeedState({
      streamState: null,
      lastAt: NOW - (DEFAULT_STALE_AFTER_MS + 1000),
      now: NOW,
    });
    expect(beyond).toBe('STALE');

    // STALE wins over SYNCING: an old observation is still more informative.
    const connectedButOld = deriveFeedState({
      streamState: 'CONNECTED',
      ticksFresh: false,
      lastAt: NOW - (DEFAULT_STALE_AFTER_MS + 1000),
      now: NOW,
    });
    expect(connectedButOld).toBe('STALE');
  });

  it('returns SYNCING when connected but no fresh ticks have arrived', () => {
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: false, lastAt: null, now: NOW })).toBe('SYNCING');
  });

  it('returns SYNCING when a first fetch is in flight with no prior observation', () => {
    expect(deriveFeedState({ fetching: true, lastAt: null, now: NOW })).toBe('SYNCING');
  });

  it('returns LIVE for fresh stream ticks', () => {
    expect(deriveFeedState({ streamState: 'CONNECTED', ticksFresh: true, now: NOW })).toBe('LIVE');
  });

  it('returns LIVE for a recent REST observation even without a stream', () => {
    expect(deriveFeedState({ streamState: null, lastAt: NOW - 4000, now: NOW })).toBe('LIVE');
  });

  it('defaults to SYNCING when nothing is known yet (cold start)', () => {
    expect(deriveFeedState({ now: NOW })).toBe('SYNCING');
  });

  it('accepts Date/string/number lastAt forms', () => {
    const recent = NOW - 2000;
    expect(deriveFeedState({ lastAt: new Date(recent), now: NOW })).toBe('LIVE');
    expect(deriveFeedState({ lastAt: new Date(recent).toISOString(), now: NOW })).toBe('LIVE');
    expect(deriveFeedState({ lastAt: recent, now: NOW })).toBe('LIVE');
  });

  it('ignores invalid lastAt values', () => {
    expect(deriveFeedState({ lastAt: 'not-a-date', now: NOW })).toBe('SYNCING');
    expect(deriveFeedState({ lastAt: '', now: NOW })).toBe('SYNCING');
  });
});

describe('ageLabel', () => {
  it('formats seconds, minutes, and hours', () => {
    expect(ageLabel(NOW - 3_000, NOW)).toBe('3s ago');
    expect(ageLabel(NOW - 90_000, NOW)).toBe('1m ago');
    expect(ageLabel(NOW - 150_000, NOW)).toBe('2m ago');
    expect(ageLabel(NOW - 2 * 60 * 60_000, NOW)).toBe('2h ago');
  });

  it('returns null for missing or invalid input', () => {
    expect(ageLabel(null, NOW)).toBeNull();
    expect(ageLabel(undefined, NOW)).toBeNull();
    expect(ageLabel('', NOW)).toBeNull();
    expect(ageLabel('garbage', NOW)).toBeNull();
  });

  it('never produces a negative age', () => {
    expect(ageLabel(NOW + 60_000, NOW)).toBe('0s ago');
  });
});

describe('presentation helpers', () => {
  it('assigns a distinct tone per state', () => {
    const tones: Record<FeedState, string> = {
      LIVE: feedPillTone('LIVE'),
      SYNCING: feedPillTone('SYNCING'),
      STALE: feedPillTone('STALE'),
      DEGRADED: feedPillTone('DEGRADED'),
      DOWN: feedPillTone('DOWN'),
      CLOSED: feedPillTone('CLOSED'),
    };
    expect(tones.LIVE).toBe('on');
    expect(tones.DOWN).not.toBe(tones.LIVE);
    expect(tones.STALE).toBe(tones.SYNCING); // both "waiting" tones
    expect(tones.CLOSED).toBe('idle');
  });

  it('covers every state in the vocabulary', () => {
    expect(FEED_STATES).toHaveLength(6);
    for (const s of FEED_STATES) {
      expect(typeof feedStateDescription(s)).toBe('string');
      expect(feedStateDescription(s).length).toBeGreaterThan(0);
    }
  });
});
