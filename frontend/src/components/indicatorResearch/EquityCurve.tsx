'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { chartTokens, type ChartTokens } from '@/lib/chartTheme';
import type { EquityPoint } from '@/lib/api/indicatorResearch';
import { fmt, fmtMoney, fmtStamp } from '@/lib/indicatorResearch';

const H = 190;
const DD_H = 74;
const GAP = 18;
const LEFT = 62;
const RIGHT = 46;
const TOP = 8;
const AXIS_H = 18;

function useMeasuredWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(900);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(320, node.clientWidth || 900));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}

export function EquityCurve({
  points,
  initialCapital,
  thinned,
}: {
  points: EquityPoint[];
  initialCapital: number | null;
  thinned?: { original_points: number; returned_points: number; step: number } | null;
}) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  const [tokens, setTokens] = useState<ChartTokens>(() => chartTokens());
  useEffect(() => setTokens(chartTokens()), []);

  const totalH = TOP + H + GAP + DD_H + AXIS_H;
  const plotW = Math.max(120, width - LEFT - RIGHT);

  const bounds = useMemo(() => {
    let min = Number.POSITIVE_INFINITY;
    let max = Number.NEGATIVE_INFINITY;
    for (const p of points) {
      if (!Number.isFinite(p.equity)) continue;
      min = Math.min(min, p.equity);
      max = Math.max(max, p.equity);
    }
    if (initialCapital !== null && Number.isFinite(initialCapital)) {
      min = Math.min(min, initialCapital);
      max = Math.max(max, initialCapital);
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1, ddMax: 1 };
    if (min === max) {
      min -= 1;
      max += 1;
    }
    let ddMax = 1;
    for (const p of points) ddMax = Math.max(ddMax, Math.abs(p.drawdown_pct ?? 0));
    return { min, max, ddMax };
  }, [points, initialCapital]);

  if (points.length < 2) {
    return (
      <div className="flex h-32 items-center justify-center rounded-md border border-border-subtle bg-surface-subtle">
        <p className="sg-note">No closed trades, so there is no equity path to plot.</p>
      </div>
    );
  }

  const n = points.length;
  const step = plotW / (n - 1);
  const x = (i: number) => LEFT + i * step;
  const y = (v: number) => TOP + H - ((v - bounds.min) / (bounds.max - bounds.min)) * H;
  const yDd = (v: number) => TOP + H + GAP + (Math.abs(v) / (bounds.ddMax || 1)) * DD_H;

  const equityPath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(2)} ${y(p.equity).toFixed(2)}`).join(' ');
  const ddPath =
    `M${x(0).toFixed(2)} ${yDd(0).toFixed(2)} ` +
    points.map((p, i) => `L${x(i).toFixed(2)} ${yDd(p.drawdown_pct ?? 0).toFixed(2)}`).join(' ') +
    ` L${x(n - 1).toFixed(2)} ${yDd(0).toFixed(2)} Z`;

  const peakIdx = points.reduce((best, p, i) => (p.equity > points[best].equity ? i : best), 0);
  const troughIdx = points.reduce((worst, p, i) => (p.equity < points[worst].equity ? i : worst), 0);

  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={totalH}
        viewBox={`0 0 ${width} ${totalH}`}
        role="img"
        aria-label="Equity curve and drawdown"
        style={{ fontFamily: 'var(--ds-mono, monospace)' }}
      >
        {Array.from({ length: 4 }, (_, i) => {
          const gy = TOP + (H / 3) * i;
          const value = bounds.max - ((bounds.max - bounds.min) / 3) * i;
          return (
            <g key={`eg-${i}`}>
              <line x1={LEFT} x2={LEFT + plotW} y1={gy} y2={gy} stroke={tokens.grid} strokeWidth={1} />
              <text x={LEFT - 6} y={gy + 3} textAnchor="end" fontSize={9} fill={tokens.text}>
                {fmtCompactRupees(value)}
              </text>
            </g>
          );
        })}

        {initialCapital !== null ? (
          <g>
            <line
              x1={LEFT}
              x2={LEFT + plotW}
              y1={y(initialCapital)}
              y2={y(initialCapital)}
              stroke={tokens.text}
              strokeDasharray="4 4"
              strokeWidth={1}
            />
            <text x={LEFT + plotW - 2} y={y(initialCapital) - 3} textAnchor="end" fontSize={9} fill={tokens.text}>
              start {fmtCompactRupees(initialCapital)}
            </text>
          </g>
        ) : null}

        <path d={equityPath} fill="none" stroke={tokens.accent} strokeWidth={1.6} />

        <circle cx={x(peakIdx)} cy={y(points[peakIdx].equity)} r={2.6} fill={tokens.up} />
        <circle cx={x(troughIdx)} cy={y(points[troughIdx].equity)} r={2.6} fill={tokens.down} />

        {/* drawdown pane */}
        <line x1={LEFT} x2={LEFT + plotW} y1={TOP + H + GAP} y2={TOP + H + GAP} stroke={tokens.axis} />
        <text x={LEFT + 2} y={TOP + H + GAP} fontSize={9} fill={tokens.text}>
          drawdown %
        </text>
        <path d={ddPath} fill={tokens.down} opacity={0.18} stroke={tokens.down} strokeWidth={1} />

        <line x1={LEFT} x2={LEFT + plotW} y1={TOP + H + GAP + DD_H} y2={TOP + H + GAP + DD_H} stroke={tokens.axis} />
        {Array.from({ length: 5 }, (_, i) => {
          const idx = Math.round((n - 1) * (i / 4));
          return (
            <text
              key={`et-${i}`}
              x={x(idx)}
              y={TOP + H + GAP + DD_H + 12}
              textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}
              fontSize={9}
              fill={tokens.text}
            >
              {fmtStamp(points[idx]?.time ?? null, i === 0)}
            </text>
          );
        })}
      </svg>

      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-3">
        <span>
          peak {fmtMoney(points[peakIdx].equity)} @ {fmtStamp(points[peakIdx].time)}
        </span>
        <span>
          trough {fmtMoney(points[troughIdx].equity)} @ {fmtStamp(points[troughIdx].time)}
        </span>
        <span>max DD {fmt(bounds.ddMax, 2)}%</span>
        {thinned ? (
          <span title="The equity path was down-sampled for transport; trades and metrics use every bar.">
            plotted {thinned.returned_points}/{thinned.original_points} points (1 per {thinned.step} bars)
          </span>
        ) : null}
      </div>
    </div>
  );
}

function fmtCompactRupees(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  if (abs >= 1e3) return `${sign}₹${(abs / 1e3).toFixed(1)}K`;
  return `${sign}₹${abs.toFixed(0)}`;
}
