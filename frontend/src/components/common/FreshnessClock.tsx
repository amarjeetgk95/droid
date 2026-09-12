'use client';

/**
 * FreshnessClock — reusable truth-of-data pill (UI_INSTITUTIONAL_PLAN v2.1, Phase 1.1).
 *
 * Renders feed state + age, e.g. "LIVE · 3s ago" / "STALE · 47s ago".
 * Derives state via lib/feedState.ts when `state` is not passed explicitly,
 * so a surface can hand it raw signals (lastAt, streamState, ticksFresh…)
 * and still get the single honest vocabulary.
 *
 * Never displays LIVE unless the evidence supports it: stale transitions are
 * automatic, DOWN is visually distinct from STALE, and a paused tab renders
 * the hidden-tab notice so a resumed clock never jumps 0s → 4m silently.
 */

import { useEffect, useMemo, useState } from 'react';
import {
  deriveFeedState,
  ageLabel,
  feedPillTone,
  feedStateDescription,
  type FeedState,
  type FeedStateInput,
} from '@/lib/feedState';

const TICK_MS = 1000;

export type FreshnessClockProps = {
  /** Explicit state override (skip derivation). */
  state?: FeedState;
  /** Signals for derivation when `state` is not provided. */
  lastAt?: Date | string | number | null;
  streamState?: string | null;
  ticksFresh?: boolean;
  fetching?: boolean;
  marketClosed?: boolean;
  dataQuality?: 'HEALTHY' | 'DEGRADED' | 'FALLBACK' | string | null;
  /** Where the data comes from, e.g. "SSE", "REST · 15s poll". */
  sourceLabel?: string;
  /** Extra trailing text, e.g. "snapshot 10:05". */
  note?: string;
  className?: string;
};

export function FreshnessClock({
  state,
  lastAt,
  streamState,
  ticksFresh,
  fetching,
  marketClosed,
  dataQuality,
  sourceLabel,
  note,
  className,
}: FreshnessClockProps) {
  const [now, setNow] = useState<number>(() => Date.now());

  // Re-render once per second while visible so the age label stays truthful.
  // When the tab is hidden we STOP ticking: the pill must not silently claim
  // fresh ages that were computed before the user looked away.
  useEffect(() => {
    if (typeof document !== 'undefined' && document.hidden) return;
    const id = setInterval(() => setNow(Date.now()), TICK_MS);
    const onVisible = () => {
      if (!document.hidden) {
        setNow(Date.now());
        const id = setInterval(() => setNow(Date.now()), TICK_MS);
        return () => clearInterval(id);
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  const hidden = typeof document !== 'undefined' ? document.hidden : false;

  const derived: FeedState = useMemo(() => {
    if (state) return state;
    return deriveFeedState({ lastAt, streamState, ticksFresh, fetching, marketClosed, dataQuality, now });
    // `now` is intentionally a dep: age transitions must re-derive each second.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, lastAt, streamState, ticksFresh, fetching, marketClosed, dataQuality, now]);

  const age = hidden ? null : ageLabel(lastAt, now);

  const label = hidden
    ? 'PAUSED · tab hidden'
    : stateLabel(derived, age, fetching);

  const tone = hidden ? 'idle' : feedPillTone(derived);
  const title = hidden
    ? 'Auto-refresh paused while the tab is hidden.'
    : feedStateDescription(derived);

  return (
    <span className={`feed-pill feed-pill--${tone} ${className ?? ''}`} title={title}>
      <i aria-hidden="true" />
      <span className="feed-pill__label">{label}</span>
      {sourceLabel ? <span className="feed-pill__meta">{sourceLabel}</span> : null}
      {note ? <span className="feed-pill__meta">{note}</span> : null}
      <span className="sr-only" role="status">
        {`${title} ${lastAt && age ? `Last update ${age}.` : ''}`}
      </span>
    </span>
  );
}

function stateLabel(s: FeedState, age: string | null, fetching?: boolean): string {
  switch (s) {
    case 'LIVE':
      return age ? `LIVE · ${age}` : 'LIVE';
    case 'SYNCING':
      return fetching ? 'SYNCING · updating' : 'SYNCING · waiting';
    case 'STALE':
      return age ? `STALE · ${age}` : 'STALE';
    case 'DEGRADED':
      return 'DEGRADED · fallback data';
    case 'DOWN':
      return 'DOWN · feed unavailable';
    case 'CLOSED':
      return 'CLOSED · market closed';
  }
}

export default FreshnessClock;
