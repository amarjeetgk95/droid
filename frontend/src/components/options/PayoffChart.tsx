'use client';

import { Card, EmptyNote, fmtINR } from '@/components/ui/desk';
import { chartTokens } from '@/lib/chartTheme';
import type { MaxPainResult } from '@/lib/types';

const W = 640;
const H = 240;
const PAD = { top: 16, right: 14, bottom: 36, left: 54 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

export function fmtCompactINR(v: number | null | undefined): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  if (abs >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return fmtINR(v);
}

export function PayoffChart({
  data,
  spotPrice,
}: {
  data: MaxPainResult | null;
  spotPrice: number;
}) {
  if (!data || data.strikes.length === 0) {
    return (
      <Card title="Max pain payout" meta="—">
        <EmptyNote>No Max Pain payout distribution available for this expiry.</EmptyNote>
      </Card>
    );
  }

  const series = data.strikes
    .map((strike, i) => ({ strike, payout: data.payouts[i] }))
    .filter((p): p is { strike: number; payout: number } =>
      typeof p.payout === 'number' && Number.isFinite(p.payout),
    );

  if (series.length === 0) {
    return (
      <Card title="Max pain payout" meta="—">
        <EmptyNote>The payout distribution came back empty — no curve can be drawn.</EmptyNote>
      </Card>
    );
  }

  const tokens = chartTokens();
  const sMin = series[0].strike;
  const sMax = series[series.length - 1].strike;
  const strikeSpan = sMax - sMin || 1;
  const maxPayout = Math.max(...series.map((p) => p.payout), 1);
  const base = H - PAD.bottom;

  const x = (strike: number) => PAD.left + ((strike - sMin) / strikeSpan) * PLOT_W;
  const y = (payout: number) => base - (Math.max(0, payout) / maxPayout) * PLOT_H;

  const line = series
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.strike).toFixed(1)} ${y(p.payout).toFixed(1)}`)
    .join(' ');
  const area = `M ${x(sMin).toFixed(1)} ${base} ${line.slice(1)} L ${x(sMax).toFixed(1)} ${base} Z`;

  const yTicks = [0, maxPayout / 2, maxPayout];
  const tickCount = Math.min(5, series.length);
  const xTickIdx = Array.from(
    new Set(
      Array.from({ length: tickCount }, (_, i) =>
        Math.round((i * (series.length - 1)) / Math.max(1, tickCount - 1)),
      ),
    ),
  );

  const maxPainInRange = data.max_pain_strike >= sMin && data.max_pain_strike <= sMax;
  const spotInRange = spotPrice >= sMin && spotPrice <= sMax;
  const peak = series.reduce((best, p) => (p.payout > best.payout ? p : best), series[0]);

  const summary =
    `Max pain payout curve across ${series.length} strikes from ${sMin.toLocaleString('en-IN')} to ` +
    `${sMax.toLocaleString('en-IN')}. Maximum payout ${fmtCompactINR(peak.payout)} at strike ` +
    `${peak.strike.toLocaleString('en-IN')}. Minimum total payout ${fmtCompactINR(data.total_loss_at_max_pain)} ` +
    `at the max pain strike ${data.max_pain_strike.toLocaleString('en-IN')}.` +
    (spotPrice > 0 ? ` Spot ${fmtINR(spotPrice)}.` : '');

  return (
    <Card
      title="Max pain payout"
      meta={`Max pain ${fmtINR(data.max_pain_strike)} · min payout ${fmtCompactINR(data.total_loss_at_max_pain)}`}
    >
      <figure style={{ margin: 0 }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={summary}
          tabIndex={0}
          style={{ width: '100%', height: 224, display: 'block' }}
          preserveAspectRatio="xMidYMid meet"
        >
          <title>{summary}</title>

          {yTicks.map((tick) => (
            <g key={`y-${tick}`}>
              <line
                x1={PAD.left}
                x2={W - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
                stroke={tokens.grid}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              <text x={PAD.left - 6} y={y(tick) + 3} textAnchor="end" fontSize={10} fill={tokens.text}>
                {fmtCompactINR(tick)}
              </text>
            </g>
          ))}

          {xTickIdx.map((idx) => (
            <text
              key={`x-${idx}`}
              x={x(series[idx].strike)}
              y={H - PAD.bottom + 14}
              textAnchor="middle"
              fontSize={10}
              fill={tokens.text}
            >
              {series[idx].strike.toLocaleString('en-IN')}
            </text>
          ))}
          <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize={10} fill={tokens.text}>
            Strike
          </text>
          <text x={4} y={11} fontSize={10} fill={tokens.text}>
            Payout
          </text>

          <path d={area} fill={tokens.accent} opacity={0.12} stroke="none" />
          <path
            d={line}
            fill="none"
            stroke={tokens.accent}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />

          {spotInRange && (
            <g>
              <line
                x1={x(spotPrice)}
                x2={x(spotPrice)}
                y1={PAD.top}
                y2={base}
                stroke={tokens.crosshair}
                strokeWidth={1}
                strokeDasharray="3 3"
                vectorEffect="non-scaling-stroke"
              />
              <text x={x(spotPrice)} y={PAD.top - 4} textAnchor="middle" fontSize={9} fill={tokens.text}>
                Spot
              </text>
            </g>
          )}
          {maxPainInRange && (
            <g>
              <line
                x1={x(data.max_pain_strike)}
                x2={x(data.max_pain_strike)}
                y1={PAD.top}
                y2={base}
                stroke={tokens.warn}
                strokeWidth={1.5}
                vectorEffect="non-scaling-stroke"
              />
              <circle cx={x(data.max_pain_strike)} cy={y(data.total_loss_at_max_pain)} r={3.5} fill={tokens.warn}>
                <title>{`Max pain ${data.max_pain_strike.toLocaleString('en-IN')}`}</title>
              </circle>
            </g>
          )}
        </svg>
        <figcaption className="sr-only">{summary}</figcaption>
      </figure>

      <div className="toolbar" style={{ marginTop: 8 }}>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: tokens.warn, marginRight: 5 }} />
          Max pain strike
        </span>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 2, background: tokens.accent, marginRight: 5 }} />
          Total payout to option buyers
        </span>
        <span className="spacer" />
        <span className="faint" style={{ fontSize: 11 }}>Total option loss minimization model</span>
      </div>
    </Card>
  );
}
