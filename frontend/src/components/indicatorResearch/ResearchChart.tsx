'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { chartTokens, type ChartTokens } from '@/lib/chartTheme';
import type { PreviewResponse } from '@/lib/api/indicatorResearch';
import { fmt, fmtStamp, prettify } from '@/lib/indicatorResearch';

const PRICE_H = 250;
const PANE_H = 132;
const GAP = 16;
const LEFT = 58;
const RIGHT = 52;
const TOP = 10;
const AXIS_H = 20;

type Series = { name: string; values: Array<number | null>; color: string; dashed?: boolean };

/** ResizeObserver-backed width so the SVG renders 1:1 pixels (no scaled text). */
function useMeasuredWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(960);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(360, node.clientWidth || 960));
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}

function scale(values: Array<number | null>): { min: number; max: number } {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const v of values) {
    if (v === null || v === undefined || !Number.isFinite(v)) continue;
    if (v < min) min = v;
    if (v > max) max = v;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1 };
  if (min === max) return { min: min - 0.5, max: max + 0.5 };
  const pad = (max - min) * 0.06;
  return { min: min - pad, max: max + pad };
}

function pathOf(values: Array<number | null>, x: (i: number) => number, y: (v: number) => number): string {
  let d = '';
  let open = false;
  for (let i = 0; i < values.length; i += 1) {
    const v = values[i];
    if (v === null || v === undefined || !Number.isFinite(v)) {
      open = false;
      continue;
    }
    d += `${open ? 'L' : 'M'}${x(i).toFixed(2)} ${y(v).toFixed(2)} `;
    open = true;
  }
  return d.trim();
}

export function ResearchChart({ preview, height }: { preview: PreviewResponse; height?: number }) {
  const { ref, width } = useMeasuredWidth<HTMLDivElement>();
  const [tokens, setTokens] = useState<ChartTokens>(() => chartTokens());

  useEffect(() => {
    setTokens(chartTokens());
  }, []);

  const candles = preview.candles ?? [];
  const n = candles.length;
  const plotW = Math.max(120, width - LEFT - RIGHT);

  const overlays = useMemo<Series[]>(() => {
    const palette = [tokens.warn, tokens.accent, tokens.up, tokens.down];
    const out: Series[] = [];
    let k = 0;
    for (const info of preview.indicators ?? []) {
      for (const name of info.outputs) {
        const pane = preview.pane_map?.[info.indicator_id]?.outputs?.[name]?.pane;
        if (pane !== 'price') continue;
        const values = preview.outputs?.[name];
        if (!values) continue;
        out.push({ name, values, color: palette[k % palette.length] });
        k += 1;
      }
    }
    return out;
  }, [preview, tokens]);

  const separatePanes = useMemo(() => {
    const palette = [tokens.accent, tokens.warn, tokens.up, tokens.down];
    const groups: Array<{ id: string; title: string; series: Series[] }> = [];
    for (const info of preview.indicators ?? []) {
      const series: Series[] = [];
      let k = 0;
      for (const name of info.outputs) {
        const pane = preview.pane_map?.[info.indicator_id]?.outputs?.[name]?.pane;
        if (pane !== 'separate') continue;
        const values = preview.outputs?.[name];
        if (!values) continue;
        series.push({ name, values, color: palette[k % palette.length] });
        k += 1;
      }
      if (series.length > 0) {
        groups.push({
          id: info.indicator_id,
          title: `${info.name}${series.length > 1 ? ` · ${series.map((s) => prettify(s.name)).join(' / ')}` : ''}`,
          series,
        });
      }
    }
    return groups;
  }, [preview, tokens]);

  const totalH = TOP + PRICE_H + separatePanes.length * (PANE_H + GAP) + AXIS_H;

  const priceSeries = useMemo(() => {
    const values: Array<number | null> = [];
    for (const c of candles) values.push(c.low, c.high);
    for (const s of overlays) values.push(...s.values);
    return values;
  }, [candles, overlays]);

  const price = scale(priceSeries);
  const x = (i: number) => LEFT + (step()) * (i + 0.5);
  const step = () => (n > 0 ? plotW / n : 1);
  const yPrice = (v: number) => TOP + PRICE_H - ((v - price.min) / (price.max - price.min)) * PRICE_H;

  const longSet = useMemo(() => new Set(preview.signals?.long ?? []), [preview.signals]);
  const shortSet = useMemo(() => new Set(preview.signals?.short ?? []), [preview.signals]);

  if (n === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-md border border-border-subtle bg-surface-subtle">
        <p className="sg-note">No bars in this window — widen the date range or lower the warm-up requirement.</p>
      </div>
    );
  }

  const bodyW = Math.max(1, Math.min(10, step() * 0.68));
  const axisTicks = 5;

  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={height ?? totalH}
        viewBox={`0 0 ${width} ${totalH}`}
        role="img"
        aria-label="Price with indicator panes and generated signals"
        style={{ fontFamily: 'var(--ds-mono, monospace)' }}
      >
        {/* price grid */}
        {Array.from({ length: axisTicks + 1 }, (_, i) => {
          const y = TOP + (PRICE_H / axisTicks) * i;
          const value = price.max - ((price.max - price.min) / axisTicks) * i;
          return (
            <g key={`pg-${i}`}>
              <line x1={LEFT} x2={LEFT + plotW} y1={y} y2={y} stroke={tokens.grid} strokeWidth={1} />
              <text x={LEFT - 6} y={y + 3} textAnchor="end" fontSize={9} fill={tokens.text}>
                {fmt(value, 2)}
              </text>
            </g>
          );
        })}

        {/* candles */}
        {candles.map((c, i) => {
          if (c.high === null || c.low === null || c.open === null || c.close === null) return null;
          const up = c.close >= c.open;
          const color = up ? tokens.up : tokens.down;
          const cx = x(i);
          const yd = yPrice(c.open);
          const yc = yPrice(c.close);
          return (
            <g key={`c-${c.index}-${i}`}>
              <line x1={cx} x2={cx} y1={yPrice(c.high)} y2={yPrice(c.low)} stroke={color} strokeWidth={1} />
              <rect
                x={cx - bodyW / 2}
                y={Math.min(yd, yc)}
                width={bodyW}
                height={Math.max(1, Math.abs(yc - yd))}
                fill={up ? tokens.surface : color}
                stroke={color}
                strokeWidth={1}
              />
            </g>
          );
        })}

        {/* overlays */}
        {overlays.map((s) => (
          <path key={s.name} d={pathOf(s.values, x, yPrice)} fill="none" stroke={s.color} strokeWidth={1.4} />
        ))}

        {/* signal markers on price */}
        {candles.map((c, i) =>
          longSet.has(c.index) && c.low !== null ? (
            <polygon
              key={`l-${c.index}`}
              points={`${x(i)},${yPrice(c.low) + 9} ${x(i) - 3.5},${yPrice(c.low) + 15} ${x(i) + 3.5},${yPrice(c.low) + 15}`}
              fill={tokens.up}
            />
          ) : null,
        )}
        {candles.map((c, i) =>
          shortSet.has(c.index) && c.high !== null ? (
            <polygon
              key={`s-${c.index}`}
              points={`${x(i)},${yPrice(c.high) - 9} ${x(i) - 3.5},${yPrice(c.high) - 15} ${x(i) + 3.5},${yPrice(c.high) - 15}`}
              fill={tokens.down}
            />
          ) : null,
        )}

        {/* indicator panes */}
        {separatePanes.map((group, gi) => {
          const top = TOP + PRICE_H + GAP + gi * (PANE_H + GAP);
          const flat: Array<number | null> = [];
          for (const s of group.series) flat.push(...s.values);
          const bounds = scale(flat);
          const y = (v: number) => top + PANE_H - ((v - bounds.min) / (bounds.max - bounds.min)) * PANE_H;
          return (
            <g key={group.id}>
              {Array.from({ length: 3 }, (_, i) => {
                const gy = top + (PANE_H / 2) * i;
                const value = bounds.max - ((bounds.max - bounds.min) / 2) * i;
                return (
                  <g key={`g-${group.id}-${i}`}>
                    <line x1={LEFT} x2={LEFT + plotW} y1={gy} y2={gy} stroke={tokens.grid} strokeWidth={1} />
                    <text x={LEFT - 6} y={gy + 3} textAnchor="end" fontSize={9} fill={tokens.text}>
                      {fmt(value, 2)}
                    </text>
                  </g>
                );
              })}
              {bounds.min < 0 && bounds.max > 0 ? (
                <line x1={LEFT} x2={LEFT + plotW} y1={y(0)} y2={y(0)} stroke={tokens.axis} strokeWidth={1} strokeDasharray="3 3" />
              ) : null}
              <text x={LEFT + 4} y={top - 3} fontSize={9} fill={tokens.text}>
                {group.title}
              </text>
              {group.series.map((s) => (
                <path key={s.name} d={pathOf(s.values, x, y)} fill="none" stroke={s.color} strokeWidth={1.4} />
              ))}
            </g>
          );
        })}

        {/* time axis */}
        <line
          x1={LEFT}
          x2={LEFT + plotW}
          y1={TOP + PRICE_H + separatePanes.length * (PANE_H + GAP)}
          y2={TOP + PRICE_H + separatePanes.length * (PANE_H + GAP)}
          stroke={tokens.axis}
        />
        {Array.from({ length: 6 }, (_, i) => {
          const idx = Math.min(n - 1, Math.round((n - 1) * (i / 5)));
          const cx = x(idx);
          return (
            <text
              key={`t-${i}`}
              x={cx}
              y={TOP + PRICE_H + separatePanes.length * (PANE_H + GAP) + 12}
              textAnchor={i === 0 ? 'start' : i === 5 ? 'end' : 'middle'}
              fontSize={9}
              fill={tokens.text}
            >
              {fmtStamp(candles[idx]?.time ?? null, i === 0)}
            </text>
          );
        })}
      </svg>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        {[...overlays, ...separatePanes.flatMap((g) => g.series)].map((s) => (
          <span key={`lg-${s.name}`} className="flex items-center gap-1 text-[10px] text-ink-3">
            <span className="inline-block h-0.5 w-4 rounded-sm" style={{ background: s.color }} />
            {prettify(s.name)}
          </span>
        ))}
        {longSet.size > 0 ? (
          <span className="flex items-center gap-1 text-[10px] text-up-strong">
            <span className="inline-block h-0 w-0 border-x-4 border-b-[6px] border-x-transparent" style={{ borderBottomColor: tokens.up }} />
            {longSet.size} long signal{longSet.size === 1 ? '' : 's'}
          </span>
        ) : null}
        {shortSet.size > 0 ? (
          <span className="flex items-center gap-1 text-[10px] text-down-strong">
            <span className="inline-block h-0 w-0 border-x-4 border-t-[6px] border-x-transparent" style={{ borderTopColor: tokens.down }} />
            {shortSet.size} short signal{shortSet.size === 1 ? '' : 's'}
          </span>
        ) : null}
      </div>
    </div>
  );
}
