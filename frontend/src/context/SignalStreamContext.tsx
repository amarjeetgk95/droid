'use client';

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';
import { useSignalsStream, type SignalsStreamEvent } from '@/hooks/useSignalsStream';

interface SignalStreamContextType {
  connected: boolean;
  lastEvent: SignalsStreamEvent | null;
  events: SignalsStreamEvent[];
  clearEvents: () => void;
}

export const SignalStreamContext = createContext<SignalStreamContextType | null>(null);

/**
 * Single owner of the signals SSE subscription. `useSignalsStream` is itself a
 * refcounted module-level singleton, so even raw-hook consumers share this
 * provider's connection — this component only owns the event buffer.
 */
export const SignalStreamProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [events, setEvents] = useState<SignalsStreamEvent[]>([]);

  const handleEvent = useCallback((evt: string, data: unknown) => {
    const streamEvent: SignalsStreamEvent = {
      type: evt,
      data,
      at: new Date(),
    };
    setEvents((prev) => [streamEvent, ...prev.slice(0, 49)]); // Keep last 50 events
  }, []);

  const { connected, lastEvent } = useSignalsStream({ onEvent: handleEvent });

  const clearEvents = useCallback(() => setEvents([]), []);

  // Memoized so an event-buffer update doesn't churn consumers that only read
  // `connected`/`clearEvents` — identity changes only when values change.
  const value = useMemo<SignalStreamContextType>(
    () => ({
      connected,
      lastEvent,
      events,
      clearEvents,
    }),
    [connected, lastEvent, events, clearEvents],
  );

  return <SignalStreamContext.Provider value={value}>{children}</SignalStreamContext.Provider>;
};

export function useSignalStreamContext() {
  const ctx = useContext(SignalStreamContext);
  if (!ctx) {
    throw new Error('useSignalStreamContext must be used within a SignalStreamProvider');
  }
  return ctx;
}

export const useSignalStream = useSignalStreamContext;
