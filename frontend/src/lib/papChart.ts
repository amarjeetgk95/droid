import type { ChartTokens } from './chartTheme';
import type { PapPrediction } from './api/pap';

export type PapCandle = { time: number; open: number; high: number; low: number; close: number };

export type PapChartMarker = {
  time: number;
  prediction: PapPrediction | null;
  horizon: string | null;
  p_up: number;
  p_neutral: number;
  p_down: number;
  actual: PapPrediction | null;
  correct: boolean | null;
  price_change_pct: number | null;
  confidence: number;
};

export type ChartMarker = {
  time: number;
  position: 'aboveBar' | 'belowBar' | 'inBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle';
  text: string;
};

/** Prediction -> marker geometry. Shape carries direction, colour carries outcome. */
export function toChartMarkers(markers: PapChartMarker[], tokens: ChartTokens): ChartMarker[] {
  return markers
    .filter((m) => m.prediction === 'UP' || m.prediction === 'DOWN' || m.prediction === 'NEUTRAL')
    .map((m) => {
      const color = m.correct === true ? tokens.up : m.correct === false ? tokens.down : tokens.warn;
      if (m.prediction === 'UP') {
        return { time: m.time, position: 'belowBar' as const, color, shape: 'arrowUp' as const, text: `UP ${m.p_up}%` };
      }
      if (m.prediction === 'DOWN') {
        return { time: m.time, position: 'aboveBar' as const, color, shape: 'arrowDown' as const, text: `DOWN ${m.p_down}%` };
      }
      return { time: m.time, position: 'inBar' as const, color, shape: 'circle' as const, text: `NEU ${m.p_neutral}%` };
    });
}

/** Detail card lines for a clicked marker — null when nothing is selected. */
export function markerDetail(m: PapChartMarker | null): {
  title: string;
  rows: Array<[string, string]>;
  correct: boolean | null;
} | null {
  if (!m) return null;
  const pct = (v: number) => `${v}%`;
  const signed = (v: number | null) => (v === null ? '—' : `${v >= 0 ? '+' : ''}${v}%`);
  return {
    title: `Prediction: ${m.prediction ?? '—'}`,
    rows: [
      ['Horizon', m.horizon ?? '—'],
      ['P(UP)', pct(m.p_up)],
      ['P(Neutral)', pct(m.p_neutral)],
      ['P(DOWN)', pct(m.p_down)],
      ['Actual return', signed(m.price_change_pct)],
      ['Result', m.correct === null ? 'PENDING' : m.correct ? 'CORRECT' : 'INCORRECT'],
    ],
    correct: m.correct,
  };
}
