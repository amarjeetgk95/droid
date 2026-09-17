'use client';

import type { TechnicalIndicators } from '@/lib/types';
import { Card, DirectionBadge, EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';
import { finiteNum, hasIndicatorData, posNum } from './truthful';

function rsiReading(rsi: number): string {
  if (rsi >= 70) return 'Overbought';
  if (rsi <= 30) return 'Oversold';
  if (rsi >= 50) return 'Bullish zone';
  return 'Bearish zone';
}

export function IndicatorsGrid({
  indicators,
  spotPrice,
  provenance,
  stale,
}: {
  indicators: TechnicalIndicators | null;
  spotPrice: number;
  provenance?: string | null;
  stale?: boolean;
}) {
  if (!indicators || !hasIndicatorData(indicators)) {
    return (
      <Card
        title="Indicators"
        meta={indicators ? 'no data' : 'unavailable'}
        action={stale ? <span className="badge b-warn">STALE</span> : undefined}
      >
        <EmptyNote>
          {indicators
            ? 'Provider returned placeholder indicator values (no candle data) — treated as unavailable.'
            : 'No technical indicators available.'}
        </EmptyNote>
        {provenance ? (
          <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
            {provenance}
          </p>
        ) : null}
      </Card>
    );
  }

  const spot = posNum(spotPrice);

  const rsiRaw = finiteNum(indicators.rsi_14);
  const rsi = rsiRaw !== null && rsiRaw > 0 && rsiRaw <= 100 ? rsiRaw : null;

  const adx = finiteNum(indicators.adx_14);
  const plusDi = finiteNum(indicators.plus_di);
  const minusDi = finiteNum(indicators.minus_di);

  const atr = posNum(indicators.atr_14);
  const atrPct =
    atr !== null && spot !== null ? `${((atr / spot) * 100).toFixed(2)}% of spot` : '—';

  const supertrendValue = posNum(indicators.supertrend_value);
  const supertrendDirection =
    supertrendValue !== null &&
    (indicators.supertrend_direction === 'BULLISH' || indicators.supertrend_direction === 'BEARISH')
      ? indicators.supertrend_direction
      : null;

  const bbUpper = posNum(indicators.bollinger_upper);
  const bbMiddle = posNum(indicators.bollinger_middle);
  const bbLower = posNum(indicators.bollinger_lower);
  const bbBandwidth = posNum(indicators.bollinger_bandwidth);
  const bbPctB = finiteNum(indicators.bollinger_pct_b);
  const bbKnown = bbUpper !== null || bbMiddle !== null || bbLower !== null || bbBandwidth !== null;

  const emaStack: Array<{ label: string; value: number | null }> = [
    { label: '20', value: posNum(indicators.ema_20) },
    { label: '50', value: posNum(indicators.ema_50) },
    { label: '200', value: posNum(indicators.sma_200) },
  ];
  const available = emaStack.filter((e): e is { label: string; value: number } => e.value !== null);
  const above = spot !== null ? available.filter((e) => spot > e.value).length : 0;
  const emaReading =
    available.length === 0 || spot === null
      ? '—'
      : above === available.length
        ? 'Spot above stack'
        : above === 0
          ? 'Spot below stack'
          : `Spot mid-stack (${above}/${available.length} above)`;

  return (
    <Card
      title="Indicators"
      meta={spot !== null ? `Spot ${fmtINR(spot)}` : undefined}
      action={stale ? <span className="badge b-warn">STALE</span> : undefined}
    >
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Indicator</th>
              <th className="r">Value</th>
              <th>Reading</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>RSI (14)</td>
              <td className="r num">{fmtNum(rsi, 1)}</td>
              <td className="muted">{rsi === null ? 'no data' : rsiReading(rsi)}</td>
            </tr>
            <tr>
              <td>ADX (14)</td>
              <td className="r num">{fmtNum(adx, 1)}</td>
              <td className="muted">
                {adx === null ? 'no data' : adx >= 25 ? 'Strong trend' : 'Non-trending'}
                {adx !== null && plusDi !== null && minusDi !== null ? (
                  <>
                    {' '}
                    · +DI {fmtNum(plusDi, 1)} / -DI {fmtNum(minusDi, 1)}
                  </>
                ) : null}
              </td>
            </tr>
            <tr>
              <td>Supertrend (10, 3)</td>
              <td className="r num">{fmtINR(supertrendValue)}</td>
              <td className="muted">
                {supertrendDirection ? <DirectionBadge direction={supertrendDirection} /> : 'no data'}
              </td>
            </tr>
            <tr>
              <td>Bollinger bandwidth</td>
              <td className="r num">{bbBandwidth !== null ? `${fmtNum(bbBandwidth, 2)}%` : '—'}</td>
              <td className="muted num">
                {bbKnown
                  ? `Upper ${fmtINR(bbUpper)} · Middle ${fmtINR(bbMiddle)} · Lower ${fmtINR(bbLower)} · %B ${
                      bbPctB !== null ? fmtNum(bbPctB, 2) : '—'
                    }`
                  : 'no data'}
              </td>
            </tr>
            <tr>
              <td>ATR (14)</td>
              <td className="r num">{atr !== null ? `${fmtNum(atr, 1)} pts` : '—'}</td>
              <td className="muted num">{atrPct}</td>
            </tr>
            <tr>
              <td>EMA 20 / 50 · SMA 200</td>
              <td className="r num">
                {emaStack.map((e) => `${e.label}: ${fmtINR(e.value)}`).join(' · ')}
              </td>
              <td className="muted">{emaReading}</td>
            </tr>
          </tbody>
        </table>
      </div>
      {provenance ? (
        <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
          {provenance}
        </p>
      ) : null}
    </Card>
  );
}
