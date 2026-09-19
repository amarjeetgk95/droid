'use client';

import { useMemo } from 'react';
import type {
  FIIDIIOverviewResponse,
  IndexCard,
  MarketBreadthData,
  MarketRegimeOverview,
  OptionsAnalytics,
} from '@/lib/types';
import { findInstrumentCard } from '@/lib/symbols';
import { safeInt, safeNum } from '@/lib/utils';
import { getObj, pickMs, pickNum, pickStr } from '@/lib/signalsNormalize';
import { KV, Panel } from '@/components/ui/Panel';
import {
  pickByInstrument,
  type ForecastSectionValue,
  type MarketSectionValue,
  type MlSectionValue,
  type RegimeSectionValue,
  type RiskEventsSectionValue,
} from './sections';

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const coords = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * 100;
      const y = 30 - ((point - min) / span) * 28;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
  const up = points[points.length - 1] >= points[0];
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="h-8 w-full" aria-hidden="true">
      <polyline
        points={coords}
        fill="none"
        strokeWidth={1.4}
        className={up ? 'stroke-up' : 'stroke-down'}
      />
    </svg>
  );
}

export function MarketPulsePanel({
  value,
  instrument,
}: {
  value: MarketSectionValue | null;
  instrument: string;
}) {
  const card: IndexCard | undefined = findInstrumentCard(value?.cards ?? [], instrument);
  const breadth: MarketBreadthData | null = value?.breadth ?? null;
  const session = value?.market_status?.session ?? null;

  return (
    <Panel
      title="Market Pulse"
      meta={session ? `${session} · ${value?.market_status?.provider ?? ''}` : undefined}
    >
      {card ? (
        <>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold tracking-wide text-ink-3">
                {card.display_name || card.symbol}
              </div>
              <div className="mono mt-0.5 text-[20px] font-bold leading-none text-ink">
                {safeNum(card.ltp)}
              </div>
              <div className={`mono mt-1 text-[13px] font-semibold ${card.change >= 0 ? 'v-bull' : 'v-bear'}`}>
                {card.change >= 0 ? '+' : ''}
                {safeNum(card.change)} ({card.change_percent >= 0 ? '+' : ''}
                {safeNum(card.change_percent)}%)
              </div>
            </div>
            <div className="w-32">
              <Sparkline points={card.sparkline ?? []} />
            </div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-x-4">
            <KV label="Open">{safeNum(card.open)}</KV>
            <KV label="Prev close">{safeNum(card.previous_close)}</KV>
            <KV label="High">{safeNum(card.high)}</KV>
            <KV label="Low">{safeNum(card.low)}</KV>
            <KV label="Volume">{safeInt(card.volume)}</KV>
            <KV label="Open interest">{safeInt(card.open_interest)}</KV>
          </div>
        </>
      ) : (
        <p className="m-0 text-[13px] text-ink-2">Index card unavailable for {instrument}.</p>
      )}

      {breadth ? (
        <div className="mt-3 border-t border-border-subtle pt-3">
          <div className="flex items-center justify-between">
            <span className="stat-l">Breadth</span>
            <span
              className={`badge ${
                breadth.sentiment.includes('BULLISH') ? 'b-bull' : breadth.sentiment.includes('BEARISH') ? 'b-bear' : 'b-neut'
              }`}
            >
              {breadth.sentiment.replace('_', ' ')}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <div>
              <div className="stat-l">Advancing</div>
              <div className="mono text-[13px] font-semibold v-bull">{safeInt(breadth.advancing)}</div>
            </div>
            <div>
              <div className="stat-l">Declining</div>
              <div className="mono text-[13px] font-semibold v-bear">{safeInt(breadth.declining)}</div>
            </div>
            <div>
              <div className="stat-l">A/D ratio</div>
              <div className="mono text-[13px] font-semibold">{safeNum(breadth.advance_decline_ratio)}</div>
            </div>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

function regimeTone(state: MarketRegimeOverview['regime_state'] | undefined): string {
  if (state === 'TRENDING_BULLISH') return 'b-bull';
  if (state === 'TRENDING_BEARISH') return 'b-bear';
  if (state === 'VOLATILE_EXPANSION' || state === 'RANGEBOUND_HIGH_VOL') return 'b-warn';
  return 'b-neut';
}

export function RegimePanel({ value }: { value: RegimeSectionValue | null }) {
  const regime = value?.regime_overview ?? null;
  const options = value?.options_analytics ?? null;

  if (!regime && !options) {
    return (
      <Panel title="Regime & Options Context">
        <p className="m-0 text-[13px] text-ink-2">Regime classification unavailable.</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Regime & Options Context"
      meta={regime?.symbol ?? options?.symbol ?? undefined}
    >
      {regime ? (
        <>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <span className={`badge ${regimeTone(regime.regime_state)}`}>
                {regime.regime_state.replace(/_/g, ' ')}
              </span>
              <p className="m-0 mt-1.5 text-[13px] leading-snug text-ink-2">{regime.summary_headline}</p>
            </div>
            <div className="text-right">
              <div className="mono text-[16px] font-bold">
                {Math.round(regime.confidence_score)}%
              </div>
              <div className="stat-l">confidence</div>
            </div>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4">
            <KV label="RSI 14">{safeNum(regime.indicators?.rsi_14)}</KV>
            <KV label="ADX 14">{safeNum(regime.indicators?.adx_14)}</KV>
            <KV label="ATR 14">{safeNum(regime.indicators?.atr_14)}</KV>
            <KV label="Supertrend">{regime.indicators?.supertrend_direction ?? '—'}</KV>
            <KV label="Support">{safeNum(regime.key_levels?.nearest_support)}</KV>
            <KV label="Resistance">{safeNum(regime.key_levels?.nearest_resistance)}</KV>
            <KV label="VIX">{safeNum(regime.vix_regime?.vix_value)}</KV>
            <KV label="VIX regime">
              {regime.vix_regime?.regime_category?.replace(/_/g, ' ') ?? '—'}
            </KV>
          </div>
        </>
      ) : null}

      {options ? (
        <div className="mt-3 border-t border-border-subtle pt-3">
          <div className="flex items-center justify-between">
            <span className="stat-l">Options analytics</span>
            {options.expiry ? <span className="card-meta">{options.expiry}</span> : null}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4">
            <KV label="ATM strike">{safeNum(options.atm_strike)}</KV>
            <KV label="ATM IV">{safeNum(options.atm_iv)}</KV>
            <KV label="PCR (OI)">{safeNum(options.pcr_oi)}</KV>
            <KV label="PCR (vol)">{safeNum(options.pcr_volume)}</KV>
            <KV label="Max pain">{safeNum(options.max_pain_strike)}</KV>
            <KV label="IV skew">{safeNum(options.iv_skew)}</KV>
          </div>
        </div>
      ) : null}
    </Panel>
  );
}

export function MlBiasPanel({
  value,
  instrument,
}: {
  value: MlSectionValue | null;
  instrument: string;
}) {
  const bySymbol = value?.by_symbol ?? null;
  const instrumentKey = instrument === 'NIFTY' ? 'NIFTY 50' : instrument;
  const prediction =
    pickByInstrument(bySymbol, instrumentKey) ??
    (instrument === 'NIFTY' ? value?.ml_prediction ?? null : null);

  if (!prediction) {
    return (
      <Panel title="ML Directional Bias">
        <p className="m-0 text-[13px] text-ink-2">
          No calibrated model output for {instrument}. The engine degrades to a neutral layer.
        </p>
      </Panel>
    );
  }

  const rows: Array<[string, number]> = [
    ['BULL', prediction.bullish_pct],
    ['NEUT', prediction.neutral_pct],
    ['BEAR', prediction.bearish_pct],
  ];

  return (
    <Panel title="ML Directional Bias" meta={`${prediction.model_version ?? ''} · ${prediction.market_regime ?? ''}`}>
      <div className="flex items-start justify-between gap-2">
        <span
          className={`badge ${
            prediction.predicted_bias === 'BULLISH'
              ? 'b-bull'
              : prediction.predicted_bias === 'BEARISH'
                ? 'b-bear'
                : 'b-neut'
          }`}
        >
          {prediction.predicted_bias}
        </span>
        <div className="text-right">
          <div className="mono text-[16px] font-bold">{safeNum(prediction.confidence_score)}</div>
          <div className="stat-l">confidence</div>
        </div>
      </div>
      <div className="mt-2 grid gap-1.5">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center gap-2">
            <span className="w-9 text-[11px] font-semibold tracking-wide text-ink-3">
              {label}
            </span>
            <span className="meter flex-1">
              <i
                className={label === 'BULL' ? 'bg-up' : label === 'BEAR' ? 'bg-down' : 'bg-border-strong'}
                style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
              />
            </span>
            <span className="mono w-9 text-right text-[11px]">{safeNum(value, '—', 0)}%</span>
          </div>
        ))}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-4">
        <KV label="Trend strength">{safeNum(prediction.trend_strength)}</KV>
        <KV label="Spot">{safeNum(prediction.spot_price)}</KV>
      </div>
      {prediction.top_features?.length ? (
        <div className="mt-2 border-t border-border-subtle pt-2">
          <span className="stat-l">Top drivers</span>
          <ul className="sg-list">
            {prediction.top_features.slice(0, 3).map((feature, index) => (
              <li key={`${feature.feature_name}-${index}`}>
                <span className="font-semibold">{feature.feature_name}</span>
                <span className="faint"> · {feature.description}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Panel>
  );
}

export function FlowRiskPanel({ value }: { value: RiskEventsSectionValue | null }) {
  const fiiDii: FIIDIIOverviewResponse | null = value?.fii_dii ?? null;
  const overlay = getObj(value?.event_risk ?? null);
  const proximity = overlay ? pickStr(overlay, 'proximity_state') : null;
  const canEnter = overlay && typeof overlay.can_enter === 'boolean' ? overlay.can_enter : null;
  const sizing = overlay ? pickNum(overlay, 'sizing_multiplier') : null;
  const triggerTitle = overlay ? pickStr(overlay, 'triggering_event_title') : null;
  const minutesToEvent = overlay ? pickNum(overlay, 'minutes_to_event') : null;

  return (
    <Panel title="Institutional Flow & Event Risk">
      {fiiDii ? (
        <>
          <div className="flex items-center justify-between">
            <span className="stat-l">FII / DII positioning</span>
            <span
              className={`badge ${
                fiiDii.institutional_sentiment?.includes('BULLISH')
                  ? 'b-bull'
                  : fiiDii.institutional_sentiment?.includes('BEARISH')
                    ? 'b-bear'
                    : 'b-neut'
              }`}
            >
              {(fiiDii.institutional_sentiment ?? 'NEUTRAL').replace(/_/g, ' ')}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4">
            <KV label="FII L/S ratio">{safeNum(fiiDii.fii_long_short_ratio)}</KV>
            <KV label="FII futures net">{safeInt(fiiDii.fii_futures_net_contracts)}</KV>
            <KV label="DII futures net">{safeInt(fiiDii.dii_futures_net_contracts)}</KV>
            <KV label="Client futures net">{safeInt(fiiDii.client_futures_net_contracts)}</KV>
            <KV label="FII cash net">{`${safeNum(fiiDii.fii_cash_net_crores)} Cr`}</KV>
            <KV label="DII cash net">{`${safeNum(fiiDii.dii_cash_net_crores)} Cr`}</KV>
          </div>
        </>
      ) : (
        <p className="m-0 text-[13px] text-ink-2">FII/DII flow unavailable.</p>
      )}

      <div className="mt-3 border-t border-border-subtle pt-3">
        <div className="flex items-center justify-between">
          <span className="stat-l">Event risk overlay</span>
          {proximity ? (
            <span
              className={`badge ${
                proximity === 'BLACKOUT_WINDOW' ? 'b-bear' : proximity === 'NORMAL' ? 'b-bull' : 'b-warn'
              }`}
            >
              {proximity.replace(/_/g, ' ')}
            </span>
          ) : null}
        </div>
        {overlay ? (
          <div className="mt-2 grid grid-cols-2 gap-x-4">
            <KV label="Entry allowed">{canEnter === null ? '—' : canEnter ? 'YES' : 'NO'}</KV>
            <KV label="Sizing multiplier">{sizing !== null ? `${Math.round(sizing * 100)}%` : '—'}</KV>
            <KV label="Trigger event">{triggerTitle ?? '—'}</KV>
            <KV label="Minutes to event">
              {minutesToEvent !== null ? safeNum(minutesToEvent, '—', 1) : '—'}
            </KV>
          </div>
        ) : (
          <p className="m-0 mt-1 text-[13px] text-ink-2">No active event constraints.</p>
        )}
      </div>
    </Panel>
  );
}

export function OptionsPanel({ value }: { value: RegimeSectionValue | null }) {
  const analytics: OptionsAnalytics | null = value?.options_analytics ?? null;
  if (!analytics) {
    return (
      <Panel title="Options Snapshot">
        <p className="m-0 text-[13px] text-ink-2">Options analytics unavailable.</p>
      </Panel>
    );
  }
  const maxPainBias =
    analytics.spot_price && analytics.max_pain_strike
      ? analytics.max_pain_strike > analytics.spot_price
        ? 'Max pain above spot — pin risk higher'
        : analytics.max_pain_strike < analytics.spot_price
          ? 'Max pain below spot — pin risk lower'
          : 'Max pain at spot'
      : null;

  return (
    <Panel title="Options Snapshot" meta={analytics.symbol}>
      <div className="grid grid-cols-2 gap-x-4">
        <KV label="Spot">{safeNum(analytics.spot_price)}</KV>
        <KV label="Futures">{safeNum(analytics.futures_price)}</KV>
        <KV label="ATM strike">{safeNum(analytics.atm_strike)}</KV>
        <KV label="ATM IV">{safeNum(analytics.atm_iv)}</KV>
        <KV label="PCR OI">{safeNum(analytics.pcr_oi)}</KV>
        <KV label="PCR volume">{safeNum(analytics.pcr_volume)}</KV>
        <KV label="Max pain">{safeNum(analytics.max_pain_strike)}</KV>
        <KV label="IV skew">{safeNum(analytics.iv_skew)}</KV>
        <KV label="Total call OI">{safeInt(analytics.total_call_oi)}</KV>
        <KV label="Total put OI">{safeInt(analytics.total_put_oi)}</KV>
        <KV label="Expiry">{analytics.expiry ?? '—'}</KV>
        <KV label="Days to expiry">{safeNum(analytics.time_to_expiry_days, '—', 1)}</KV>
      </div>
      {maxPainBias ? <p className="sg-note mt-2">{maxPainBias}</p> : null}
    </Panel>
  );
}

export function PredictionTrackPanel({
  value,
  instrument,
}: {
  value: ForecastSectionValue | null;
  instrument: string;
}) {
  const predictions = value?.predictions ?? null;
  const byInstrument = value?.by_instrument ?? null;
  const scoped = useMemo(() => {
    if (instrument === 'NIFTY 50') return predictions ?? [];
    const key = Object.keys(byInstrument ?? {}).find(
      (candidate) => candidate.toUpperCase() === instrument.toUpperCase(),
    );
    return key ? byInstrument?.[key] ?? [] : [];
  }, [instrument, predictions, byInstrument]);

  const rows = scoped.filter((row) => getObj(row) !== null);
  const scored = rows
    .map((raw) => getObj(raw))
    .filter((row): row is Record<string, unknown> => row !== null)
    .slice(0, 6);

  return (
    <Panel title="Prediction Track Record" meta={`${rows.length} recorded`}>
      {scored.length === 0 ? (
        <p className="m-0 text-[13px] text-ink-2">
          No recorded predictions for {instrument} in this window.
        </p>
      ) : (
        <div className="tbl-scroll">
          <table className="tbl tbl-dense">
            <thead>
              <tr>
                <th>Time</th>
                <th>Horizon</th>
                <th>Direction</th>
                <th className="r">Score</th>
                <th className="r">Conf</th>
              </tr>
            </thead>
            <tbody>
              {scored.map((row, index) => {
                const direction = (pickStr(row, 'direction') ?? '—').toUpperCase();
                const timeMs = pickMs(row, 'created_at', 'timestamp');
                const confidence = pickNum(row, 'confidence');
                return (
                  <tr key={pickStr(row, 'prediction_id') ?? index}>
                    <td className="mono">
                      {timeMs !== null ? new Date(timeMs).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td className="mono">{pickStr(row, 'forecast_horizon') ?? pickStr(row, 'timeframe') ?? '—'}</td>
                    <td>
                      <span
                        className={`sg-dir ${direction === 'BULLISH' ? 'long' : direction === 'BEARISH' ? 'short' : 'neut'}`}
                      >
                        {direction}
                      </span>
                    </td>
                    <td className="r mono">{safeNum(pickNum(row, 'score'), '—', 0)}</td>
                    <td className="r mono">
                      {confidence !== null ? `${Math.round(confidence * 100)}%` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
