/**
 * Framework-agnostic SVG chart geometry shared by the hand-rolled chart
 * components (risk-matrix, options, research-lab).
 *
 * The path/point builders intentionally pin one-decimal coordinates and the
 * exact `M`/`L`/comma separators the components used inline, so swapping the
 * inline math for these helpers is byte-stable in the rendered SVG.
 */

export interface ChartPoint {
  x: number;
  y: number;
}

export interface ChartPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface PlotBox {
  /** width - left - right */
  plotWidth: number;
  /** height - top - bottom */
  plotHeight: number;
  /** height - bottom; the chart baseline / zero-line anchor */
  baseY: number;
  /** width - right; right edge of the plot area */
  rightEdge: number;
}

export type Scale = (value: number) => number;

/** Plot-area metrics for a padded SVG viewBox. */
export function plotBox(width: number, height: number, pad: ChartPadding): PlotBox {
  return {
    plotWidth: width - pad.left - pad.right,
    plotHeight: height - pad.top - pad.bottom,
    baseY: height - pad.bottom,
    rightEdge: width - pad.right,
  };
}

/**
 * Linear scale: `range[0] + ((value - domain[0]) / span) * (range[1] - range[0])`.
 * A zero-width domain falls back to span 1 so a flat series cannot divide by zero.
 */
export function linearScale(
  domain: readonly [number, number],
  range: readonly [number, number],
): Scale {
  const d0 = domain[0];
  const span = domain[1] - d0 || 1;
  const r0 = range[0];
  const length = range[1] - r0;
  return (value: number) => r0 + ((value - d0) / span) * length;
}

/** `M x y L x y …` with one-decimal coordinates, joined by spaces. */
export function pathFromPoints(points: readonly ChartPoint[]): string {
  return points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    .join(' ');
}

/** `x,y x,y …` polyline points with one-decimal coordinates. */
export function polylinePoints(points: readonly ChartPoint[]): string {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}

/** Evenly spaced, de-duplicated index ticks (at most `maxTicks`, default 5). */
export function tickIndices(length: number, maxTicks = 5): number[] {
  const count = Math.min(maxTicks, length);
  return Array.from(
    new Set(
      Array.from({ length: count }, (_, i) =>
        Math.round((i * (length - 1)) / Math.max(1, count - 1)),
      ),
    ),
  );
}
