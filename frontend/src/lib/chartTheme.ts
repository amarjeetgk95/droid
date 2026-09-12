/**
 * Centralized Kite-inspired financial chart theme constants.
 * Use these across Lightweight Charts, SVG payoff/IV diagrams, and technical indicators.
 */
export const KITE_CHART_THEME = {
  bullish: '#4caf50',
  bearish: '#df514c',
  primary: '#387ed1',
  accent: '#387ed1',
  actionSell: '#eb5b3c',
  grid: '#f0f0f0',
  border: '#e0e0e0',
  text: '#666666',
  textFaint: '#9b9b9b',
  surface: '#ffffff',
  background: '#fbfbfb',
  atmStrike: '#f59e0b',
  volumeCall: '#387ed1',
  volumePut: '#eb5b3c',
} as const;

export type KiteChartTheme = typeof KITE_CHART_THEME;
