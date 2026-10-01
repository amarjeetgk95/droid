'use client';

import { useMemo, useState } from 'react';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useCommandSection } from '@/context/AppStreamContext';
import { narrowRiskEvents } from '@/components/dashboard/sections';
import { useEventsDesk, useInstitutionalDesk } from '@/hooks/useIntelDesk';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { badgeClass, healthTone } from '@/lib/intelDesk';
import { InstitutionalTab } from './InstitutionalTab';
import { EventsTab } from './EventsTab';

type TopTab = 'institutional' | 'events';

function interpretPcr(value: number | null): string | null {
  if (value === null) return null;
  if (value > 1.2) return 'bullish';
  if (value < 0.8) return 'bearish';
  if (value >= 0.9 && value <= 1.1) return 'neutral';
  return 'mixed';
}

function interpretSizing(multiplier: number | null | undefined): string | null {
  if (multiplier === null || multiplier === undefined) return null;
  if (multiplier >= 1.0) return 'full size';
  if (multiplier >= 0.75) return 'reduced';
  return 'minimal';
}

export function IntelModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const [tab, setTab] = useState<TopTab>('institutional');

  const inst = useInstitutionalDesk(instrument, { pollMs: isOpen ? 60_000 : null });
  const events = useEventsDesk(instrument, { pollMs: isOpen ? 60_000 : null });

  const riskSection = useCommandSection('risk_events');
  const risk = useMemo(() => narrowRiskEvents(riskSection?.value), [riskSection?.value]);

  const overlay = useMemo(() => getObj(risk?.event_risk ?? null), [risk]);
  const proximity = overlay ? pickStr(overlay, 'proximity_state') : events.overlay?.proximity_state ?? null;
  const canEnter = overlay && typeof overlay.can_enter === 'boolean'
    ? overlay.can_enter
    : (events.overlay?.can_enter ?? null);
  const sizing = overlay ? pickNum(overlay, 'sizing_multiplier') : (events.overlay?.sizing_multiplier ?? null);
  const fiiSentiment = risk?.fii_dii?.institutional_sentiment ?? null;

  const proximityTone = healthTone(proximity);
  const activeEventCount = events.today.filter((e) => e.temporal_phase === 'ACTIVE').length;

  const updatedLabel = useMemo(() => {
    const at = Math.max(inst.updatedAt ?? 0, events.updatedAt ?? 0);
    if (!at) return '—';
    return new Date(at).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }, [inst.updatedAt, events.updatedAt]);

  const busy = tab === 'institutional' ? inst.refreshing : events.refreshing;
  const error = tab === 'institutional' ? inst.error : events.error;

  const regime = inst.mi?.regime?.replace(/_/g, ' ');
  const regimeLabel = regime && regime !== '—' ? regime.toLowerCase() : null;

  const pcrRaw = pickNum(getObj(inst.callsPuts) ?? {}, 'pcr');
  const pcrInterpretation = interpretPcr(pcrRaw);
  const sizingInterpretation = interpretSizing(sizing);

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="Intelligence hub controls" aria-busy={busy}>
        <div className="ds-title">
          <h2>Intelligence Hub</h2>
          <span className={`badge ${isOpen ? 'b-bull' : 'b-neut'}`}>
            {isOpen ? 'MARKET OPEN' : 'MARKET CLOSED'}
          </span>
          {regimeLabel ? (
            <span className={`badge ${badgeClass(healthTone(inst.mi?.regime))}`} title="Current market regime">
              {regimeLabel}
            </span>
          ) : null}
          {proximity ? (
            <span className={`badge ${badgeClass(proximityTone)}`} title="Event proximity (stream + overlay)">
              {proximity.replace(/_/g, ' ')}
            </span>
          ) : null}
          <span className="card-meta">{instrument}</span>
        </div>
        <div className="stat-chips">
          {regime ? (
            <span className="stat-chip" title="Current market regime">
              regime <b>{regime}</b>
            </span>
          ) : null}
          <span className="stat-chip" title="Can new trades enter right now?">
            entry <b>{canEnter === null ? '—' : canEnter ? 'OPEN' : 'BLOCKED'}</b>
          </span>
          {sizing !== null && sizing !== undefined ? (
            <span className="stat-chip" title={`Size multiplier: ${Math.round(Number(sizing) * 100)}%`}>
              size <b>{Math.round(Number(sizing) * 100)}%</b>
              {sizingInterpretation ? <span className={`sg-tag ${sizingInterpretation === 'full size' ? 'bull' : sizingInterpretation === 'reduced' ? 'warn' : 'neut'}`} style={{ marginLeft: 4 }}>{sizingInterpretation}</span> : null}
            </span>
          ) : null}
          <span className="stat-chip" title="Currently active events">
            live <b>{activeEventCount}</b>
          </span>
          <span className="stat-chip" title="FII/DII institutional money flow">
            flow <b>{fiiSentiment ? fiiSentiment.replace(/_/g, ' ') : '—'}</b>
          </span>
          {pcrRaw !== null ? (
            <span className="stat-chip" title={`Put/Call ratio = ${pcrRaw.toFixed(2)}`}>
              pcr <b>{pcrRaw.toFixed(2)}</b>
              {pcrInterpretation ? <span className={`sg-tag ${pcrInterpretation === 'bullish' ? 'bull' : pcrInterpretation === 'bearish' ? 'bear' : 'neut'}`} style={{ marginLeft: 4 }}>{pcrInterpretation}</span> : null}
            </span>
          ) : null}
          <span className="stat-chip" title="Time of last data refresh">
            as of <b>{updatedLabel}</b>
          </span>
        </div>
        <div className="ds-filters">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => void (tab === 'institutional' ? inst.refresh() : events.refresh())}
          >
            {busy ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="Intelligence hub sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'institutional'}
          className={`tab ${tab === 'institutional' ? 'is-active' : ''}`}
          onClick={() => setTab('institutional')}
        >
          Institutional <span className="n">{inst.signals.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'events'}
          className={`tab ${tab === 'events' ? 'is-active' : ''}`}
          onClick={() => setTab('events')}
        >
          Events <span className="n">{events.today.length + events.upcoming.length}</span>
        </button>
      </section>

      {error ? <p className="sg-err">{error}</p> : null}

      {tab === 'institutional' ? (
        <InstitutionalTab desk={inst} instrument={instrument} />
      ) : (
        <EventsTab desk={events} underlying={instrument} isOpen={isOpen} />
      )}
    </div>
  );
}
