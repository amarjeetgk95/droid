'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { useOptionalLiveMarketContext } from '@/context/LiveMarketContext';
import ForecastCard, { type HourForecast } from '@/components/research/ForecastCard';
import { WhyStrip } from '@/components/dashboard/WhyStrip';
import { ForecastOutcomes } from '@/components/dashboard/ForecastOutcomes';
import { SupportingSignalsPanel } from '@/components/signals/SupportingSignalsPanel';

const INSTRUMENTS = ['NIFTY 50', 'BANKNIFTY', 'SENSEX'] as const;

const TIMEFRAMES = [
  { id: '1m', label: '1M' },
  { id: '5m', label: '5M' },
  { id: '15m', label: '15M' },
  { id: '30m', label: '30M' },
  { id: '1h', label: '1H' },
] as const;

type TimeframeId = (typeof TIMEFRAMES)[number]['id'];

export default function ForecastHomePage() {
  const [instrument, setInstrument] = useState<string>('NIFTY 50');
  const [timeframe, setTimeframe] = useState<TimeframeId>('1h');
  const [forecast, setForecast] = useState<HourForecast | null>(null);
  const [forecastLoading, setForecastLoading] = useState(true);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const market = useOptionalMarketDataContext();
  const live = useOptionalLiveMarketContext();
  const marketStatus = market?.marketStatus ?? null;
  const streamState = live?.streamState ?? market?.streamState ?? 'CONNECTING';
  const ticksFresh = live?.ticksFresh ?? market?.ticksFresh ?? false;

  const timeframeLabel = TIMEFRAMES.find((t) => t.id === timeframe)?.label ?? '1H';

  const loadForecast = useCallback(async () => {
    if (typeof document !== 'undefined' && document.hidden) return;
    setForecastLoading(true);
    setForecastError(null);
    try {
      const data = await api.getForecast(instrument, timeframe, true);
      setForecast(data as HourForecast);
      setLastUpdated(new Date());
    } catch (err) {
      setForecast(null);
      setForecastError(err instanceof Error ? err.message : 'forecast unavailable');
    } finally {
      setForecastLoading(false);
    }
  }, [instrument, timeframe]);

  useEffect(() => {
    void loadForecast();
  }, [loadForecast]);

  useEffect(() => {
    const id = setInterval(() => {
      if (typeof document !== 'undefined' && document.hidden) return;
      void loadForecast();
    }, 60000);
    return () => clearInterval(id);
  }, [loadForecast]);

  const isMarketClosed = marketStatus?.session === 'CLOSED' || marketStatus?.is_trading_day === false;
  const isStreamLive = !isMarketClosed && streamState === 'CONNECTED' && ticksFresh;
  const isStreamWaiting = !isMarketClosed && streamState === 'CONNECTED' && !ticksFresh;
  const feedTone = isMarketClosed ? 'stale-dot' : isStreamLive ? 'live-dot' : isStreamWaiting ? 'stale-dot' : 'down-dot';
  const feedLabel = isMarketClosed
    ? 'Session closed'
    : isStreamLive
      ? 'Feed live'
      : isStreamWaiting
        ? 'Feed stale — retrying'
        : 'Feed down';
  const sessionLabel = marketStatus?.session
    ? marketStatus.session.replace(/_/g, ' ').toLowerCase()
    : 'session —';

  return (
    <div className="ds-page">
      {/* header */}
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>{timeframeLabel} Forecast</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>LIVE MODEL</span>
            </div>
            <p className="muted num">
              {instrument} · {timeframeLabel} horizon · {sessionLabel} · <span className={feedTone} style={{ marginRight: 6 }} />{feedLabel}
              {lastUpdated ? ` · updated ${lastUpdated.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}` : ''}
            </p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Forecast horizon">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.id}
                type="button"
                className="seg-btn"
                data-active={timeframe === tf.id}
                aria-pressed={timeframe === tf.id}
                onClick={() => setTimeframe(tf.id)}
              >
                {tf.label}
              </button>
            ))}
          </div>
          <div className="seg" role="group" aria-label="Instrument">
            {INSTRUMENTS.map((inst) => (
              <button
                key={inst}
                type="button"
                className="seg-btn"
                data-active={instrument === inst}
                aria-pressed={instrument === inst}
                onClick={() => setInstrument(inst)}
              >
                {inst.replace(' 50', '')}
              </button>
            ))}
          </div>
          <button type="button" className="btn btn-primary" onClick={() => void loadForecast()} disabled={forecastLoading}>
            {forecastLoading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      {/* hero */}
      <ForecastCard
        forecast={forecast}
        loading={forecastLoading}
        error={forecastError}
        onRetry={() => void loadForecast()}
        updatedAt={lastUpdated}
        timeframe={timeframe}
        timeframeLabel={timeframeLabel}
      />

      {/* context */}
      <WhyStrip instrument={instrument} />

      {/* supporting signals */}
      <SupportingSignalsPanel />

      {/* track record */}
      <ForecastOutcomes instrument={instrument} timeframe={timeframe} />
    </div>
  );
}
