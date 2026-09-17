// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, cleanup } from '@testing-library/react';
import { useSignalsStream } from './useSignalsStream';

type FakeListener = (event: { data: string }) => void;

class FakeEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: FakeEventSource[] = [];

  readonly url: string;
  readyState = FakeEventSource.OPEN;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: FakeListener | null = null;
  closeCalls = 0;

  private listeners = new Map<string, Set<FakeListener>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
    queueMicrotask(() => {
      if (this.readyState === FakeEventSource.OPEN) this.onopen?.();
    });
  }

  addEventListener(type: string, listener: FakeListener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: FakeListener) {
    this.listeners.get(type)?.delete(listener);
  }

  close() {
    this.closeCalls += 1;
    this.readyState = FakeEventSource.CLOSED;
  }

  emit(payload: unknown) {
    const event = { data: JSON.stringify(payload) };
    this.listeners.get('signal_event')?.forEach((listener) => listener(event));
  }
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal('EventSource', FakeEventSource);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('useSignalsStream shared connection', () => {
  it('shares one EventSource across multiple mounts and fans events out once each', async () => {
    const firstListener = vi.fn();
    const secondListener = vi.fn();

    const first = renderHook(() => useSignalsStream({ onEvent: firstListener }));
    const second = renderHook(() => useSignalsStream({ onEvent: secondListener }));

    expect(FakeEventSource.instances).toHaveLength(1);

    await act(async () => {
      await Promise.resolve();
    });
    expect(first.result.current.connected).toBe(true);
    expect(second.result.current.connected).toBe(true);

    act(() => {
      FakeEventSource.instances[0].emit({ event: 'signal_event', data: { id: 1 } });
    });

    expect(firstListener).toHaveBeenCalledTimes(1);
    expect(firstListener).toHaveBeenCalledWith('signal_event', { id: 1 });
    expect(secondListener).toHaveBeenCalledTimes(1);
    expect(first.result.current.lastEvent?.type).toBe('signal_event');
  });

  it('keeps the connection alive until the last subscriber unmounts', async () => {
    const first = renderHook(() => useSignalsStream());
    const second = renderHook(() => useSignalsStream());

    const source = FakeEventSource.instances[0];
    await act(async () => {
      await Promise.resolve();
    });
    expect(source.closeCalls).toBe(0);

    first.unmount();
    expect(source.closeCalls).toBe(0);

    second.unmount();
    expect(source.closeCalls).toBe(1);
  });
});
