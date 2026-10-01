'use client';

import { useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { usePapLive } from '@/hooks/usePapLive';
import { PapLivePanel } from './PapLivePanel';
import { PapResearchView } from './PapResearchView';

type PapTab = 'live' | 'research';

export function PapModule() {
  const { instrument, setInstrument, allInstruments } = useInstrument();
  const { isOpen } = useMarketSession();
  const [tab, setTab] = useState<PapTab>('live');
  const live = usePapLive(instrument, isOpen && tab === 'live');

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="PAP intelligence controls">
        <div className="ds-title">
          <h2>Signal Centre · PAP</h2>
          <span className="card-meta">{instrument}</span>
          <span className="card-meta" title={isOpen ? 'Market open' : 'Market closed'}>
            {isOpen ? 'market open' : 'market closed'}
          </span>
        </div>
        <div className="ds-filters">
          <span className="seg" title="Instrument">
            {allInstruments.map((o) => (
              <button
                key={o}
                type="button"
                className="seg-btn"
                data-active={instrument === o}
                onClick={() => setInstrument(o)}
              >
                {o}
              </button>
            ))}
          </span>
          <button type="button" className="btn" disabled={live.refreshing} onClick={() => void live.refresh()}>
            {live.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="PAP sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'live'}
          className={`tab ${tab === 'live' ? 'is-active' : ''}`}
          onClick={() => setTab('live')}
        >
          Live PAP
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'research'}
          className={`tab ${tab === 'research' ? 'is-active' : ''}`}
          onClick={() => setTab('research')}
        >
          Research
        </button>
      </section>

      {tab === 'live' ? (
        <PapLivePanel live={live.live} error={live.error} loading={live.loading} />
      ) : (
        <PapResearchView />
      )}
    </div>
  );
}
