// @vitest-environment happy-dom
import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useExecutionGuard } from './useExecutionGuard';

afterEach(() => cleanup());

describe('useExecutionGuard (real hook)', () => {
  it('runs an action, returns its result, and tracks pending state', async () => {
    const { result } = renderHook(() => useExecutionGuard());

    let resolveAction: ((value: string) => void) | undefined;
    let promise: Promise<string | null> | undefined;
    act(() => {
      promise = result.current.execute(
        () =>
          new Promise<string>((resolve) => {
            resolveAction = resolve;
          }),
      );
    });

    expect(result.current.isPending).toBe(true);

    await act(async () => {
      resolveAction?.('filled');
    });
    await expect(promise).resolves.toBe('filled');

    expect(result.current.isPending).toBe(false);
    expect(result.current.lastError).toBeNull();
    expect(result.current.lastRejectionReason).toBeNull();
  });

  it('returns the action result and resets pending after success', async () => {
    const { result } = renderHook(() => useExecutionGuard());

    let outcome: number | null | undefined;
    await act(async () => {
      outcome = await result.current.execute(async () => 42);
    });

    expect(outcome).toBe(42);
    expect(result.current.isPending).toBe(false);
    expect(result.current.lastError).toBeNull();
  });

  it('rejects re-entrant calls as busy, distinguishably from errors', async () => {
    const { result } = renderHook(() => useExecutionGuard());

    let releaseFirst: (() => void) | undefined;
    let first: Promise<string | null> | undefined;
    act(() => {
      first = result.current.execute(
        () =>
          new Promise<string>((resolve) => {
            releaseFirst = () => resolve('first');
          }),
      );
    });

    let secondOutcome: string | null | undefined;
    await act(async () => {
      secondOutcome = await result.current.execute(async () => 'should-not-run');
    });

    expect(secondOutcome).toBeNull();
    expect(result.current.isPending).toBe(true);
    expect(result.current.lastRejectionReason).toBe('busy');
    expect(result.current.lastError).toBeNull();

    await act(async () => {
      releaseFirst?.();
      await first;
    });
    expect(result.current.isPending).toBe(false);
  });

  it('captures action errors and flags them as error rejections', async () => {
    const { result } = renderHook(() => useExecutionGuard());

    let outcome: string | null | undefined;
    await act(async () => {
      outcome = await result.current.execute(async () => {
        throw new Error('order rejected');
      });
    });

    expect(outcome).toBeNull();
    expect(result.current.isPending).toBe(false);
    expect(result.current.lastError).toBe('order rejected');
    expect(result.current.lastRejectionReason).toBe('error');

    act(() => {
      result.current.clearError();
    });
    expect(result.current.lastError).toBeNull();
    expect(result.current.lastRejectionReason).toBeNull();
  });

  it('detects stale quotes against the configured threshold', () => {
    const { result } = renderHook(() => useExecutionGuard({ defaultStaleThresholdSec: 15 }));
    const now = Date.now();

    expect(result.current.checkQuoteFreshness(now - 5_000)).toEqual({ isStale: false, ageSec: 5 });
    expect(result.current.checkQuoteFreshness(now - 25_000)).toEqual({ isStale: true, ageSec: 25 });
    expect(result.current.checkQuoteFreshness(null)).toEqual({ isStale: true, ageSec: null });
    expect(result.current.checkQuoteFreshness(now - 1_000, 0)).toEqual({ isStale: true, ageSec: 1 });
  });

  it('does not set state after unmount when a late action settles', async () => {
    const { result, unmount } = renderHook(() => useExecutionGuard());

    let releaseLate: (() => void) | undefined;
    let promise: Promise<string | null> | undefined;
    act(() => {
      promise = result.current.execute(
        () =>
          new Promise<string>((resolve) => {
            releaseLate = () => resolve('late');
          }),
      );
    });

    unmount();

    await act(async () => {
      releaseLate?.();
      await promise;
    });
  });
});
