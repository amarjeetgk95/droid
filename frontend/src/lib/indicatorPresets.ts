import type { ResearchPreset } from './api/indicatorResearch';

export const CANONICAL_PRESETS: ResearchPreset[] = [
  {
    id: 'ehlers_cycle_reversal',
    name: 'Ehlers Cycle Reversal (Fisher 9 + EBSW)',
    description: 'Combines Gaussian normalized price extremity (Fisher Transform 9) with cycle turning points from Even Better Sinewave (EBSW).',
    instrument: 'NIFTY',
    timeframe: '5m',
    order_flow_required: false,
    indicators: [
      { indicator_id: 'fisher', params: { length: 9, signal_length: 1 }, role: 'primary' },
      { indicator_id: 'ebsw', params: { hp_period: 48, ssf_period: 10 }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'fisher', operator: 'crosses_above', right: -1.5 },
          { left: 'ebsw', operator: 'turns_up' },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'fisher', operator: 'crosses_below', right: 1.5 },
          { left: 'ebsw', operator: 'turns_down' },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 1.5, target_mode: 'atr', target_value: 3.0 },
    },
  },
  {
    id: 'trend_momentum',
    name: 'Trend Momentum (WaveTrend + Anchored VWAP)',
    description: 'WaveTrend oscillator zero-line / oversold crossovers filtered by price relative to Anchored VWAP.',
    instrument: 'NIFTY',
    timeframe: '5m',
    order_flow_required: false,
    indicators: [
      { indicator_id: 'wavetrend', params: { channel_length: 10, average_length: 21 }, role: 'primary' },
      { indicator_id: 'vwap', params: { anchor: 'session' }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'wt1', operator: 'crosses_above', right: 'wt2' },
          { left: 'close', operator: '>', right: 'vwap' },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'wt1', operator: 'crosses_below', right: 'wt2' },
          { left: 'close', operator: '<', right: 'vwap' },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 2.0, target_mode: 'atr', target_value: 4.0 },
    },
  },
  {
    id: 'order_flow_absorption',
    name: 'Order Flow Absorption (CVD + Absorption Detector)',
    description: 'Detects aggressive delta volume absorption at key price extremes where aggressive market orders fail to push price.',
    instrument: 'NIFTY',
    timeframe: '1m',
    order_flow_required: true,
    indicators: [
      {
        indicator_id: 'absorption',
        params: { window: 10, aggression_threshold: 2.5, progress_threshold_atr: 0.5 },
        role: 'primary',
      },
      { indicator_id: 'cvd', params: { anchor: 'session' }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'bullish_absorption', operator: '>', right: 0.5 },
          { left: 'delta', operator: '>', right: 0.0 },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'bearish_absorption', operator: '>', right: 0.5 },
          { left: 'delta', operator: '<', right: 0.0 },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 1.0, target_mode: 'atr', target_value: 2.0 },
    },
  },
  {
    id: 'dpfi_breakout',
    name: 'Directional Pressure Breakout (DPFI v1 + Supertrend)',
    description: 'High directional pressure flow imbalance (DPFI) confirmed by Supertrend trend alignment.',
    instrument: 'BANKNIFTY',
    timeframe: '1m',
    order_flow_required: true,
    indicators: [
      {
        indicator_id: 'dpfi',
        params: { depth_levels: 5, norm_window: 20, decay: 0.9 },
        role: 'primary',
      },
      { indicator_id: 'supertrend', params: { length: 10, multiplier: 3.0 }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'dpfi', operator: '>', right: 0.35 },
          { left: 'supertrend_direction', operator: '==', right: 1 },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'dpfi', operator: '<', right: -0.35 },
          { left: 'supertrend_direction', operator: '==', right: -1 },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 1.5, target_mode: 'atr', target_value: 3.0 },
    },
  },
  {
    id: 'stoch_rsi_mean_reversion',
    name: 'Stochastic RSI Mean Reversion (Stoch RSI + Bollinger Bands)',
    description: 'Oversold / overbought momentum turns from Stochastic RSI occurring outside or near Bollinger Band extremes.',
    instrument: 'NIFTY',
    timeframe: '5m',
    order_flow_required: false,
    indicators: [
      {
        indicator_id: 'stoch_rsi',
        params: { rsi_length: 14, stoch_length: 14, k_smooth: 3, d_smooth: 3 },
        role: 'primary',
      },
      { indicator_id: 'bollinger', params: { length: 20, std_dev: 2.0 }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'k', operator: 'crosses_above', right: 20.0 },
          { left: 'close', operator: '<=', right: 'lower' },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'k', operator: 'crosses_below', right: 80.0 },
          { left: 'close', operator: '>=', right: 'upper' },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 1.5, target_mode: 'atr', target_value: 2.5 },
    },
  },
  {
    id: 'stc_mama_timing',
    name: 'Schaff Trend Cycle Timing (STC + MAMA/FAMA)',
    description: 'Fast cycle timing using Schaff Trend Cycle filtered by adaptive trend state from Ehlers MAMA / FAMA crossover.',
    instrument: 'NIFTY',
    timeframe: '5m',
    order_flow_required: false,
    indicators: [
      {
        indicator_id: 'stc',
        params: { fast_length: 23, slow_length: 50, stc_length: 10, factor: 0.5 },
        role: 'primary',
      },
      { indicator_id: 'mama_fama', params: { fast_limit: 0.5, slow_limit: 0.05 }, role: 'overlay' },
    ],
    rules: {
      long: {
        operator: 'AND',
        conditions: [
          { left: 'stc', operator: 'crosses_above', right: 25.0 },
          { left: 'mama', operator: '>', right: 'fama' },
        ],
      },
      short: {
        operator: 'AND',
        conditions: [
          { left: 'stc', operator: 'crosses_below', right: 75.0 },
          { left: 'mama', operator: '<', right: 'fama' },
        ],
      },
    },
    settings: {
      execution: { entry_fill: 'next_open' },
      exits: { stop_mode: 'atr', stop_value: 1.5, target_mode: 'atr', target_value: 3.0 },
    },
  },
];
