// @vitest-environment happy-dom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useSmartInterval } from './useSmartInterval';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // Restore the prototype getter overridden by the visibility test.
  delete (document as unknown as Record<string, unknown>).hidden;
});

describe('useSmartInterval (real hook)', () => {
  it('fires immediately on mount by default and reports active', () => {
    const callback = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useSmartInterval(callback, 1000));

    expect(callback).toHaveBeenCalledTimes(1);
    expect(result.current.active).toBe(true);
  });

  it('does not fire when intervalMs is null and reports inactive', () => {
    const callback = vi.fn().mockResolvedValue(undefined);
    const { result } = renderHook(() => useSmartInterval(callback, null));

    expect(callback).not.toHaveBeenCalled();
    expect(result.current.active).toBe(false);
  });

  it('waits for the interval when fireOnMount is false', async () => {
    vi.useFakeTimers();
    const callback = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useSmartInterval(callback, 1000, { fireOnMount: false }));

    expect(callback).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('skips refresh() while a previous execution is unresolved (overlap guard)', async () => {
    let resolveFirst: (() => void) | undefined;
    const callback = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const { result } = renderHook(() => useSmartInterval(callback, 1000));
    expect(callback).toHaveBeenCalledTimes(1);

    await act(async () => {
      await result.current.refresh();
    });
    expect(callback).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst?.();
    });
  });

  it('keeps the period at intervalMs when the callback takes time (drift correction)', async () => {
    vi.useFakeTimers();
    const starts: number[] = [];
    const callback = vi.fn(async () => {
      starts.push(Date.now());
      await new Promise((resolve) => setTimeout(resolve, 300));
    });

    renderHook(() => useSmartInterval(callback, 1000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(starts.length).toBeGreaterThanOrEqual(4);
    // Mount run starts at t0, the next tick is aligned to t0 + 300 + 1000.
    // Every gap after that must stay exactly intervalMs (not intervalMs + 300).
    const gaps = starts.slice(2).map((start, i) => start - starts[i + 1]);
    expect(gaps.every((gap) => gap === 1000)).toBe(true);
  });

  it('captures callback rejections (no unhandled rejection) and keeps scheduling', async () => {
    vi.useFakeTimers();
    const callback = vi.fn().mockRejectedValue(new Error('boom'));

    renderHook(() => useSmartInterval(callback, 1000));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500);
    });

    expect(callback.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('pauses while document.hidden and fires once on visibility return', async () => {
    vi.useFakeTimers();
    const callback = vi.fn().mockResolvedValue(undefined);
    renderHook(() => useSmartInterval(callback, 1000));
    expect(callback).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(callback).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(callback).toHaveBeenCalledTimes(2);
  });
});
