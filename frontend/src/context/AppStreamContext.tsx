'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import { api, API_BASE } from '@/lib/api';
import {
  parseCommandView,
  parseHeartbeatFrame,
  parseHintClearedFrame,
  parseHintRaisedFrame,
  parseSignalEventFrame,
  parseViewSectionChangedFrame,
  type AppHint,
  type CommandSectionEnvelope,
  type SignalEventData,
  type ViewSectionChangedData,
} from '@/lib/api/view';

export type CommandSectionState = {
  value: unknown;
  updated_at: string;
  freshness_s: number;
  degraded: boolean;
  version: number;
};

export type AppStreamSource = 'sse' | 'fetch';

export type AppStreamStatus = {
  connected: boolean;
  lastEventAt: number | null;
  reconnects: number;
  source: AppStreamSource;
};

export type SignalEventHandler = (payload: SignalEventData) => void;

export type AppHintEvent =
  | { type: 'raised'; hint: AppHint }
  | { type: 'cleared'; id: string };

export type AppHintHandler = (event: AppHintEvent) => void;

const MIN_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;
const IDLE_TIMEOUT_MS = 20_000;
const IDLE_CHECK_MS = 5_000;
const STREAM_PATH = '/api/v1/stream';
const COMMAND_VIEW_PATH = '/api/v1/view/command';

const INITIAL_STATUS: AppStreamStatus = {
  connected: false,
  lastEventAt: null,
  reconnects: 0,
  source: 'fetch',
};

const EMPTY_SECTION: CommandSectionState | null = null;

// ---------------------------------------------------------------------------
// Module-level refcounted store — one SSE connection per tab, shared by every
// `useCommandSection` / `useStreamStatus` / `useSignalEvents` / `useAppHint`
// consumer. The connection opens when the first consumer subscribes and closes
// when the last one unmounts. Frames are validated with the frozen zod schemas
// in `lib/api/view.ts`; unparseable frames are ignored, never fatal.
// ---------------------------------------------------------------------------

const sections = new Map<string, CommandSectionState>();
const sectionListeners = new Map<string, Set<() => void>>();
const statusListeners = new Set<() => void>();
const signalEventListeners = new Set<SignalEventHandler>();
const hintListeners = new Set<AppHintHandler>();

let statusSnapshot: AppStreamStatus = INITIAL_STATUS;
let started = false;
let refCount = 0;
let backoffMs = MIN_BACKOFF_MS;
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let idleTimer: ReturnType<typeof setInterval> | null = null;
let controller: AbortController | null = null;
let lastFrameAt = 0;
let hydrationPromise: Promise<void> | null = null;

function notify(listeners: Set<() => void>) {
  for (const subscriber of [...listeners]) {
    try {
      subscriber();
    } catch {
      // A consumer throwing must not break the stream or other consumers.
    }
  }
}

function notifySection(name: string) {
  const listeners = sectionListeners.get(name);
  if (listeners) notify(listeners);
}

function notifySignalEvent(payload: SignalEventData) {
  for (const handler of [...signalEventListeners]) {
    try {
      handler(payload);
    } catch {
      // Consumer errors must never kill the stream.
    }
  }
}

function notifyHint(event: AppHintEvent) {
  for (const handler of [...hintListeners]) {
    try {
      handler(event);
    } catch {
      // Consumer errors must never kill the stream.
    }
  }
}

function publishStatus(patch: Partial<AppStreamStatus>) {
  const next: AppStreamStatus = { ...statusSnapshot, ...patch };
  if (
    next.connected === statusSnapshot.connected &&
    next.lastEventAt === statusSnapshot.lastEventAt &&
    next.reconnects === statusSnapshot.reconnects &&
    next.source === statusSnapshot.source
  ) {
    return;
  }
  statusSnapshot = next;
  notify(statusListeners);
}

function isStaleSection(
  previous: Pick<CommandSectionState, 'version' | 'updated_at'> | undefined,
  incoming: { version: number; updated_at: string },
): boolean {
  if (!previous) return false;
  const incomingAt = Date.parse(incoming.updated_at);
  const previousAt = Date.parse(previous.updated_at);
  // Backend restarts reset section version counters to 1. A strictly newer
  // observation timestamp always wins; an older one is stale; for equal or
  // unparseable timestamps fall back to the version guard so duplicated or
  // out-of-order frames cannot regress state.
  if (Number.isFinite(incomingAt) && Number.isFinite(previousAt)) {
    if (incomingAt > previousAt) return false;
    if (incomingAt < previousAt) return true;
  }
  return incoming.version <= previous.version;
}

function applySectionChange(data: ViewSectionChangedData) {
  const previous = sections.get(data.section);
  if (isStaleSection(previous, data)) return;
  const next: CommandSectionState = {
    value: data.value,
    updated_at: data.updated_at,
    freshness_s: data.freshness_s,
    degraded: data.degraded,
    version: data.version,
  };
  sections.set(data.section, next);
  notifySection(data.section);
}

function applySectionEnvelope(name: string, envelope: CommandSectionEnvelope) {
  const previous = sections.get(name);
  if (isStaleSection(previous, envelope)) return;
  sections.set(name, { ...envelope });
  notifySection(name);
}

function handleFrameBlock(rawBlock: string) {
  let eventName = '';
  const dataLines: string[] = [];
  for (const line of rawBlock.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return;

  lastFrameAt = Date.now();
  backoffMs = MIN_BACKOFF_MS;

  let parsed: unknown;
  try {
    parsed = JSON.parse(dataLines.join('\n'));
  } catch {
    return;
  }

  switch (eventName) {
    case 'view.section.changed': {
      const frame = parseViewSectionChangedFrame(parsed);
      if (frame) applySectionChange(frame.data);
      return;
    }
    case 'signal.event': {
      const frame = parseSignalEventFrame(parsed);
      if (frame) notifySignalEvent(frame.data);
      return;
    }
    case 'hint.raised': {
      const frame = parseHintRaisedFrame(parsed);
      if (frame) notifyHint({ type: 'raised', hint: frame.data.hint });
      return;
    }
    case 'hint.cleared': {
      const frame = parseHintClearedFrame(parsed);
      if (frame) notifyHint({ type: 'cleared', id: frame.data.id });
      return;
    }
    case 'heartbeat': {
      if (parseHeartbeatFrame(parsed)) {
        // Liveness refresh only: business frames (sections/signals/hints) must
        // not wake `useStreamStatus` consumers.
        publishStatus({ lastEventAt: lastFrameAt });
      }
      return;
    }
    default:
      // `connected` and unknown future frame types are liveness-only.
      return;
  }
}

async function hydrateFromCommandView(): Promise<void> {
  try {
    const raw = await api.request<unknown>(COMMAND_VIEW_PATH);
    const view = parseCommandView(raw);
    if (!view) return;
    for (const [name, envelope] of Object.entries(view.sections)) {
      applySectionEnvelope(name, envelope);
    }
  } catch {
    // Honest state: keep whatever sections already exist.
  }
}

/**
 * Force a CommandView re-fetch (seed/recover sections). Concurrent calls share
 * one in-flight request; each call after completion triggers a fresh fetch.
 */
export function refresh(): Promise<void> {
  if (hydrationPromise) return hydrationPromise;
  hydrationPromise = hydrateFromCommandView().finally(() => {
    hydrationPromise = null;
  });
  return hydrationPromise;
}

function streamUrl(): string {
  return `${API_BASE.replace(/\/+$/, '')}${STREAM_PATH}`;
}

function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = { Accept: 'text/event-stream' };
  const token = api.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

function closeConnection() {
  const active = controller;
  controller = null;
  if (!active) return;
  try {
    active.abort();
  } catch {
    // ignore
  }
}

function clearRetry() {
  if (retryTimer) {
    clearTimeout(retryTimer);
    retryTimer = null;
  }
}

function scheduleReconnect() {
  if (!started || retryTimer) return;
  // Don't churn while the tab is hidden — visibilitychange resumes.
  if (typeof document !== 'undefined' && document.hidden) {
    publishStatus({ connected: false, source: 'fetch' });
    return;
  }
  const delay = Math.max(
    MIN_BACKOFF_MS,
    Math.min(MAX_BACKOFF_MS, backoffMs * (0.8 + Math.random() * 0.4)),
  );
  backoffMs = Math.min(MAX_BACKOFF_MS, backoffMs * 2);
  publishStatus({
    connected: false,
    source: 'fetch',
    reconnects: statusSnapshot.reconnects + 1,
  });
  retryTimer = setTimeout(() => {
    retryTimer = null;
    void connect();
  }, delay);
}

async function connect(): Promise<void> {
  if (!started) return;
  if (typeof document !== 'undefined' && document.hidden) {
    publishStatus({ connected: false, source: 'fetch' });
    return;
  }
  closeConnection();
  const request = new AbortController();
  controller = request;
  lastFrameAt = Date.now();

  let response: Response;
  try {
    response = await fetch(streamUrl(), {
      method: 'GET',
      headers: buildHeaders(),
      signal: request.signal,
      cache: 'no-store',
    });
  } catch {
    if (controller !== request) return;
    publishStatus({ connected: false, source: 'fetch' });
    scheduleReconnect();
    return;
  }
  if (controller !== request) return;

  if (!response.ok || !response.body) {
    publishStatus({ connected: false, source: 'fetch' });
    scheduleReconnect();
    return;
  }

  backoffMs = MIN_BACKOFF_MS;
  lastFrameAt = Date.now();
  publishStatus({ connected: true, source: 'sse', lastEventAt: lastFrameAt });
  void refresh();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (controller !== request) return;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        handleFrameBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }
    }
  } catch {
    // Abort or transport failure — fall through to the reconnect path.
  }

  if (controller !== request) return;
  controller = null;
  publishStatus({ connected: false, source: 'fetch' });
  scheduleReconnect();
}

function checkIdle() {
  if (!started) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  if (statusSnapshot.connected && Date.now() - lastFrameAt > IDLE_TIMEOUT_MS) {
    closeConnection();
    publishStatus({ connected: false, source: 'fetch' });
    scheduleReconnect();
  }
}

function handleVisibility() {
  if (!started) return;
  if (document.hidden) {
    closeConnection();
    clearRetry();
    publishStatus({ connected: false, source: 'fetch' });
    return;
  }
  backoffMs = MIN_BACKOFF_MS;
  clearRetry();
  void connect();
}

function handleFocus() {
  if (!started) return;
  if (typeof document !== 'undefined' && document.hidden) return;
  if (statusSnapshot.connected) return;
  backoffMs = MIN_BACKOFF_MS;
  clearRetry();
  void connect();
}

function start() {
  if (started) return;
  if (typeof window === 'undefined' || typeof fetch === 'undefined') return;
  started = true;
  backoffMs = MIN_BACKOFF_MS;
  void connect();
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibility);
  }
  window.addEventListener('focus', handleFocus);
  if (idleTimer === null) {
    idleTimer = setInterval(checkIdle, IDLE_CHECK_MS);
  }
}

function stop() {
  if (!started) return;
  started = false;
  clearRetry();
  if (idleTimer !== null) {
    clearInterval(idleTimer);
    idleTimer = null;
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', handleVisibility);
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('focus', handleFocus);
  }
  closeConnection();
  lastFrameAt = 0;
  backoffMs = MIN_BACKOFF_MS;
  publishStatus(INITIAL_STATUS);
}

function addConsumer(): () => void {
  refCount += 1;
  if (refCount === 1) start();
  return () => {
    refCount = Math.max(0, refCount - 1);
    if (refCount === 0) stop();
  };
}

function subscribeSection(name: string, subscriber: () => void): () => void {
  let listeners = sectionListeners.get(name);
  if (!listeners) {
    listeners = new Set();
    sectionListeners.set(name, listeners);
  }
  const set = listeners;
  set.add(subscriber);
  const release = addConsumer();
  return () => {
    set.delete(subscriber);
    if (set.size === 0) sectionListeners.delete(name);
    release();
  };
}

function subscribeStatus(subscriber: () => void): () => void {
  statusListeners.add(subscriber);
  const release = addConsumer();
  return () => {
    statusListeners.delete(subscriber);
    release();
  };
}

function subscribeSignalEvents(handler: SignalEventHandler): () => void {
  signalEventListeners.add(handler);
  const release = addConsumer();
  return () => {
    signalEventListeners.delete(handler);
    release();
  };
}

function subscribeHints(handler: AppHintHandler): () => void {
  hintListeners.add(handler);
  const release = addConsumer();
  return () => {
    hintListeners.delete(handler);
    release();
  };
}

function getStatusSnapshot(): AppStreamStatus {
  return statusSnapshot;
}

function getServerStatusSnapshot(): AppStreamStatus {
  return INITIAL_STATUS;
}

/** Per-section slice — any update velocity, only this section re-renders. */
export function useCommandSection(name: string): CommandSectionState | null {
  const subscribe = useCallback(
    (subscriber: () => void) => subscribeSection(name, subscriber),
    [name],
  );
  const getSnapshot = useCallback(
    () => sections.get(name) ?? EMPTY_SECTION,
    [name],
  );
  const getServerSnapshot = useCallback(() => EMPTY_SECTION, []);
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Low-frequency connection status slice — not notified by section frames. */
export function useStreamStatus(): AppStreamStatus {
  return useSyncExternalStore(
    subscribeStatus,
    getStatusSnapshot,
    getServerStatusSnapshot,
  );
}

/** `signal.event` subscription — handlers fire without re-rendering the caller. */
export function useSignalEvents(handler: SignalEventHandler): void {
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  useEffect(() => {
    const listener: SignalEventHandler = (payload) => handlerRef.current(payload);
    return subscribeSignalEvents(listener);
  }, []);
}

/** `hint.raised` / `hint.cleared` subscription — no re-render on event. */
export function useAppHint(handler: AppHintHandler): void {
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  useEffect(() => {
    const listener: AppHintHandler = (event) => handlerRef.current(event);
    return subscribeHints(listener);
  }, []);
}

export function useAppStreamRefresh(): () => Promise<void> {
  return refresh;
}

type AppStreamApi = {
  refresh: () => Promise<void>;
};

const APP_STREAM_API: AppStreamApi = { refresh };

const AppStreamContext = createContext<AppStreamApi>(APP_STREAM_API);

/**
 * Anchors the app stream in the provider tree. Mounting this provider alone
 * does not open the connection — the refcounted store connects on the first
 * consumer subscription and closes when the last consumer unmounts.
 */
export function AppStreamProvider({ children }: { children: ReactNode }) {
  return (
    <AppStreamContext.Provider value={APP_STREAM_API}>
      {children}
    </AppStreamContext.Provider>
  );
}

export function useAppStream(): AppStreamApi {
  return useContext(AppStreamContext);
}
