// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useEffect } from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { api } from '@/lib/api';
import type { SignalEventData } from '@/lib/api/view';
import fixture from '@/lib/api/__fixtures__/commandView.sample.json';
import {
  AppStreamProvider,
  refresh,
  useAppHint,
  useCommandSection,
  useSignalEvents,
  useStreamStatus,
  type AppHintEvent,
  type CommandSectionState,
} from './AppStreamContext';

const encoder = new TextEncoder();

const EMPTY_VIEW = {
  view: 'command',
  view_version: 1,
  generated_at: '2026-09-18T07:22:01.000Z',
  degraded: false,
  sections: {},
  hints: [],
  errors: {},
};

function sectionEnvelope(version: number, value: unknown, degraded = false) {
  return {
    value,
    updated_at: '2026-09-18T07:22:01.000Z',
    freshness_s: 1,
    degraded,
    version,
  };
}

function sectionFrame(
  section: string,
  version: number,
  value: unknown,
  updatedAt = '2026-09-18T07:22:01.000Z',
) {
  return {
    event: 'view.section.changed',
    data: {
      section,
      version,
      value,
      updated_at: updatedAt,
      freshness_s: 1,
      degraded: false,
    },
    priority: 'P1',
    seq: version,
    timestamp: 1789716120000,
  };
}

function signalEventFrame() {
  return {
    event: 'signal.event',
    data: {
      event: 'SIGNAL_CREATED',
      data: { id: 'SIG-20260918-0007' },
      priority: 'P0',
      seq: 901,
      timestamp: 1789716120000,
    },
    priority: 'P1',
    seq: 43,
    timestamp: 1789716120000,
  };
}

function hintRaisedFrame() {
  return {
    event: 'hint.raised',
    data: {
      hint: {
        id: 'feed:stale:SENSEX',
        severity: 'warn',
        action_required: false,
        target: 'feed_health',
      },
    },
    priority: 'P1',
    seq: 44,
    timestamp: 1789716120000,
  };
}

function hintClearedFrame() {
  return {
    event: 'hint.cleared',
    data: { id: 'feed:stale:SENSEX' },
    priority: 'P1',
    seq: 45,
    timestamp: 1789716120000,
  };
}

function heartbeatFrame() {
  return {
    event: 'heartbeat',
    data: { status: 'ok' },
    priority: 'P2',
    seq: 99,
    timestamp: 1789716120000,
  };
}

function sseBlock(event: string, data: unknown): Uint8Array {
  return encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

type StreamHandle = {
  response: Response;
  push: (event: string, data: unknown) => void;
  pushRaw: (raw: string) => void;
};

function openStream(): StreamHandle {
  let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c;
    },
  });
  return {
    response: { ok: true, status: 200, body } as unknown as Response,
    push: (event, data) => controller?.enqueue(sseBlock(event, data)),
    pushRaw: (raw) => controller?.enqueue(encoder.encode(raw)),
  };
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function installFetch(handler: (url: string) => Response | Promise<Response>) {
  const mock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(handler(String(input))),
  );
  vi.stubGlobal('fetch', mock);
  return mock;
}

function streamFetches(mock: ReturnType<typeof installFetch>): number {
  return mock.mock.calls.filter(([input]) => String(input).includes('/api/v1/stream')).length;
}

function SectionProbe({ name }: { name: string }) {
  const section: CommandSectionState | null = useCommandSection(name);
  return (
    <div data-testid={`section-${name}`}>
      {section ? `v${section.version}` : 'none'}
    </div>
  );
}

let statusRenders = 0;

function StatusProbe({ onRender }: { onRender?: () => void } = {}) {
  const status = useStreamStatus();
  useEffect(() => {
    onRender?.();
  });
  return (
    <div data-testid="status">
      {`${status.connected ? 'up' : 'down'}:${status.reconnects}:${status.source}`}
    </div>
  );
}

function SubscriptionProbe({
  onSignal,
  onHint,
}: {
  onSignal: (payload: SignalEventData) => void;
  onHint: (event: AppHintEvent) => void;
}) {
  useSignalEvents(onSignal);
  useAppHint(onHint);
  return null;
}

beforeEach(() => {
  api.setToken(null);
  statusRenders = 0;
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(document, 'hidden');
  vi.unstubAllGlobals();
  vi.useRealTimers();
  api.setToken(null);
});

describe('AppStreamContext transport', () => {
  it('does not open a connection just by mounting the provider', async () => {
    const fetchMock = installFetch(() => jsonResponse(EMPTY_VIEW));

    await act(async () => {
      render(
        <AppStreamProvider>
          <div data-testid="child" />
        </AppStreamProvider>,
      );
    });

    expect(screen.getByTestId('child')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('parses SSE frames, applies a section delta, and ignores unparseable frames', async () => {
    api.setToken('tok-test');
    const stream = openStream();
    const fetchMock = installFetch((url) =>
      url.includes('/api/v1/stream') ? stream.response : jsonResponse(EMPTY_VIEW),
    );
    const onSignal = vi.fn();
    const onHint = vi.fn();

    await act(async () => {
      render(
        <AppStreamProvider>
          <SectionProbe name="signals" />
          <SubscriptionProbe onSignal={onSignal} onHint={onHint} />
        </AppStreamProvider>,
      );
    });

    const streamCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes('/api/v1/stream'),
    );
    expect(streamCall).toBeTruthy();
    const headers = streamCall?.[1]?.headers as Record<string, string>;
    expect(headers.Accept).toBe('text/event-stream');
    expect(headers.Authorization).toBe('Bearer tok-test');
    expect(screen.getByTestId('section-signals').textContent).toBe('none');

    await act(async () => {
      stream.pushRaw('event: connected\ndata: {"status": "ok", "message": "App stream connected"}\n\n');
      stream.pushRaw('event: view.section.changed\ndata: {not valid json}\n\n');
      stream.push('view.section.changed', { event: 'view.section.changed', data: { section: 'signals' } });
      stream.push('view.section.changed', sectionFrame('signals', 902, [{ id: 'SIG-1' }]));
      stream.push('signal.event', signalEventFrame());
      stream.push('hint.raised', hintRaisedFrame());
      stream.push('hint.cleared', hintClearedFrame());
    });

    await waitFor(() => {
      expect(screen.getByTestId('section-signals').textContent).toBe('v902');
    });
    expect(onSignal).toHaveBeenCalledTimes(1);
    expect(onSignal.mock.calls[0][0]).toMatchObject({ event: 'SIGNAL_CREATED' });
    expect(onHint).toHaveBeenCalledTimes(2);
    expect(onHint.mock.calls[0][0]).toMatchObject({ type: 'raised' });
    expect(onHint.mock.calls[1][0]).toMatchObject({ type: 'cleared', id: 'feed:stale:SENSEX' });
  });

  it('ignores an out-of-order section frame with an older version', async () => {
    const stream = openStream();
    installFetch((url) =>
      url.includes('/api/v1/stream') ? stream.response : jsonResponse(EMPTY_VIEW),
    );

    await act(async () => {
      render(
        <>
          <SectionProbe name="market-order" />
          <SectionProbe name="regime-marker" />
        </>,
      );
    });

    await act(async () => {
      stream.push('view.section.changed', sectionFrame('market-order', 5, { status: 'new' }));
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-market-order').textContent).toBe('v5');
    });

    await act(async () => {
      stream.push('view.section.changed', sectionFrame('market-order', 3, { status: 'stale' }));
      stream.push('view.section.changed', sectionFrame('regime-marker', 1, { ok: true }));
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-regime-marker').textContent).toBe('v1');
    });
    expect(screen.getByTestId('section-market-order').textContent).toBe('v5');
  });

  it('accepts a lower version when the observation timestamp is newer (backend restart)', async () => {
    const stream = openStream();
    installFetch((url) =>
      url.includes('/api/v1/stream') ? stream.response : jsonResponse(EMPTY_VIEW),
    );

    await act(async () => {
      render(<SectionProbe name="market-restart" />);
    });

    await act(async () => {
      stream.push(
        'view.section.changed',
        sectionFrame('market-restart', 42, { status: 'before' }, '2026-09-18T07:22:01.000Z'),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-market-restart').textContent).toBe('v42');
    });

    await act(async () => {
      stream.push(
        'view.section.changed',
        sectionFrame('market-restart', 1, { status: 'after-restart' }, '2026-09-18T07:25:00.000Z'),
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-market-restart').textContent).toBe('v1');
    });
  });

  it('hydrates sections from /view/command on connect and refreshes on demand', async () => {
    let viewPayload: unknown = {
      ...fixture,
      sections: {
        ...fixture.sections,
        hydration_probe: sectionEnvelope(12, { status: 'ok' }),
      },
    };
    const fetchMock = installFetch((url) =>
      url.includes('/api/v1/stream') ? openStream().response : jsonResponse(viewPayload),
    );

    await act(async () => {
      render(<SectionProbe name="market" />);
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-market').textContent).toBe('v41');
    });

    viewPayload = {
      ...fixture,
      sections: {
        ...fixture.sections,
        market: { ...fixture.sections.market, version: 42 },
      },
    };
    await act(async () => {
      await refresh();
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-market').textContent).toBe('v42');
    });

    const viewFetches = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/api/v1/view/command'),
    );
    expect(viewFetches.length).toBeGreaterThanOrEqual(2);
  });

  it('notifies only the section slice on a section update', async () => {
    const stream = openStream();
    installFetch((url) =>
      url.includes('/api/v1/stream') ? stream.response : jsonResponse(EMPTY_VIEW),
    );

    await act(async () => {
      render(
        <>
          <StatusProbe
            onRender={() => {
              statusRenders += 1;
            }}
          />
          <SectionProbe name="granularity" />
        </>,
      );
    });
    await waitFor(() => {
      expect(screen.getByTestId('status').textContent).toContain('up:');
    });
    const baseline = statusRenders;

    await act(async () => {
      stream.push('view.section.changed', sectionFrame('granularity', 1, { n: 1 }));
    });
    await waitFor(() => {
      expect(screen.getByTestId('section-granularity').textContent).toBe('v1');
    });
    expect(statusRenders).toBe(baseline);

    await act(async () => {
      stream.push('heartbeat', heartbeatFrame());
    });
    await waitFor(() => {
      expect(statusRenders).toBeGreaterThan(baseline);
    });
  });

  it('shares one connection across consumers until the last unmounts', async () => {
    const fetchMock = installFetch((url) =>
      url.includes('/api/v1/stream') ? openStream().response : jsonResponse(EMPTY_VIEW),
    );

    const first = render(<SectionProbe name="ref-a" />);
    const second = render(<SectionProbe name="ref-b" />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(streamFetches(fetchMock)).toBe(1);

    first.unmount();
    await act(async () => {
      await Promise.resolve();
    });
    expect(streamFetches(fetchMock)).toBe(1);

    second.unmount();
    await act(async () => {
      await Promise.resolve();
    });
    expect(streamFetches(fetchMock)).toBe(1);
  });

  it('reschedules failed connections with exponential backoff and jitter', async () => {
    vi.useFakeTimers();
    const fetchMock = installFetch((url) => {
      if (url.includes('/api/v1/stream')) return Promise.reject(new TypeError('network down'));
      return jsonResponse(EMPTY_VIEW);
    });

    await act(async () => {
      render(<StatusProbe />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(streamFetches(fetchMock)).toBe(1);
    expect(screen.getByTestId('status').textContent).toBe('down:1:fetch');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_300);
    });
    expect(streamFetches(fetchMock)).toBe(2);
    expect(screen.getByTestId('status').textContent).toBe('down:2:fetch');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_700);
    });
    expect(streamFetches(fetchMock)).toBe(3);
    expect(screen.getByTestId('status').textContent).toBe('down:3:fetch');
  });

  it('pauses the stream while hidden and reconnects when visible again', async () => {
    vi.useFakeTimers();
    let hidden = false;
    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => hidden,
    });

    const fetchMock = installFetch((url) =>
      url.includes('/api/v1/stream') ? openStream().response : jsonResponse(EMPTY_VIEW),
    );

    await act(async () => {
      render(<StatusProbe />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByTestId('status').textContent).toBe('up:0:sse');
    expect(streamFetches(fetchMock)).toBe(1);

    await act(async () => {
      hidden = true;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(screen.getByTestId('status').textContent).toBe('down:0:fetch');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(streamFetches(fetchMock)).toBe(1);

    await act(async () => {
      hidden = false;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(streamFetches(fetchMock)).toBe(2);
    expect(screen.getByTestId('status').textContent).toBe('up:0:sse');
  });
});
