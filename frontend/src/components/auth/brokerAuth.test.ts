// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { openBrokerAuth } from '@/lib/brokerAuth';

const APP_ORIGIN = 'http://localhost:3000';

// happy-dom exposes setURL at runtime but not in the standard Window type.
function setTestUrl(url: string): void {
  const w = window as unknown as { happyDOM?: { setURL: (value: string) => void } };
  if (!w.happyDOM) {
    throw new Error('happy-dom setURL is unavailable in this test environment');
  }
  w.happyDOM.setURL(url);
}
const BACKEND_ORIGIN = 'http://127.0.0.1:8000';
const LOGIN_URL = `${BACKEND_ORIGIN}/api/v1/tokens/fyers/login`;

type FakePopup = { closed: boolean; close: ReturnType<typeof vi.fn> };

function fakePopup(closed = false): FakePopup {
  return { closed, close: vi.fn() };
}

describe('openBrokerAuth', () => {
  const openMock = vi.fn();
  const cleanups: Array<() => void> = [];

  beforeEach(() => {
    setTestUrl(`${APP_ORIGIN}/war-room`);
    localStorage.clear();
    sessionStorage.clear();
    vi.useFakeTimers();
    openMock.mockReset();
    vi.stubGlobal('open', openMock);
  });

  afterEach(() => {
    for (const cleanup of cleanups.splice(0)) cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('does NOT report success when the popup closes without a callback marker (cancelled login)', () => {
    const popup = fakePopup();
    openMock.mockReturnValue(popup);
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    const authEvents = vi.fn();
    window.addEventListener('broker:authenticated', authEvents);

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onSuccess, onClose });
    cleanups.push(cleanup);

    popup.closed = true;
    vi.advanceTimersByTime(700);

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(authEvents).not.toHaveBeenCalled();
    window.removeEventListener('broker:authenticated', authEvents);
  });

  it('accepts a fresh localStorage marker for the SAME provider as success', () => {
    const popup = fakePopup();
    openMock.mockReturnValue(popup);
    const onSuccess = vi.fn();

    localStorage.setItem('droid_last_auth_time', String(Date.now()));
    localStorage.setItem('droid_last_auth_provider', 'fyers');

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onSuccess });
    cleanups.push(cleanup);

    popup.closed = true;
    vi.advanceTimersByTime(700);

    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('ignores a fresh marker written for a DIFFERENT provider', () => {
    const popup = fakePopup();
    openMock.mockReturnValue(popup);
    const onSuccess = vi.fn();
    const onClose = vi.fn();

    localStorage.setItem('droid_last_auth_time', String(Date.now()));
    localStorage.setItem('droid_last_auth_provider', 'zerodha');

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onSuccess, onClose });
    cleanups.push(cleanup);

    popup.closed = true;
    vi.advanceTimersByTime(700);

    expect(onSuccess).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('accepts a success message only from the app or broker-login origin', () => {
    const popup = fakePopup();
    openMock.mockReturnValue(popup);
    const onSuccess = vi.fn();

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onSuccess });
    cleanups.push(cleanup);

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'DROID_AUTH_SUCCESS' },
        origin: 'https://evil.example',
      }),
    );
    expect(onSuccess).not.toHaveBeenCalled();

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'DROID_AUTH_SUCCESS' },
        origin: BACKEND_ORIGIN,
      }),
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('validates origin on the BroadcastChannel listener too', () => {
    class FakeBroadcastChannel {
      static instances: FakeBroadcastChannel[] = [];
      onmessage: ((event: MessageEvent) => void) | null = null;

      constructor(public readonly name: string) {
        FakeBroadcastChannel.instances.push(this);
      }

      postMessage() {}
      close() {}
    }
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel);

    const popup = fakePopup();
    openMock.mockReturnValue(popup);
    const onSuccess = vi.fn();

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onSuccess });
    cleanups.push(cleanup);

    const channel = FakeBroadcastChannel.instances[FakeBroadcastChannel.instances.length - 1];
    expect(channel).toBeDefined();

    channel.onmessage?.(
      new MessageEvent('message', {
        data: { type: 'BROKER_AUTHENTICATED' },
        origin: 'https://evil.example',
      }),
    );
    expect(onSuccess).not.toHaveBeenCalled();

    channel.onmessage?.(new MessageEvent('message', { data: { type: 'BROKER_AUTHENTICATED' }, origin: '' }));
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('surfaces a blocked popup instead of failing silently', () => {
    openMock.mockReturnValue(null);
    const onError = vi.fn();

    const cleanup = openBrokerAuth({ provider: 'fyers', loginUrl: LOGIN_URL, onError });
    cleanups.push(cleanup);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toMatch(/Popup was blocked/);
  });
});
