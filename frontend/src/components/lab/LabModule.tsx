'use client';

import { useMemo, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useCommandSection } from '@/context/AppStreamContext';
import { useResearchLab } from '@/hooks/useResearchLab';
import { useMlDesk } from '@/hooks/useMlDesk';
import { consensusOf, FORECAST_HORIZONS } from '@/lib/forecastBoard';
import { summarizeForecastSection, LAB_TABS, type LabTab } from '@/lib/labDesk';
import { narrowForecast } from '@/components/dashboard/sections';
import { ForecastPanel } from './ForecastPanel';
import { IndicatorsPanel } from './IndicatorsPanel';
import { ExperimentsPanel } from './ExperimentsPanel';
import { MlPanel } from './MlPanel';

export function LabModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const [tab, setTab] = useState<LabTab>('forecasts');

  const lab = useResearchLab(instrument, isOpen);
  const ml = useMlDesk(instrument, isOpen && tab === 'ml');

  const forecastSection = useCommandSection('forecast');
  const streamValue = useMemo(() => narrowForecast(forecastSection?.value), [forecastSection?.value]);
  const strip = useMemo(() => summarizeForecastSection(streamValue), [streamValue]);
  const consensus = useMemo(
    () => consensusOf(lab.board.forecasts as Parameters<typeof consensusOf>[0]),
    [lab.board.forecasts],
  );

  const consensusClass =
    consensus.tone === 'bull' ? 'b-bull' : consensus.tone === 'bear' ? 'b-bear' : 'b-neut';

  const updatedLabel = useMemo(() => {
    if (!lab.board.updatedAt) return '—';
    return new Date(lab.board.updatedAt).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }, [lab.board.updatedAt]);

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="Research and ML lab controls">
        <div className="ds-title">
          <h2>Research &amp; ML Lab</h2>
          <span className={`badge ${consensusClass}`} title="Weighted tactical consensus across horizons">
            {consensus.label}
          </span>
          <span className="card-meta">{lab.apiInstrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            horizons <b>{FORECAST_HORIZONS.length}</b>
          </span>
          <span className="stat-chip">
            ledger <b>{lab.predictions.length}</b>
          </span>
          <span className="stat-chip">
            indicators <b>{lab.indicators.length}</b>
          </span>
          <span className="stat-chip" title="Last completed forecast run">
            as of <b>{updatedLabel}</b>
          </span>
        </div>
        <div className="ds-filters">
          <button type="button" className="btn btn-ic" disabled={lab.board.refreshing} onClick={() => void lab.refreshAll()}>
            <FlaskConical size={13} />
            {lab.board.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <div className="pnl-strip" aria-label="Streamed prediction strip">
        <span className="ps">
          <span className="ps-l">stream predictions</span>
          <span className="ps-v num">{strip.count}</span>
        </span>
        <span className="ps">
          <span className="ps-l">bull</span>
          <span className="ps-v num">{strip.bull}</span>
        </span>
        <span className="ps">
          <span className="ps-l">bear</span>
          <span className="ps-v num">{strip.bear}</span>
        </span>
        <span className="ps">
          <span className="ps-l">source</span>
          <span className="ps-v num">command/forecast</span>
        </span>
      </div>

      <section className="tabbar w-fit" role="tablist" aria-label="Lab sections">
        {LAB_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'is-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {t.id === 'forecasts' ? <span className="n">{lab.predictions.length}</span> : null}
            {t.id === 'indicators' ? <span className="n">{lab.indicators.length}</span> : null}
          </button>
        ))}
      </section>

      {tab === 'forecasts' ? <ForecastPanel lab={lab} /> : null}
      {tab === 'indicators' ? <IndicatorsPanel lab={lab} /> : null}
      {tab === 'experiments' ? <ExperimentsPanel lab={lab} /> : null}
      {tab === 'ml' ? <MlPanel ml={ml} lab={lab} symbol={instrument} /> : null}
    </div>
  );
}
