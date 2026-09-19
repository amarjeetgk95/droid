'use client';

import { useMemo } from 'react';
import { RefreshCw } from 'lucide-react';
import { useCommandSection } from '@/context/AppStreamContext';
import { useInstrument } from '@/context/InstrumentContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { useForecastBoard } from '@/hooks/useForecastBoard';
import {
  FORECAST_HORIZONS,
  consensusOf,
  forecastInstrument,
} from '@/lib/forecastBoard';
import { isStaleForecast } from '@/lib/forecastStatus';
import { ForecastHorizonCard } from './ForecastHorizonCard';
import {
  FlowRiskPanel,
  MarketPulsePanel,
  MlBiasPanel,
  OptionsPanel,
  PredictionTrackPanel,
  RegimePanel,
} from './ContextPanels';
import { HealthPanel } from './HealthPanel';
import {
  narrowFeedHealth,
  narrowForecast,
  narrowMarket,
  narrowMl,
  narrowRegime,
  narrowRiskEvents,
} from './sections';

export function DashboardModule() {
  const { instrument } = useInstrument();
  const { isOpen } = useMarketSession();
  const apiInstrument = forecastInstrument(instrument);

  const board = useForecastBoard(apiInstrument, { autoRefreshMs: isOpen ? 60_000 : null });

  const marketSection = useCommandSection('market');
  const regimeSection = useCommandSection('regime');
  const mlSection = useCommandSection('ml');
  const riskSection = useCommandSection('risk_events');
  const feedSection = useCommandSection('feed_health');
  const forecastSection = useCommandSection('forecast');

  const market = useMemo(() => narrowMarket(marketSection?.value), [marketSection?.value]);
  const regime = useMemo(() => narrowRegime(regimeSection?.value), [regimeSection?.value]);
  const ml = useMemo(() => narrowMl(mlSection?.value), [mlSection?.value]);
  const risk = useMemo(() => narrowRiskEvents(riskSection?.value), [riskSection?.value]);
  const feed = useMemo(() => narrowFeedHealth(feedSection?.value), [feedSection?.value]);
  const forecast = useMemo(() => narrowForecast(forecastSection?.value), [forecastSection?.value]);

  const consensus = useMemo(() => consensusOf(board.forecasts), [board.forecasts]);
  const errorCount = Object.keys(board.errors).length;
  const staleCount = useMemo(
    () => Object.values(board.forecasts).filter((f) => isStaleForecast(f)).length,
    [board.forecasts],
  );

  const updatedLabel = useMemo(() => {
    if (!board.updatedAt) return '—';
    const clock = new Date(board.updatedAt).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    return `${clock} IST`;
  }, [board.updatedAt]);

  const consensusClass =
    consensus.tone === 'bull' ? 'b-bull' : consensus.tone === 'bear' ? 'b-bear' : 'b-neut';

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar" aria-label="Market forecast controls" aria-busy={board.refreshing}>
        <div className="ds-title">
          <span className="cmd-hd">
            <span className="micro-label">Tactical forecast · 1m–60m</span>
            <h2>Market Forecast</h2>
          </span>
          <span className={`badge ${consensusClass}`} title={`Weighted across horizons: ${consensus.weightedScore}`}>
            {consensus.label}
            {consensus.label !== 'NO DATA' ? ` ${consensus.weightedScore > 0 ? '+' : ''}${consensus.weightedScore}` : ''}
          </span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            instrument <b>{apiInstrument}</b>
          </span>
          <span className="stat-chip">
            horizons <b>{FORECAST_HORIZONS.length}</b>
          </span>
          <span className="stat-chip" title="Server time of the last completed forecast run">
            as of <b>{updatedLabel}</b>
          </span>
          {staleCount > 0 ? (
            <span
              className="stat-chip"
              style={{ color: 'var(--ds-warn-strong)' }}
              title="Served from the last successful run — live regeneration failed or is in flight"
            >
              {staleCount} stale
            </span>
          ) : null}
          {errorCount > 0 ? (
            <span className="stat-chip" style={{ color: 'var(--ds-warn-strong)' }}>{errorCount} horizon error(s)</span>
          ) : null}
        </div>
        <div className="ds-filters">
          <button
            type="button"
            className="btn btn-primary btn-ic"
            disabled={board.refreshing}
            onClick={() => void board.refresh({ record: true })}
            title="Regenerate all horizons and persist immutable predictions"
          >
            <RefreshCw size={13} className={board.refreshing ? 'animate-spin' : undefined} />
            {board.refreshing ? 'Generating…' : 'Generate forecast'}
          </button>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {FORECAST_HORIZONS.map((horizon) => (
          <ForecastHorizonCard
            key={horizon}
            horizon={horizon}
            forecast={board.forecasts[horizon]}
            error={board.errors[horizon]}
            loading={board.loading}
          />
        ))}
      </div>

      <div className="ds-grid-dashboard">
        <MarketPulsePanel value={market} instrument={instrument} />
        <RegimePanel value={regime} />
        <MlBiasPanel value={ml} instrument={instrument} />
        <OptionsPanel value={regime} />
        <FlowRiskPanel value={risk} />
        <HealthPanel feed={feed} />
        <PredictionTrackPanel value={forecast} instrument={apiInstrument} />
      </div>
    </div>
  );
}
