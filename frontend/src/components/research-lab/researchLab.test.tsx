// @vitest-environment happy-dom
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getResearchIndicators: vi.fn(async () => [] as unknown[]),
    runResearchExperiment: vi.fn(async (_payload: Record<string, unknown>) => ({}) as unknown),
    getMLModelInfo: vi.fn(async () => ({ data: {} }) as unknown),
    getMLChampionInfo: vi.fn(async () => ({ data: { champion_models: {} } }) as unknown),
    getMLChallengerInfo: vi.fn(async () => ({ data: { challenger_models: {} } }) as unknown),
    listResearchPredictions: vi.fn(async () => [] as unknown[]),
    measureResearchPrediction: vi.fn(async () => ({}) as unknown),
  },
}));

vi.mock('@/lib/api', () => ({ api: apiMock }));
vi.mock('@/context/InstrumentContext', () => ({
  useInstrument: () => ({
    instrument: 'NIFTY',
    setInstrument: () => {},
    timeframe: '1h',
    setTimeframe: () => {},
    allInstruments: ['NIFTY'],
    allTimeframes: ['1h'],
  }),
}));

import { ExperimentRunner } from './ExperimentRunner';
import { MLModelRegistry } from './MLModelRegistry';
import { PredictionTracker } from './PredictionTracker';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  apiMock.getResearchIndicators.mockResolvedValue([]);
  apiMock.getMLModelInfo.mockResolvedValue({ data: {} });
  apiMock.getMLChampionInfo.mockResolvedValue({ data: { champion_models: {} } });
  apiMock.getMLChallengerInfo.mockResolvedValue({ data: { challenger_models: {} } });
  apiMock.listResearchPredictions.mockResolvedValue([]);
});

describe('ExperimentRunner', () => {
  it('posts the indicator contract and renders the real validation report', async () => {
    apiMock.getResearchIndicators.mockResolvedValue([
      {
        indicator_id: 'vwap_bands',
        name: 'Anchor VWAP Multi-Bands',
        lifecycle: 'VALIDATING',
        current_version: '1.0.0',
      },
    ]);
    apiMock.runResearchExperiment.mockResolvedValue({
      run: { run_id: 'run_abc', status: 'COMPLETED', sample_count: 40, completed_at: '2026-09-17T10:00:00Z' },
      report: {
        sample_size: 40,
        accuracy: 62.5,
        baseline_accuracy: 50,
        excess_accuracy: 12.5,
        precision: 60,
        recall: 55,
        f1_score: 57.4,
        p_value: 0.031,
        is_statistically_significant: true,
        confidence_interval_95: [48.1, 74.9],
      },
    });

    render(<ExperimentRunner />);
    await waitFor(() => expect(screen.getByRole('button', { name: /Run validation experiment/i })).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: /Run validation experiment/i }));

    await waitFor(() => expect(apiMock.runResearchExperiment).toHaveBeenCalledTimes(1));
    const payload = apiMock.runResearchExperiment.mock.calls[0][0];
    expect(payload).toMatchObject({
      indicator_id: 'vwap_bands',
      instrument: 'NIFTY',
      timeframe: '1h',
      horizon_candles: 5,
      stride: 5,
    });
    expect(Object.keys(payload)).not.toContain('name');
    expect(Object.keys(payload)).not.toContain('hypothesis');

    await waitFor(() => expect(screen.getByText('62.50%')).toBeTruthy());
    expect(screen.queryByText(/2\.14/)).toBeNull();
    expect(screen.queryByText(/HYPOTHESIS VALIDATED/i)).toBeNull();
  });
});

describe('MLModelRegistry', () => {
  it('renders real manifests and disables training with an explicit reason', async () => {
    apiMock.getMLModelInfo.mockResolvedValue({
      data: {
        trained: true,
        model_version: 'XGBoost-LightGBM-Ensemble-v2.0-h60',
        horizon_minutes: 60,
        n_samples: 120,
        n_features: 15,
        target_spec_version: 'v2-atr-em-session',
        trained_at: '2026-09-17T14:58:58Z',
        metrics: { ensemble_accuracy: 0.625, xgb_accuracy: 0.6667, xgb_logloss: 0.8121, lgb_accuracy: 0.5833, lgb_logloss: 0.8135 },
        artifacts: { xgb_exists: true, lgb_exists: true },
      },
    });
    apiMock.getMLChampionInfo.mockResolvedValue({
      data: { champion_models: { breakout_meta: { model_version: 'breakout_v1_champion', validation_accuracy: 0.994 } } },
    });

    render(<MLModelRegistry />);

    await waitFor(() =>
      expect(screen.getAllByText('breakout_v1_champion').length).toBeGreaterThan(0),
    );
    expect(screen.getByText('validation accuracy')).toBeTruthy();
    expect(screen.getByText('63%')).toBeTruthy();
    expect(screen.getByText(/Unavailable from this UI/)).toBeTruthy();
    const retrain = screen.getByRole('button', { name: /Retrain ensemble/i }) as HTMLButtonElement;
    expect(retrain.disabled).toBe(true);
    expect(screen.queryByText(/JOB-001/)).toBeNull();
  });
});

describe('PredictionTracker', () => {
  it('lists backend rows and measures against the real prediction id', async () => {
    apiMock.listResearchPredictions.mockResolvedValue([
      {
        prediction_id: 'pred_abc123',
        indicator_id: 'vwap_bands',
        instrument: 'NIFTY',
        timeframe: '5m',
        timestamp: '2026-09-17T10:00:00Z',
        direction: 'BULLISH',
        confidence: 0.82,
        forecast_horizon: '15m',
      },
    ]);
    apiMock.measureResearchPrediction.mockResolvedValue({
      outcome_id: 'out_1',
      prediction_id: 'pred_abc123',
      actual_direction: 'BULLISH',
      actual_pct_move: 0.42,
      is_correct: true,
    });

    render(<PredictionTracker />);

    await waitFor(() => expect(screen.getByText('pred_abc123')).toBeTruthy());
    expect(screen.getByText('BULLISH')).toBeTruthy();
    expect(screen.queryByText(/PRED-101/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Measure/i }));
    await waitFor(() => expect(apiMock.measureResearchPrediction).toHaveBeenCalledWith('pred_abc123'));
    await waitFor(() => expect(screen.getByText(/CORRECT/)).toBeTruthy());
  });

  it('shows the error state instead of fake seed rows when the list fails', async () => {
    apiMock.listResearchPredictions.mockRejectedValue(new Error('backend down'));

    render(<PredictionTracker />);

    await waitFor(() => expect(screen.getByText(/backend down/)).toBeTruthy());
    expect(screen.queryByText(/PRED-10/)).toBeNull();
    expect(screen.queryByText(/UNMEASURED/)).toBeNull();
  });
});
