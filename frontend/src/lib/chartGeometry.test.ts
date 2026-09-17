import { describe, expect, it } from 'vitest';
import {
  linearScale,
  pathFromPoints,
  plotBox,
  polylinePoints,
  tickIndices,
} from './chartGeometry';

describe('plotBox', () => {
  it('derives plot metrics from the viewBox and padding', () => {
    expect(plotBox(640, 240, { top: 16, right: 14, bottom: 36, left: 54 })).toEqual({
      plotWidth: 572,
      plotHeight: 188,
      baseY: 204,
      rightEdge: 626,
    });
    expect(plotBox(500, 100, { top: 12, right: 0, bottom: 12, left: 0 })).toEqual({
      plotWidth: 500,
      plotHeight: 76,
      baseY: 88,
      rightEdge: 500,
    });
  });
});

describe('linearScale', () => {
  it('maps a domain onto a range and supports inverted ranges', () => {
    expect(linearScale([0, 10], [0, 100])(2.5)).toBe(25);
    expect(linearScale([10, 0], [0, 100])(2.5)).toBe(75);
    expect(linearScale([100, 200], [0, 50])(150)).toBe(25);
    expect(linearScale([0, 10], [20, 40])(0)).toBe(20);
    expect(linearScale([0, 10], [20, 40])(10)).toBe(40);
  });

  it('falls back to a span of 1 for a zero-width domain', () => {
    expect(linearScale([5, 5], [0, 10])(7)).toBe(20);
  });
});

describe('pathFromPoints', () => {
  it('renders M/L segments with one-decimal coordinates', () => {
    expect(pathFromPoints([])).toBe('');
    expect(pathFromPoints([{ x: 1.234, y: -5.678 }])).toBe('M 1.2 -5.7');
    expect(
      pathFromPoints([
        { x: 1.234, y: -5.678 },
        { x: 9.012, y: 3.456 },
      ]),
    ).toBe('M 1.2 -5.7 L 9.0 3.5');
  });
});

describe('polylinePoints', () => {
  it('renders comma-separated one-decimal pairs', () => {
    expect(polylinePoints([])).toBe('');
    expect(polylinePoints([{ x: 1.234, y: -5.678 }, { x: 9.012, y: 3.456 }])).toBe(
      '1.2,-5.7 9.0,3.5',
    );
  });
});

describe('tickIndices', () => {
  it('spreads at most five evenly spaced, de-duplicated indices', () => {
    expect(tickIndices(0)).toEqual([]);
    expect(tickIndices(1)).toEqual([0]);
    expect(tickIndices(2)).toEqual([0, 1]);
    expect(tickIndices(3)).toEqual([0, 1, 2]);
    expect(tickIndices(6)).toEqual([0, 1, 3, 4, 5]);
    expect(tickIndices(7)).toEqual([0, 2, 3, 5, 6]);
    expect(tickIndices(10, 3)).toEqual([0, 5, 9]);
  });
});
