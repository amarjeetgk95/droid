import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { navigationController } from './navigationController';

const EMERGENCY_TIMEOUT_MS = 8000;

describe('navigationController', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Start every test from a clean, idle state (singleton is module-level).
    navigationController.cancel();
  });

  afterEach(() => {
    navigationController.cancel();
    vi.useRealTimers();
  });

  it('increments navIds monotonically and reports navigating', () => {
    const first = navigationController.start();
    const state1 = navigationController.getState();
    expect(state1.activeNavId).toBe(first);
    expect(state1.isNavigating).toBe(true);

    const second = navigationController.start();
    expect(second).toBe(first + 1);
    expect(navigationController.getState().activeNavId).toBe(second);
    expect(navigationController.getState().isNavigating).toBe(true);

    navigationController.complete(second);
    expect(navigationController.getState().isNavigating).toBe(false);
  });

  it('discards a stale completion from an older navigation', () => {
    const first = navigationController.start();
    const second = navigationController.start();

    navigationController.complete(first);

    expect(navigationController.getState().isNavigating).toBe(true);
    expect(navigationController.getState().activeNavId).toBe(second);

    navigationController.complete(second);
    expect(navigationController.getState().isNavigating).toBe(false);
  });

  it('discards a stale cancellation from an older navigation', () => {
    const first = navigationController.start();
    const second = navigationController.start();

    navigationController.cancel(first);

    expect(navigationController.getState().isNavigating).toBe(true);
    expect(navigationController.getState().activeNavId).toBe(second);
  });

  it('does not let an older emergency timeout cancel the newer navigation', () => {
    const first = navigationController.start();
    vi.advanceTimersByTime(EMERGENCY_TIMEOUT_MS - 1000);
    const second = navigationController.start();

    // t = 8000ms: the first timer would fire here if it had not been retired.
    vi.advanceTimersByTime(1000);
    expect(navigationController.getState().isNavigating).toBe(true);
    expect(navigationController.getState().activeNavId).toBe(second);

    // The newer navigation still has its own 8s fallback.
    vi.advanceTimersByTime(EMERGENCY_TIMEOUT_MS - 1000);
    expect(navigationController.getState().isNavigating).toBe(false);
    expect(navigationController.getState().activeNavId).toBe(second);
    expect(first).toBeLessThan(second);
  });

  it('completes the active navigation when called without a navId', () => {
    navigationController.start();
    expect(navigationController.getState().isNavigating).toBe(true);

    navigationController.complete();
    expect(navigationController.getState().isNavigating).toBe(false);

    // Idle completion is a no-op — no extra notifications.
    const listener = vi.fn();
    const unsubscribe = navigationController.subscribe(listener);
    listener.mockClear();
    navigationController.complete();
    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });

  it('notifies subscribers on start and clears the timer on complete', () => {
    const listener = vi.fn();
    const unsubscribe = navigationController.subscribe(listener);
    listener.mockClear();

    const id = navigationController.start();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenLastCalledWith({ activeNavId: id, isNavigating: true });

    navigationController.complete(id);
    expect(listener).toHaveBeenCalledTimes(2);
    expect(listener).toHaveBeenLastCalledWith({ activeNavId: id, isNavigating: false });

    // Completed navigation's emergency timeout must be retired.
    vi.advanceTimersByTime(EMERGENCY_TIMEOUT_MS + 1000);
    expect(listener).toHaveBeenCalledTimes(2);

    unsubscribe();
    listener.mockClear();
    navigationController.start();
    expect(listener).not.toHaveBeenCalled();
    navigationController.complete();
  });
});
