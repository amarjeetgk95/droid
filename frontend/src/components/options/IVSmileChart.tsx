'use client';

import { useMemo } from 'react';
import { Card, EmptyNote, fmtNum } from '@/components/ui/desk';
import { chartTokens } from '@/lib/chartTheme';
import type { OptionChainStrikeRow } from '@/lib/types';

interface IvPoint {
  strike: number;
  ce: number | null;
  pe: number | null;
  isAtm: boolean;
}

interface Point {
  x: number;
  y: number;
}

const W = 640;
const H = 240;
const PAD = { top: 16, right: 14, bottom: 36, left: 46 };
const PLOT_W = W - PAD.left - PAD.right;
const PLOT_H = H - PAD.top - PAD.bottom;

function ivOf(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : null;
}

function pathThrough(pts: Point[]): string {
  if (pts.length === 0) return '';
  return pts
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ');
}

export function IVSmileChart({
  strikes,
  atmStrike,
}: {
  strikes: OptionChainStrikeRow[];
  atmStrike: number;
}) {
  const points = useMemo<IvPoint[]>(
    () =>
      (strikes ?? [])
        .map((s) => ({
          strike: s.strike,
          ce: ivOf(s.call?.greeks?.iv),
          pe: ivOf(s.put?.greeks?.iv),
          isAtm: s.is_atm,
        }))
        .filter((p) => p.ce !== null || p.pe !== null)
        .sort((a, b) => a.strike - b.strike),
    [strikes],
  );

  if (points.length === 0) {
    return (
      <Card title="IV smile & skew" meta="unavailable">
        <EmptyNote>
          No solvable implied volatilities for this expiry — the broker chain published no priced
          contracts, so no smile is drawn.
        </EmptyNote>
      </Card>
    );
  }

  const tokens = chartTokens();
  const sMin = points[0].strike;
  const sMax = points[points.length - 1].strike;
  const strikeSpan = sMax - sMin || 1;

  const ivs: number[] = [];
  for (const p of points) {
    if (p.ce !== null) ivs.push(p.ce);
    if (p.pe !== null) ivs.push(p.pe);
  }
  const minIv = Math.min(...ivs);
  const maxIv = Math.max(...ivs);
  const yMin = Math.max(0, Math.floor(minIv - 1));
  const yMaxRaw = Math.ceil(maxIv + 1);
  const yMax = yMaxRaw > yMin ? yMaxRaw : yMin + 1;

  const x = (strike: number) => PAD.left + ((strike - sMin) / strikeSpan) * PLOT_W;
  const y = (iv: number) => H - PAD.bottom - ((iv - yMin) / (yMax - yMin)) * PLOT_H;

  const cePts = points.filter((p) => p.ce !== null).map((p) => ({ x: x(p.strike), y: y(p.ce as number) }));
  const pePts = points.filter((p) => p.pe !== null).map((p) => ({ x: x(p.strike), y: y(p.pe as number) }));

  const yTicks = [yMin, (yMin + yMax) / 2, yMax];
  const tickCount = Math.min(5, points.length);
  const xTickIdx = Array.from(
    new Set(
      Array.from({ length: tickCount }, (_, i) =>
        Math.round((i * (points.length - 1)) / Math.max(1, tickCount - 1)),
      ),
    ),
  );

  const ceVals = points.map((p) => p.ce).filter((v): v is number => v !== null);
  const peVals = points.map((p) => p.pe).filter((v): v is number => v !== null);
  const atmPoint = points.find((p) => p.strike === atmStrike) ?? points.find((p) => p.isAtm);
  const atmLine = atmStrike >= sMin && atmStrike <= sMax ? x(atmStrike) : null;

  const summary =
    `IV smile and skew across ${points.length} strikes from ${sMin.toLocaleString('en-IN')} to ` +
    `${sMax.toLocaleString('en-IN')}. ` +
    (ceVals.length > 0
      ? `Call IV ${fmtNum(Math.min(...ceVals), 1)}% to ${fmtNum(Math.max(...ceVals), 1)}%. `
      : 'Call IV unavailable. ') +
    (peVals.length > 0
      ? `Put IV ${fmtNum(Math.min(...peVals), 1)}% to ${fmtNum(Math.max(...peVals), 1)}%.`
      : 'Put IV unavailable.') +
    (atmPoint
      ? ` ATM ${atmPoint.strike.toLocaleString('en-IN')}: call IV ${
          atmPoint.ce !== null ? `${fmtNum(atmPoint.ce, 1)}%` : 'unavailable'
        }, put IV ${atmPoint.pe !== null ? `${fmtNum(atmPoint.pe, 1)}%` : 'unavailable'}.`
      : '');

  return (
    <Card title="IV smile & skew" meta={`ATM ${atmStrike.toLocaleString('en-IN')} · IV ${fmtNum(minIv, 1)}%–${fmtNum(maxIv, 1)}%`}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={summary}
        tabIndex={0}
        style={{ width: '100%', height: 224, display: 'block' }}
        preserveAspectRatio="xMidYMid meet"
      >
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
              {fmtNum(tick, 1)}%
            </text>
          </g>
        ))}

        {xTickIdx.map((idx) => (
          <text
            key={`x-${idx}`}
            x={x(points[idx].strike)}
            y={H - PAD.bottom + 14}
            textAnchor="middle"
            fontSize={10}
            fill={tokens.text}
          >
            {points[idx].strike.toLocaleString('en-IN')}
          </text>
        ))}
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize={10} fill={tokens.text}>
          Strike
        </text>
        <text x={4} y={11} fontSize={10} fill={tokens.text}>
          IV %
        </text>

        {atmLine !== null && (
          <g>
            <line
              x1={atmLine}
              x2={atmLine}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke={tokens.crosshair}
              strokeWidth={1}
              strokeDasharray="3 3"
              vectorEffect="non-scaling-stroke"
            />
            <text x={atmLine} y={PAD.top - 4} textAnchor="middle" fontSize={9} fill={tokens.text}>
              ATM
            </text>
          </g>
        )}

        {cePts.length > 0 && (
          <path
            d={pathThrough(cePts)}
            fill="none"
            stroke={tokens.accent}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        )}
        {pePts.length > 0 && (
          <path
            d={pathThrough(pePts)}
            fill="none"
            stroke={tokens.warn}
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
          />
        )}

        {points.map((p) =>
          p.ce !== null ? (
            <circle key={`ce-${p.strike}`} cx={x(p.strike)} cy={y(p.ce)} r={3} fill={tokens.accent}>
              <title>{`${p.strike.toLocaleString('en-IN')} CE · IV ${fmtNum(p.ce, 1)}%`}</title>
            </circle>
          ) : null,
        )}
        {points.map((p) =>
          p.pe !== null ? (
            <circle key={`pe-${p.strike}`} cx={x(p.strike)} cy={y(p.pe)} r={3} fill={tokens.warn}>
              <title>{`${p.strike.toLocaleString('en-IN')} PE · IV ${fmtNum(p.pe, 1)}%`}</title>
            </circle>
          ) : null,
        )}
      </svg>

      <div className="toolbar" style={{ marginTop: 8 }}>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: tokens.accent, marginRight: 5 }} />
          Call IV (CE)
        </span>
        <span className="faint" style={{ fontSize: 11 }}>
          <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 999, background: tokens.warn, marginRight: 5 }} />
          Put IV (PE)
        </span>
        <span className="spacer" />
        <span className="faint num" style={{ fontSize: 11 }}>
          ATM {atmStrike.toLocaleString('en-IN')}
        </span>
      </div>
    </Card>
  );
}
