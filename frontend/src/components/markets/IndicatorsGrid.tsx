'use client';

import type { TechnicalIndicators } from '@/lib/types';
import { Card, DirectionBadge, EmptyNote, fmtINR, fmtNum } from '@/components/ui/desk';

function rsiReading(rsi: number): string {
  if (rsi >= 70) return 'Overbought';
  if (rsi <= 30) return 'Oversold';
  if (rsi >= 50) return 'Bullish zone';
  return 'Bearish zone';
}

export function IndicatorsGrid({
  indicators,
  spotPrice,
}: {
  indicators: TechnicalIndicators | null;
  spotPrice: number;
}) {
  if (!indicators) {
    return (
      <Card title="Indicators" meta="unavailable">
        <EmptyNote>No technical indicators available.</EmptyNote>
      </Card>
    );
  }

  const rsi = indicators.rsi_14 ?? 50;
  const adx = indicators.adx_14 ?? 0;
  const atr = indicators.atr_14;
  const atrPct =
    typeof atr === 'number' && Number.isFinite(atr) && spotPrice
      ? `${((atr / spotPrice) * 100).toFixed(2)}% of spot`
      : '—';

  const emaStack: Array<{ label: string; value: number | null | undefined }> = [
    { label: '20', value: indicators.ema_20 },
    { label: '50', value: indicators.ema_50 },
    { label: '200', value: indicators.sma_200 },
  ];
  const available = emaStack.filter(
    (e): e is { label: string; value: number } =>
      typeof e.value === 'number' && Number.isFinite(e.value),
  );
  const above = available.filter((e) => spotPrice > e.value).length;
  const emaReading =
    available.length === 0
      ? '—'
      : above === available.length
        ? 'Spot above stack'
        : above === 0
          ? 'Spot below stack'
          : `Spot mid-stack (${above}/${available.length} above)`;

  return (
    <Card
      title="Indicators"
      meta={spotPrice ? `Spot ${fmtINR(spotPrice)}` : undefined}
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
              <td className="muted">{rsiReading(rsi)}</td>
            </tr>
            <tr>
              <td>ADX (14)</td>
              <td className="r num">{fmtNum(adx, 1)}</td>
              <td className="muted">
                {adx >= 25 ? 'Strong trend' : 'Non-trending'} · +DI {fmtNum(indicators.plus_di, 1)} / -DI{' '}
                {fmtNum(indicators.minus_di, 1)}
              </td>
            </tr>
            <tr>
              <td>Supertrend (10, 3)</td>
              <td className="r num">{fmtINR(indicators.supertrend_value)}</td>
              <td>
                <DirectionBadge direction={indicators.supertrend_direction} />
              </td>
            </tr>
            <tr>
              <td>Bollinger bandwidth</td>
              <td className="r num">{fmtNum(indicators.bollinger_bandwidth, 2)}%</td>
              <td className="muted num">
                Upper {fmtINR(indicators.bollinger_upper)} · Middle {fmtINR(indicators.bollinger_middle)} · Lower{' '}
                {fmtINR(indicators.bollinger_lower)} · %B {fmtNum(indicators.bollinger_pct_b, 2)}
              </td>
            </tr>
            <tr>
              <td>ATR (14)</td>
              <td className="r num">{fmtNum(atr, 1)} pts</td>
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
    </Card>
  );
}
