// @vitest-environment happy-dom
import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useAsyncAction, type AsyncActionOutcome } from './useAsyncAction';
import { useExecutionGuard } from './useExecutionGuard';

afterEach(() => cleanup());

describe('useAsyncAction', () => {
  it('resolves the action value under the ok branch and clears pending', async () => {
    const { result } = renderHook(() => useAsyncAction({ busyMessage: 'busy text' }));

    let outcome: AsyncActionOutcome<number> | undefined;
    await act(async () => {
      outcome = await result.current.run(async () => 42);
    });

    expect(outcome).toEqual({ ok: true, value: 42 });
    expect(result.current.isPending).toBe(false);
  });

  it('returns the exact errorMessage with the configured fallback instead of throwing', async () => {
    const { result } = renderHook(() =>
      useAsyncAction({ busyMessage: 'busy text', errorFallback: 'sizing unavailable' }),
    );

    let outcome: AsyncActionOutcome<void> | undefined;
    await act(async () => {
      outcome = await result.current.run(async () => {
        throw new Error('engine exploded');
      });
    });
    expect(outcome).toEqual({ ok: false, reason: 'error', message: 'engine exploded' });

    await act(async () => {
      outcome = await result.current.run(async () => {
        throw { opaque: true };
      });
    });
    expect(outcome).toEqual({ ok: false, reason: 'error', message: 'sizing unavailable' });
    expect(result.current.lastRejectionReason).toBe('error');
  });

  it('reports a re-entrant run as busy with the default or per-run busy text', async () => {
    const { result } = renderHook(() => useAsyncAction({ busyMessage: 'already running' }));

    let release: (() => void) | undefined;
    let first: Promise<AsyncActionOutcome<string>> | undefined;
    act(() => {
      first = result.current.run(
        () =>
          new Promise<string>((resolve) => {
            release = () => resolve('first');
          }),
      );
    });

    let busy: AsyncActionOutcome<void> | undefined;
    await act(async () => {
      busy = await result.current.run(async () => undefined);
    });
    expect(busy).toEqual({ ok: false, reason: 'busy', message: 'already running' });

    await act(async () => {
      busy = await result.current.run(async () => undefined, { busyMessage: 'unknown error' });
    });
    expect(busy).toEqual({ ok: false, reason: 'busy', message: 'unknown error' });

    await act(async () => {
      release?.();
      await first;
    });
  });

  it('shares a provided guard so both wrappers contend for one lock', async () => {
    const { result } = renderHook(() => {
      const guard = useExecutionGuard();
      const action = useAsyncAction({ guard, busyMessage: 'already running' });
      return { guard, action };
    });

    let release: (() => void) | undefined;
    let first: Promise<AsyncActionOutcome<string>> | undefined;
    act(() => {
      first = result.current.action.run(
        () =>
          new Promise<string>((resolve) => {
            release = () => resolve('first');
          }),
      );
    });

    let direct: string | null | undefined;
    await act(async () => {
      direct = await result.current.guard.execute(async () => 'should-not-run');
    });
    expect(direct).toBeNull();
    expect(result.current.guard.lastRejectionReason).toBe('busy');

    await act(async () => {
      release?.();
      await first;
    });

    let after: AsyncActionOutcome<string> | undefined;
    await act(async () => {
      after = await result.current.action.run(async () => 'after');
    });
    expect(after).toEqual({ ok: true, value: 'after' });
    expect(result.current.guard.lastRejectionReason).toBeNull();
  });
});
