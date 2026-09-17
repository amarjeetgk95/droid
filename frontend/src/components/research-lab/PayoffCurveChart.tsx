'use client';

import React, { useMemo } from 'react';
import { EmptyNote, fmtINR } from '@/components/ui/desk';
import { chartTokens } from '@/lib/chartTheme';
import { computePayoffStats, splitPayoffBySign, type PayoffPoint } from './contracts';

export interface PayoffCurveChartProps {
  points: PayoffPoint[];
  spotPrice?: number | null;
  maxProfit?: number | 'unlimited' | null;
  maxLoss?: number | 'unlimited' | null;
  breakevens?: number[] | null;
  riskRewardRatio?: number | null;
  premiumNote?: string | null;
}

const W = 640;
const H = 220;
const PAD = { top: 16, right: 14, bottom: 30, left: 64 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function compactINR(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '+';
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)} L`;
  return `${sign}₹${abs.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

function money(value: number | 'unlimited' | null | undefined): string {
  if (value === 'unlimited') return 'unlimited';
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return fmtINR(value);
}

export const PayoffCurveChart: React.FC<PayoffCurveChartProps> = ({
  points,
  spotPrice = null,
  maxProfit = null,
  maxLoss = null,
  breakevens = null,
  riskRewardRatio = null,
  premiumNote = null,
}) => {
  const stats = useMemo(() => computePayoffStats(points), [points]);
  const tokens = chartTokens();

  const breakevenList = useMemo(() => {
    if (breakevens && breakevens.length > 0) return breakevens;
    return stats?.breakevens ?? [];
  }, [breakevens, stats]);

  if (!stats) {
    return (
      <div className="rounded border border-border bg-surface-subtle p-4">
        <EmptyNote>
          No payoff curve in scope. Build a strategy from a live template to plot real points.
        </EmptyNote>
      </div>
    );
  }

  const yAbs = Math.max(Math.abs(stats.maxProfit), Math.abs(stats.maxLoss), 1);
  const x = (spot: number) =>
    PAD.left + ((spot - stats.spotMin) / (stats.spotMax - stats.spotMin || 1)) * PLOT_W;
  const y = (pnl: number) => PAD.top + (1 - (pnl + yAbs) / (2 * yAbs)) * PLOT_H;

  const segments = splitPayoffBySign(points);
  const pathFor = (segment: PayoffPoint[]) =>
    segment
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.spot).toFixed(1)} ${y(p.pnl).toFixed(1)}`)
      .join(' ');

  const spotInRange = spotPrice !== null && spotPrice >= stats.spotMin && spotPrice <= stats.spotMax;
  const yTicks = Array.from(new Set([stats.maxProfit, 0, stats.maxLoss]));
  const summary =
    `Expiry payoff across ${stats.count} sampled spots from ${stats.spotMin.toLocaleString('en-IN')} to ` +
    `${stats.spotMax.toLocaleString('en-IN')}. Maximum profit within the sampled range ${compactINR(stats.maxProfit)}, ` +
    `maximum loss ${compactINR(stats.maxLoss)}.` +
    (breakevenList.length > 0
      ? ` Breakevens ${breakevenList.map((b) => b.toLocaleString('en-IN')).join(', ')}.`
      : ' No breakeven inside the sampled range.') +
    (spotPrice !== null ? ` Spot ${fmtINR(spotPrice)}.` : '');

  return (
    <div className="rounded border border-border bg-surface p-3 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-ink">Expiry payoff profile</span>
        <span className="badge b-info">
          R:R {riskRewardRatio === null ? '—' : `1:${riskRewardRatio.toFixed(2)}`}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        <div className="rounded border border-border-subtle bg-surface-subtle p-2">
          <div className="text-[10px] uppercase text-ink-3">Max profit</div>
          <div className="num text-sm font-semibold text-up-strong mt-0.5">
            {maxProfit !== null ? money(maxProfit) : compactINR(stats.maxProfit)}
          </div>
        </div>
        <div className="rounded border border-border-subtle bg-surface-subtle p-2">
          <div className="text-[10px] uppercase text-ink-3">Max loss</div>
          <div className="num text-sm font-semibold text-down-strong mt-0.5">
            {maxLoss !== null ? money(maxLoss) : compactINR(stats.maxLoss)}
          </div>
        </div>
        <div className="rounded border border-border-subtle bg-surface-subtle p-2">
          <div className="text-[10px] uppercase text-ink-3">Breakeven(s)</div>
          <div className="num text-sm font-semibold text-ink mt-0.5">
            {breakevenList.length === 0
              ? '—'
              : breakevenList.map((b) => b.toLocaleString('en-IN')).join(', ')}
          </div>
        </div>
        <div className="rounded border border-border-subtle bg-surface-subtle p-2">
          <div className="text-[10px] uppercase text-ink-3">Sampled spots</div>
          <div className="num text-sm font-semibold text-ink mt-0.5">
            {stats.spotMin.toLocaleString('en-IN')}–{stats.spotMax.toLocaleString('en-IN')}
          </div>
        </div>
      </div>

      <figure style={{ margin: 0 }}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label={summary}
          tabIndex={0}
          style={{ width: '100%', height: 220, display: 'block' }}
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
                stroke={tick === 0 ? tokens.axis : tokens.grid}
                strokeDasharray={tick === 0 ? '4 4' : undefined}
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              <text x={PAD.left - 6} y={y(tick) + 3} textAnchor="end" fontSize={10} fill={tokens.text}>
                {compactINR(tick)}
              </text>
            </g>
          ))}

          <text x={PAD.left} y={H - 8} fontSize={10} fill={tokens.text}>
            {stats.spotMin.toLocaleString('en-IN')}
          </text>
          <text x={W - PAD.right} y={H - 8} textAnchor="end" fontSize={10} fill={tokens.text}>
            {stats.spotMax.toLocaleString('en-IN')}
          </text>

          {segments.map((segment, index) => (
            <path
              key={`seg-${index}`}
              d={pathFor(segment.points)}
              fill="none"
              stroke={segment.sign === 1 ? tokens.up : tokens.down}
              strokeWidth={2}
              vectorEffect="non-scaling-stroke"
            />
          ))}

          {breakevenList
            .filter((b) => b >= stats.spotMin && b <= stats.spotMax)
            .map((b) => (
              <g key={`be-${b}`}>
                <line
                  x1={x(b)}
                  x2={x(b)}
                  y1={PAD.top}
                  y2={H - PAD.bottom}
                  stroke={tokens.warn}
                  strokeDasharray="3 3"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
                <text x={x(b)} y={PAD.top - 4} textAnchor="middle" fontSize={9} fill={tokens.text}>
                  BE
                </text>
              </g>
            ))}

          {spotInRange ? (
            <g>
              <line
                x1={x(spotPrice as number)}
                x2={x(spotPrice as number)}
                y1={PAD.top}
                y2={H - PAD.bottom}
                stroke={tokens.accent}
                strokeWidth={1}
                strokeDasharray="2 2"
                vectorEffect="non-scaling-stroke"
              />
              <text
                x={x(spotPrice as number)}
                y={H - PAD.bottom + 12}
                textAnchor="middle"
                fontSize={9}
                fill={tokens.text}
              >
                Spot
              </text>
            </g>
          ) : null}
        </svg>
        <figcaption className="sr-only">{summary}</figcaption>
      </figure>

      <div className="flex flex-wrap items-center gap-3 faint text-[11px]">
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden
            style={{ display: 'inline-block', width: 10, height: 3, background: tokens.up }}
          />
          Profit above zero
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden
            style={{ display: 'inline-block', width: 10, height: 3, background: tokens.down }}
          />
          Loss below zero
        </span>
        <span className="inline-flex items-center gap-1.5">
          <i
            aria-hidden
            style={{ display: 'inline-block', width: 10, height: 3, background: tokens.warn }}
          />
          Breakeven
        </span>
        {premiumNote ? <span className="text-warn-ink">{premiumNote}</span> : null}
      </div>
    </div>
  );
};
