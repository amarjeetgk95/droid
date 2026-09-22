'use client';

import type { HourForecast } from '@/lib/types';
import {
  HORIZON_LABELS,
  confidenceFallbackLabel,
  confidencePct,
  directionLabel,
  expectedMoveFallbackLabel,
  expectedMovePct,
  forecastTone,
  layerRows,
  statusClass,
  type ForecastHorizonId,
} from '@/lib/forecastBoard';
import {
  UNSETTLEABLE_NOTE,
  calibrationLabel,
  forecastWhyTooltip,
  getCacheAgeSeconds,
  getDataQualityLabel,
  getForecastStatusLabel,
  getSettleReason,
  getSettlementLabel,
  isStaleForecast,
  probabilityBars,
  shortForecastId,
  type ForecastV2Status,
} from '@/lib/forecastStatus';
import { safeNum } from '@/lib/utils';

function toneValueClass(tone: 'bull' | 'bear' | 'neut'): string {
  if (tone === 'bull') return 'v-bull';
  if (tone === 'bear') return 'v-bear';
  return 'text-ink-2';
}

export function ForecastHorizonCard({
  horizon,
  forecast,
  error,
  loading,
}: {
  horizon: ForecastHorizonId;
  forecast: HourForecast | null | undefined;
  error?: string;
  loading: boolean;
}) {
  if (loading && !forecast && !error) {
    return (
      <div className="forecast-hero card-pad" data-tone="neut">
        <div className="flex items-center justify-between">
          <span className="skel text-[17px] font-bold">{HORIZON_LABELS[horizon]}</span>
          <span className="skel text-xs">LOADING</span>
        </div>
        <div className="mt-3 grid gap-2">
          <span className="skel block h-3 w-2/3" />
          <span className="skel block h-6 w-1/2" />
          <span className="skel block h-3 w-full" />
          <span className="skel block h-3 w-5/6" />
        </div>
      </div>
    );
  }

  if (error || !forecast) {
    return (
      <div className="forecast-hero card-pad" data-tone="neut">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[17px] font-bold text-ink">{HORIZON_LABELS[horizon]}</span>
          <span className="badge b-warn">UNAVAILABLE</span>
        </div>
        <p className="mt-2 text-xs leading-snug text-ink-2">
          {error ?? 'No forecast returned for this horizon.'}
        </p>
      </div>
    );
  }

  const tone = forecastTone(forecast);
  const status = getForecastStatusLabel(forecast);
  const confidence = confidencePct(forecast);
  const confidenceFallback = confidenceFallbackLabel(forecast);
  const bars = probabilityBars(forecast);
  const layers = layerRows(forecast);
  const movePct = expectedMovePct(forecast);
  const moveFallback = expectedMoveFallbackLabel(forecast);
  const quality = getDataQualityLabel(forecast);
  const settlement = getSettlementLabel(forecast);
  const predictionId = shortForecastId(forecast.prediction_id);
  const whyTitle = forecastWhyTooltip(forecast);
  const settleReason = getSettleReason(forecast);
  const stale = isStaleForecast(forecast);
  const cacheAge = getCacheAgeSeconds(forecast);

  return (
    <div className="forecast-hero" data-tone={tone}>
      <div className="card-pad">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="text-[17px] font-bold leading-none text-ink">
                {HORIZON_LABELS[horizon]}
              </span>
              <span className={`badge ${tone === 'bull' ? 'b-bull' : tone === 'bear' ? 'b-bear' : 'b-neut'}`}>
                {directionLabel(forecast)}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide text-ink-3">
              <span>{forecast.timeframe ?? horizon}</span>
              {forecast.session ? <span>· {forecast.session}</span> : null}
              <span>· {status}</span>
            </div>
          </div>
          <div className="text-right">
            <div className={`text-[17px] font-bold leading-none ${toneValueClass(tone)}`}>
              {confidence !== null ? `${confidence}%` : '—'}
            </div>
            <div className="mt-0.5 text-[11px] font-semibold tracking-wide text-ink-3">
              confidence{confidenceFallback ? ` · ${confidenceFallback}` : ''}
            </div>
          </div>
        </div>

        {bars ? (
          <div className="mt-2.5">
            <div className="prob-bar-stacked" role="img" aria-label={`Bull ${bars[0].pct}%, neutral ${bars[1].pct}%, bear ${bars[2].pct}%`}>
              <i className="seg-bull" style={{ width: `${bars[0].pct}%` }} />
              <i className="seg-neut" style={{ width: `${bars[1].pct}%` }} />
              <i className="seg-bear" style={{ width: `${bars[2].pct}%` }} />
            </div>
            <div className="mt-1 flex items-center justify-between font-mono text-[11px] text-ink-2">
              <span className="v-bull">BULL {bars[0].pct}%</span>
              <span>NEUT {bars[1].pct}%</span>
              <span className="v-bear">BEAR {bars[2].pct}%</span>
            </div>
          </div>
        ) : null}

        <div className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5">
          <div>
            <div className="stat-l">Spot</div>
            <div className="mono text-[13px] font-semibold">{safeNum(forecast.current_price, '—')}</div>
          </div>
          <div>
            <div className="stat-l">Target</div>
            <div className="mono text-[13px] font-semibold">{safeNum(forecast.target_price, '—')}</div>
          </div>
          <div>
            <div className="stat-l">Invalidation</div>
            <div className="mono text-[13px] font-semibold">{safeNum(forecast.invalidation_price, '—')}</div>
          </div>
          <div>
            <div className="stat-l">Expected move</div>
            <div className="mono text-[13px] font-semibold" title={moveFallback ?? undefined}>
              {movePct !== null ? `${movePct.toFixed(2)}%${moveFallback ? ' · fallback' : ''}` : '—'}
            </div>
          </div>
        </div>

        {layers.length > 0 ? (
          <div className="mt-2.5 grid gap-1">
            {layers.map((layer) => (
              <div key={layer.key} className="flex items-center gap-2">
                <span className="w-7 text-[11px] font-semibold tracking-wide text-ink-3">
                  {layer.label}
                </span>
                <span className="mini-meter-track">
                  <i
                    className={layer.tone === 'bull' ? 'bg-up' : layer.tone === 'bear' ? 'bg-down' : 'bg-border-strong'}
                    style={{ width: `${layer.pct}%` }}
                  />
                </span>
                <span className={`mono text-[11px] ${layer.tone === 'bull' ? 'v-bull' : layer.tone === 'bear' ? 'v-bear' : 'text-ink-2'}`}>
                  {layer.tone === 'bear' ? '-' : ''}
                  {layer.pct}
                </span>
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t border-border-subtle px-2.5 py-1.5">
        <span className={`badge ${statusClass(status as ForecastV2Status)}`} title={whyTitle}>
          {status}
        </span>
        {quality ? (
          <span className="badge b-neut" title={whyTitle}>
            {quality}
          </span>
        ) : null}
        <span className="badge b-neut" title={whyTitle}>
          {calibrationLabel(forecast)}
        </span>
        {settlement ? (
          <span
            className={`badge ${settlement === 'YES' ? 'b-bull' : 'b-warn'}`}
            title={
              settlement === 'NO'
                ? [UNSETTLEABLE_NOTE, settleReason].filter(Boolean).join(' — ')
                : whyTitle
            }
          >
            SETTLE {settlement}
          </span>
        ) : null}
        {stale ? (
          <span
            className="badge b-warn"
            title={
              cacheAge !== null
                ? `Served from cache — ${Math.round(cacheAge)}s since the last successful run`
                : 'Served from cache — live regeneration failed or is in flight'
            }
          >
            STALE
          </span>
        ) : null}
        <span className="ml-auto font-mono text-[11px] text-ink-3">
          {forecast.latency_ms != null ? `${Math.round(forecast.latency_ms)}ms` : ''}
          {predictionId ? ` · ${predictionId}` : ''}
        </span>
      </div>
    </div>
  );
}
