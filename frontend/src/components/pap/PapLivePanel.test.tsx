// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { PapLivePanel } from './PapLivePanel';
import type { PapHorizon, PapLive } from '@/lib/api/pap';

function horizon(over: Partial<PapHorizon> = {}): PapHorizon {
  return {
    up: 68,
    neutral: 19,
    down: 13,
    prediction: 'UP',
    probability: 68,
    confidence: null,
    prediction_state: 'ACTIVE',
    model_source: 'heuristic_ensemble',
    calibrated: false,
    artifact_horizon_minutes: null,
    model_version: 'XGBoost-LightGBM-Ensemble-v1.0-heuristic',
    ...over,
  };
}

function live(over: Partial<PapLive> = {}): PapLive {
  return {
    instrument: 'NIFTY',
    timeframe: '1 MIN',
    timestamp: '2026-09-23T04:00:00+00:00',
    price: 25123.45,
    data_status: 'LIVE',
    data_age_s: 4,
    available: true,
    mode: 'SHADOW',
    execution: 'DISABLED',
    horizons: { '3m': horizon({ up: 71, neutral: 18, down: 11, probability: 71 }), '5m': horizon(), '10m': horizon({ up: 39, neutral: 51, down: 10, prediction: 'NEUTRAL', probability: 51 }) },
    features: { fisher: 1.42 },
    market_state: {
      fisher: 1.42,
      price_vs_vwap_pct: 0.31,
      adx: 27.8,
      plus_di: 29,
      minus_di: 17,
      lr_slope: 0.0042,
      bb_width_pct: 0.82,
      trend: 'BULLISH',
      volatility: 'NORMAL',
      vwap_position: 'ABOVE',
    },
    evidence: [{ label: 'Price above VWAP', state: 'supportive', detail: '+0.31% vs session VWAP' }],
    evidence_note: 'Explanatory only.',
    droid_alignment: {
      droid_signal: 'LONG',
      droid_state: 'CONFIRMED',
      droid_strategy: 'VWAP_MOMENTUM',
      pap_primary: 'UP',
      pap_primary_horizon: '5m',
      alignment: 'ALIGNED',
      advisory_only: true,
    },
    horizon_consensus: { consensus: 'SHORT-TERM BULLISH', predictions: { '3m': 'UP', '5m': 'UP', '10m': 'NEUTRAL' } },
    model: {
      name: 'XGBoost',
      versions: ['XGBoost-LightGBM-Ensemble-v1.0-heuristic'],
      feature_schema: 'f10-v1',
      calibration: 'NOT_CALIBRATED',
      data_quality: 'GOOD',
      prediction_age_s: 4,
      status: 'VALID',
      shadow_mode: 'ACTIVE',
      execution: 'DISABLED',
    },
    calibration: { status: 'NOT_CALIBRATED', note: '' },
    ...over,
  };
}

describe('PapLivePanel', () => {
  afterEach(cleanup);

  it('renders 3m/5m/10m distributions with probabilities visible', () => {
    render(<PapLivePanel live={live()} error={null} loading={false} />);
    for (const id of ['3m', '5m', '10m']) {
      expect(screen.getByTestId(`pap-horizon-${id}`)).toBeTruthy();
    }
    const bar = screen.getAllByTestId('pap-prob-bar')[0];
    expect(bar.getAttribute('aria-label')).toMatch(/Up .*%, neutral .*%, down .*%/);
    expect(screen.getByTestId('pap-pred-5m').textContent).toBe('UP');
    expect(screen.getByTestId('pap-conf-5m').textContent).toContain('not calibrated');
  });

  it('shows PAP DATA UNAVAILABLE instead of fabricated values', () => {
    render(<PapLivePanel live={live({ available: false, horizons: null, unavailable_reason: 'Quote down' })} error={null} loading={false} />);
    const el = screen.getByTestId('pap-unavailable');
    expect(el.textContent).toContain('PAP DATA UNAVAILABLE');
    expect(el.textContent).toContain('Quote down');
    expect(screen.queryByTestId('pap-horizon-5m')).toBeNull();
  });

  it('renders API failure as unavailable without zeros', () => {
    render(<PapLivePanel live={null} error="Cannot reach backend" loading={false} />);
    expect(screen.getByTestId('pap-unavailable').textContent).toContain('PAP DATA UNAVAILABLE');
  });

  it('marks stale data honestly and never as live', () => {
    render(<PapLivePanel live={live({ data_status: 'STALE', data_age_s: 95 })} error={null} loading={false} />);
    expect(screen.getByTestId('pap-status').textContent).toContain('STALE');
    expect(screen.getByTestId('pap-status').textContent).not.toContain('LIVE');
  });

  it('covers alignment states and market-state features', () => {
    const { rerender } = render(<PapLivePanel live={live()} error={null} loading={false} />);
    expect(screen.getByTestId('pap-alignment').textContent).toBe('ALIGNED');
    expect(screen.getByTestId('pap-droid-signal').textContent).toContain('LONG');
    expect(screen.getByTestId('pap-market-state').textContent).toContain('27.8');
    expect(screen.getByTestId('pap-evidence').textContent).toContain('Price above VWAP');

    rerender(
      <PapLivePanel
        live={live({ droid_alignment: { droid_signal: 'LONG', pap_primary: 'DOWN', alignment: 'CONFLICT', advisory_only: true } })}
        error={null}
        loading={false}
      />,
    );
    expect(screen.getByTestId('pap-alignment').textContent).toBe('CONFLICT');
  });

  it('exposes no execution authority anywhere in the panel', () => {
    const { container } = render(<PapLivePanel live={live()} error={null} loading={false} />);
    const text = (container.textContent ?? '').toLowerCase();
    for (const forbidden of ['execute', 'buy now', 'sell now', 'place order', 'square off']) {
      // "Execute paper order" style CTAs must never appear in PAP.
      expect(text).not.toContain(forbidden === 'execute' ? 'execute paper' : forbidden);
    }
    expect(container.querySelector('button')).toBeNull();
  });

  it('switches instruments by rendering the new payload', () => {
    const { rerender } = render(<PapLivePanel live={live()} error={null} loading={false} />);
    expect(screen.getByTestId('pap-price').textContent).toContain('25,123');
    rerender(<PapLivePanel live={live({ instrument: 'BANKNIFTY', price: 57780 })} error={null} loading={false} />);
    expect(screen.getByTestId('pap-price').textContent).toContain('57,780');
  });
});
