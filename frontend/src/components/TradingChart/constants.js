export const COLORS = {
  bg: '#131722',
  grid: '#1e222d',
  axis: '#2a2e39',
  text: '#787b86',
  up: '#26a69a',
  down: '#ef5350',
  line: '#2962ff',
  cross: '#758696',
};

export const PAD_R = 66; // price axis width
export const PAD_B = 26; // time axis height
export const PAD_T = 58; // legend space

export const TIMEFRAMES = [
  { label: '1m', value: 1 },
  { label: '5m', value: 5 },
  { label: '15m', value: 15 },
  { label: '1H', value: 60 },
  { label: '4H', value: 240 },
  { label: '1D', value: 1440 },
];

export const CHART_TYPES = ['candle', 'line', 'area'];
