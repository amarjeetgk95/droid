// @vitest-environment happy-dom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, waitFor, act, cleanup } from '@testing-library/react';
import { api } from '@/lib/api';
import { FORECAST_HORIZONS } from '@/lib/forecastBoard';
import type { HourForecast } from '@/lib/types';
import type { ForecastBoardResponse } from '@/lib/api/intelligence';
import { useForecastBoard } from './useForecastBoard';

vi.mock('@/lib/api', () => ({
  api: {
    getTacticalBiasBoard: vi.fn(),
    getTacticalBias: vi.fn(),
  },
}));

const boardMock = vi.mocked(api.getTacticalBiasBoard);
const singleMock = vi.mocked(api.getTacticalBias);

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

const GENERATED_AT = '2026-09-21T12:00:00.000Z';

function horizonForecast(horizon: string, generatedAt: string = GENERATED_AT): HourForecast {
  return {
    instrument: 'SENSEX',
    timeframe: horizon,
    current_price: 82000,
    direction: 'NEUTRAL',
    score: 0,
    confidence: 50,
    generated_at: generatedAt,
  };
}

function boardPayload(generatedAt: string = GENERATED_AT): ForecastBoardResponse {
  return {
    instrument: 'SENSEX',
    generated_at: generatedAt,
    anchor_price: 82000,
    anchor_source: 'spot',
    anchor_ts: null,
    cache_age_s: 0,
    stale: false,
    horizons: Object.fromEntries(
      FORECAST_HORIZONS.map((horizon) => [horizon, horizonForecast(horizon, generatedAt)]),
    ) as ForecastBoardResponse['horizons'],
  };
}

describe('useForecastBoard (board primary path)', () => {
  it('maps the board snapshot to forecasts with the single shared generated_at', async () => {
    boardMock.mockResolvedValue(boardPayload());

    const { result } = renderHook(() => useForecastBoard('SENSEX'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(boardMock).toHaveBeenCalledTimes(1);
    expect(boardMock).toHaveBeenCalledWith('SENSEX', false, true);
    // Primary path never touches the legacy single-horizon endpoint.
    expect(singleMock).not.toHaveBeenCalled();
    for (const horizon of FORECAST_HORIZONS) {
      expect(result.current.forecasts[horizon]?.generated_at).toBe(GENERATED_AT);
    }
    expect(result.current.errors).toEqual({});
    expect(result.current.updatedAt).toBe(Date.parse(GENERATED_AT));
    expect(result.current.refreshing).toBe(false);
  });

  it('keeps refresh({record}) semantics on the board path', async () => {
    boardMock.mockResolvedValue(boardPayload());

    const { result } = renderHook(() => useForecastBoard('SENSEX'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refresh();
    });

    expect(boardMock).toHaveBeenCalledTimes(2);
    expect(boardMock).toHaveBeenLastCalledWith('SENSEX', true, true);
    await waitFor(() => expect(result.current.refreshing).toBe(false));
  });

  it('falls back to the 5-call path when the board request fails (old backend)', async () => {
    boardMock.mockRejectedValue(new Error('Not Found'));
    const times: Record<string, string> = Object.fromEntries(
      FORECAST_HORIZONS.map((horizon, index) => [
        horizon,
        new Date(Date.parse(GENERATED_AT) + index * 60_000).toISOString(),
      ]),
    );
    singleMock.mockImplementation(async (_instrument: string, horizon = '1h') =>
      horizonForecast(horizon, times[horizon] ?? GENERATED_AT),
    );

    const { result } = renderHook(() => useForecastBoard('SENSEX'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(boardMock).toHaveBeenCalledTimes(1);
    expect(singleMock).toHaveBeenCalledTimes(5);
    for (const horizon of FORECAST_HORIZONS) {
      expect(result.current.forecasts[horizon]?.generated_at).toBe(times[horizon]);
    }
    expect(result.current.errors).toEqual({});
    expect(result.current.updatedAt).toBe(
      Math.max(...Object.values(times).map((t) => Date.parse(t))),
    );
  });

  it('surfaces per-horizon errors from the fallback path', async () => {
    boardMock.mockRejectedValue(new Error('Cannot reach backend'));
    singleMock.mockImplementation(async (_instrument: string, horizon = '1h') => {
      if (horizon === '1m') throw new Error('boom');
      return horizonForecast(horizon);
    });

    const { result } = renderHook(() => useForecastBoard('SENSEX'));

    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.forecasts['1m']).toBeUndefined();
    expect(result.current.errors['1m']).toBe('boom');
    for (const horizon of FORECAST_HORIZONS) {
      if (horizon === '1m') continue;
      expect(result.current.forecasts[horizon]?.generated_at).toBe(GENERATED_AT);
    }
    expect(result.current.updatedAt).toBe(Date.parse(GENERATED_AT));
  });
});
