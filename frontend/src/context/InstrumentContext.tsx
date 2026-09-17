'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type SupportedInstrument = 'NIFTY' | 'BANKNIFTY' | 'SENSEX';
export type SupportedTimeframe = '1m' | '3m' | '5m' | '15m' | '1h' | '1d';

interface InstrumentContextType {
  instrument: SupportedInstrument;
  setInstrument: (inst: SupportedInstrument) => void;
  timeframe: SupportedTimeframe;
  setTimeframe: (tf: SupportedTimeframe) => void;
  allInstruments: SupportedInstrument[];
  allTimeframes: SupportedTimeframe[];
}

const InstrumentContext = createContext<InstrumentContextType | null>(null);

const ALL_INSTRUMENTS: SupportedInstrument[] = ['NIFTY', 'BANKNIFTY', 'SENSEX'];
const ALL_TIMEFRAMES: SupportedTimeframe[] = ['1m', '3m', '5m', '15m', '1h', '1d'];

const INSTRUMENT_STORAGE_KEY = 'droid_instrument_v1';
const TIMEFRAME_STORAGE_KEY = 'droid_timeframe_v1';

function isSupportedInstrument(value: string | null): value is SupportedInstrument {
  return value !== null && (ALL_INSTRUMENTS as string[]).includes(value);
}

function isSupportedTimeframe(value: string | null): value is SupportedTimeframe {
  return value !== null && (ALL_TIMEFRAMES as string[]).includes(value);
}

export const InstrumentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [instrument, setInstrumentState] = useState<SupportedInstrument>('NIFTY');
  const [timeframe, setTimeframeState] = useState<SupportedTimeframe>('5m');

  // Hydrate the persisted selection after mount so the first client render
  // matches SSR (defaults) and can never produce a hydration mismatch.
  useEffect(() => {
    try {
      const storedInstrument = window.localStorage.getItem(INSTRUMENT_STORAGE_KEY);
      if (isSupportedInstrument(storedInstrument)) setInstrumentState(storedInstrument);
      const storedTimeframe = window.localStorage.getItem(TIMEFRAME_STORAGE_KEY);
      if (isSupportedTimeframe(storedTimeframe)) setTimeframeState(storedTimeframe);
    } catch {
      // localStorage unavailable (privacy mode) — defaults are fine.
    }
  }, []);

  const setInstrument = useCallback((inst: SupportedInstrument) => {
    setInstrumentState(inst);
    try {
      window.localStorage.setItem(INSTRUMENT_STORAGE_KEY, inst);
    } catch {
      // Persistence is best-effort.
    }
  }, []);

  const setTimeframe = useCallback((tf: SupportedTimeframe) => {
    setTimeframeState(tf);
    try {
      window.localStorage.setItem(TIMEFRAME_STORAGE_KEY, tf);
    } catch {
      // Persistence is best-effort.
    }
  }, []);

  // Stable value + stable option arrays: consumers only re-render when the
  // selection actually changes.
  const value = useMemo<InstrumentContextType>(
    () => ({
      instrument,
      setInstrument,
      timeframe,
      setTimeframe,
      allInstruments: ALL_INSTRUMENTS,
      allTimeframes: ALL_TIMEFRAMES,
    }),
    [instrument, setInstrument, timeframe, setTimeframe],
  );

  return (
    <InstrumentContext.Provider value={value}>
      {children}
    </InstrumentContext.Provider>
  );
};

export function useInstrument() {
  const ctx = useContext(InstrumentContext);
  if (!ctx) {
    throw new Error('useInstrument must be used within an InstrumentProvider');
  }
  return ctx;
}
