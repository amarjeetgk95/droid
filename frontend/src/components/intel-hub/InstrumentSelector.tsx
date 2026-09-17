'use client';

import React from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useIntelHub } from './IntelHubData';
import { PanelNotice, PulseDot, feedTone } from './IntelHubUi';
import { Badge } from '../shared/Badge';

export const InstrumentSelector: React.FC = () => {
  const { instrument, setInstrument, allInstruments } = useInstrument();
  const { mi, miError, miStatus } = useIntelHub();

  const feedHealth = mi?.feed.health ?? mi?.dataHealth.feed ?? null;
  const sessionType = mi?.session.sessionType ?? null;
  const sessionOpen = mi?.session.isOpen ?? null;
  const sequenceGap = mi?.sequenceGap ?? null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3 shadow-xs">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs font-semibold uppercase tracking-wider text-ink-3">
          MARKET INTELLIGENCE DESK:
        </span>
        <div
          role="group"
          aria-label="Instrument"
          className="flex items-center rounded-lg border border-border bg-muted p-0.5"
        >
          {allInstruments.map((inst) => (
            <button
              key={inst}
              type="button"
              aria-pressed={instrument === inst}
              onClick={() => setInstrument(inst)}
              className={`rounded-md px-4 py-1.5 font-mono text-xs font-bold transition-all ${
                instrument === inst
                  ? 'bg-primary text-white shadow-xs'
                  : 'text-ink-2 hover:bg-muted-strong hover:text-ink'
              }`}
            >
              {inst}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2" aria-live="polite">
        {miStatus === 'loading' ? (
          <Badge variant="neutral" size="xs">
            <PulseDot tone="warn" /> SYNCING FEED
          </Badge>
        ) : null}

        {feedHealth ? (
          <Badge
            variant={feedTone(feedHealth) === 'up' ? 'success' : feedTone(feedHealth) === 'down' ? 'danger' : 'warning'}
            size="xs"
          >
            <PulseDot tone={feedTone(feedHealth)} pulse={feedTone(feedHealth) !== 'down'} />
            FEED: {feedHealth.toUpperCase()}
          </Badge>
        ) : null}

        {sessionType ? (
          <Badge variant={sessionOpen === true ? 'info' : 'neutral'} size="xs">
            SESSION: {sessionType.toUpperCase()}
          </Badge>
        ) : null}

        {sequenceGap !== null ? (
          <Badge variant={sequenceGap ? 'danger' : 'success'} size="xs">
            SEQUENCE: {sequenceGap ? 'GAP' : 'CONTIGUOUS'}
          </Badge>
        ) : null}

        {miStatus === 'error' && !mi ? (
          <PanelNotice tone="down" role="alert">
            {miError ?? 'Feed unavailable'}
          </PanelNotice>
        ) : null}
      </div>
    </div>
  );
};
