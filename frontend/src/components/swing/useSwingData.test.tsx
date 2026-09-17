// @vitest-environment happy-dom
import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { SwingPositionDTO, SwingSetupDTO } from '@/lib/api/swing';
import { useSwingData } from './useSwingData';

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getSwingSetups: vi.fn(),
    getSwingPositions: vi.fn(),
    getSwingRegime: vi.fn(),
    triggerSwingScan: vi.fn(),
    enterSwingPosition: vi.fn(),
    exitSwingPosition: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({ api: apiMock }));

function envelope(data: unknown) {
  return { data, error: null, meta: {} };
}

function setup(id: string): SwingSetupDTO {
  return { setup_id: id } as SwingSetupDTO;
}

function closedPosition(id: string): SwingPositionDTO {
  return { position_id: id } as SwingPositionDTO;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function settle() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(400);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  apiMock.getSwingSetups.mockReset();
  apiMock.getSwingPositions.mockReset();
  apiMock.getSwingRegime.mockReset();
  apiMock.triggerSwingScan.mockReset();
  apiMock.enterSwingPosition.mockReset();
  apiMock.exitSwingPosition.mockReset();

  apiMock.getSwingSetups.mockResolvedValue(
    envelope({ count: 0, total_unfiltered: 0, setups: [] }),
  );
  apiMock.getSwingPositions.mockResolvedValue(
    envelope({ open_positions: [], closed_positions: [], portfolio_risk: null }),
  );
  apiMock.getSwingRegime.mockResolvedValue(
    envelope({ regime: null, sectors: [], scan_timestamp_utc: undefined }),
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('useSwingData sequencing', () => {
  it('debounces filter changes and drops the stale response', async () => {
    const first = deferred<unknown>();
    const second = deferred<unknown>();
    apiMock.getSwingSetups
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);

    const { result, rerender } = renderHook(
      ({ filters }: { filters: { min_score: number } }) => useSwingData(filters),
      { initialProps: { filters: { min_score: 50 } } },
    );

    await settle();
    expect(apiMock.getSwingSetups).toHaveBeenCalledTimes(1);
    expect(apiMock.getSwingSetups.mock.calls[0][0]).toEqual({ min_score: 50 });

    rerender({ filters: { min_score: 70 } });
    await settle();
    expect(apiMock.getSwingSetups).toHaveBeenCalledTimes(2);
    expect(apiMock.getSwingSetups.mock.calls[1][0]).toEqual({ min_score: 70 });

    // The newer request resolves first.
    await act(async () => {
      second.resolve(envelope({ count: 1, total_unfiltered: 1, setups: [setup('new')] }));
    });
    expect(result.current.setups.map((s) => s.setup_id)).toEqual(['new']);

    // The superseded request settling late must not overwrite the newer data.
    await act(async () => {
      first.resolve(envelope({ count: 1, total_unfiltered: 1, setups: [setup('old')] }));
    });
    expect(result.current.setups.map((s) => s.setup_id)).toEqual(['new']);
  });

  it('exposes per-section errors while keeping last known data', async () => {
    apiMock.getSwingSetups
      .mockResolvedValueOnce(envelope({ count: 1, total_unfiltered: 1, setups: [setup('s1')] }))
      .mockRejectedValueOnce(new Error('setups backend down'));

    const { result } = renderHook(() => useSwingData({}));
    await settle();
    expect(result.current.setups).toHaveLength(1);
    expect(result.current.setupsError).toBeNull();

    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.setupsError).toContain('setups backend down');
    expect(result.current.stale).toBe(true);
    expect(result.current.error?.kind).toBe('load');
    // Last known setups stay visible instead of being blanked.
    expect(result.current.setups).toHaveLength(1);
  });
});

describe('useSwingData scan', () => {
  it('surfaces scan failure without rethrowing or clearing the list', async () => {
    apiMock.triggerSwingScan.mockRejectedValueOnce(new Error('scan exploded'));

    const { result } = renderHook(() => useSwingData({ min_score: 70 }));
    await settle();

    let returned: unknown = 'unset';
    await act(async () => {
      returned = await result.current.triggerScan(true);
    });

    expect(returned).toBeNull();
    expect(result.current.scanning).toBe(false);
    expect(result.current.error?.kind).toBe('scan');
    expect(result.current.error?.message).toContain('scan exploded');
  });

  it('reloads through the filter path so auto-closed positions leave the open table', async () => {
    apiMock.triggerSwingScan.mockResolvedValueOnce(
      envelope({
        scan_timestamp_utc: Date.now(),
        duration_seconds: 1,
        indices_scanned: 3,
        regime: null,
        sectors: [],
        setups: [setup('unfiltered')],
        open_positions: [],
        closed_positions_count: 1,
        portfolio_risk: null,
      }),
    );
    apiMock.getSwingSetups.mockResolvedValue(
      envelope({ count: 1, total_unfiltered: 2, setups: [setup('filtered')] }),
    );
    apiMock.getSwingPositions.mockResolvedValue(
      envelope({
        open_positions: [],
        closed_positions: [closedPosition('c1')],
        portfolio_risk: null,
      }),
    );

    const { result } = renderHook(() => useSwingData({ min_score: 70 }));
    await settle();

    await act(async () => {
      await result.current.triggerScan(true);
    });

    // The scan response is unfiltered; the desk must end on the filtered list.
    expect(apiMock.getSwingSetups.mock.calls.at(-1)?.[0]).toEqual({ min_score: 70 });
    expect(result.current.setups.map((s) => s.setup_id)).toEqual(['filtered']);
    // Scan auto-closes positions; the closed history must be refreshed.
    expect(result.current.closedPositions.map((p) => p.position_id)).toEqual(['c1']);
    expect(result.current.error).toBeNull();
  });
});

describe('useSwingData actions', () => {
  it('rethrows entry failures so the caller can show inline feedback', async () => {
    apiMock.enterSwingPosition.mockRejectedValueOnce(
      new Error('Risk Gate Rejection: max portfolio heat'),
    );

    const { result } = renderHook(() => useSwingData({}));
    await settle();

    await expect(result.current.enterTrade('s1')).rejects.toThrow('Risk Gate Rejection');
  });

  it('rethrows exit failures so the confirmation can stay open', async () => {
    apiMock.exitSwingPosition.mockRejectedValueOnce(new Error('position not found'));

    const { result } = renderHook(() => useSwingData({}));
    await settle();

    await expect(result.current.exitTrade('p1', 10, 'MANUAL_EXIT')).rejects.toThrow(
      'position not found',
    );
  });
});
