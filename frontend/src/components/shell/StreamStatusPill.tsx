'use client';

import { useStreamStatus } from '@/context/AppStreamContext';
import { useNow } from '@/hooks/useNow';
import { ageLabel, feedPillTone } from '@/lib/feedState';
import { STREAM_STATE_LABELS, streamFeedState } from './status';

export function StreamStatusPill() {
  const status = useStreamStatus();
  const now = useNow(5000);
  const state = streamFeedState(status, now);
  // Age is hover-only: an always-ticking "1s ago, 2s ago…" readout reads like
  // a broken timer even when the stream is perfectly healthy.
  const age = now > 0 ? ageLabel(status.lastEventAt, now) : null;
  const source = status.source === 'sse' ? 'SSE' : 'FETCH';

  return (
    <span
      className={`feed-pill feed-pill--${feedPillTone(state)} feed-pill--stream`}
      title={`Unified app stream — ${source} · reconnects ${status.reconnects} · ${age ?? 'no frames yet'}`}
    >
      <i />
      {STREAM_STATE_LABELS[state]}
      <span className="feed-pill__meta">{source}</span>
    </span>
  );
}
