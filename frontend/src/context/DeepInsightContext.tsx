'use client';

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
import type {
  DeepInsightPayload,
  DeepInsightApiResponse,
  DeepInsightMarket,
  DeepInsightTimeframeEntry,
  DeepInsightOptionsEvidence,
  DeepInsightHistoricalEvidence,
  DeepInsightTechnicalEvidence,
  DeepInsightRisks,
  DeepInsightSetup,
  DeepInsightValidation,
  DeepInsightSignalState,
  DeepInsightProvider,
  DeepInsightDataQuality,
  DeepInsightAiView,
} from '@/lib/deep-insight-types';

interface DeepInsightState {
  status: 'idle' | 'loading' | 'success' | 'error' | 'stale' | 'expired' | 'unavailable';
  payload: DeepInsightPayload | null;
  market: DeepInsightMarket | null;
  multiTimeframe: DeepInsightTimeframeEntry[];
  aiView: DeepInsightAiView | null;
  technicalEvidence: DeepInsightTechnicalEvidence | null;
  optionsEvidence: DeepInsightOptionsEvidence | null;
  historicalEvidence: DeepInsightHistoricalEvidence | null;
  setup: DeepInsightSetup | null;
  risks: DeepInsightRisks | null;
  invalidation: string[];
  signalState: DeepInsightSignalState | null;
  dataQuality: DeepInsightDataQuality | null;
  validation: DeepInsightValidation | null;
  provider: DeepInsightProvider | null;
  lastUpdated: string | null;
  error: string | null;
}

const initialState: DeepInsightState = {
  status: 'idle',
  payload: null,
  market: null,
  multiTimeframe: [],
  aiView: null,
  technicalEvidence: null,
  optionsEvidence: null,
  historicalEvidence: null,
  setup: null,
  risks: null,
  invalidation: [],
  signalState: null,
  dataQuality: null,
  validation: null,
  provider: null,
  lastUpdated: null,
  error: null,
};

type DeepInsightAction =
  | { type: 'FETCH_START' }
  | { type: 'FETCH_SUCCESS'; payload: DeepInsightPayload }
  | { type: 'FETCH_ERROR'; error: string }
  | { type: 'SET_STALE'; message: string }
  | { type: 'SET_EXPIRED' }
  | { type: 'SET_UNAVAILABLE'; message: string }
  | { type: 'TICK' }
  | { type: 'RESET' };

function deepInsightReducer(state: DeepInsightState, action: DeepInsightAction): DeepInsightState {
  switch (action.type) {
    case 'FETCH_START':
      return { ...initialState, status: 'loading' };
    case 'FETCH_SUCCESS': {
      const p = action.payload;
      const now = new Date().toISOString();
      const signalState = p.signal_state;
      const ttlRemaining = signalState?.ttl_remaining ?? 0;

      let status: DeepInsightState['status'] = 'success';
      if (p.error) {
        status = 'error';
      } else if (signalState?.state === 'EXPIRED' || ttlRemaining <= 0) {
        status = 'expired';
      } else if (signalState?.state === 'AI_UNAVAILABLE') {
        status = 'unavailable';
      }

      return {
        ...state,
        status,
        payload: p,
        market: p.market ?? null,
        multiTimeframe: p.multi_timeframe ?? [],
        aiView: (p.ai_view && Object.keys(p.ai_view).length > 0) ? p.ai_view as DeepInsightAiView : null,
        technicalEvidence: (p.technical_evidence && Object.keys(p.technical_evidence).length > 0) ? p.technical_evidence as DeepInsightTechnicalEvidence : null,
        optionsEvidence: p.options_evidence ?? null,
        historicalEvidence: p.historical_evidence ?? null,
        setup: p.setup ?? null,
        risks: (p.risks && Object.keys(p.risks).length > 0) ? p.risks as DeepInsightRisks : null,
        invalidation: p.invalidation ?? [],
        signalState: signalState ?? null,
        dataQuality: p.data_quality ?? null,
        validation: p.validation ?? null,
        provider: p.provider ?? null,
        lastUpdated: now,
        error: p.error ?? null,
      };
    }
    case 'FETCH_ERROR':
      return { ...state, status: 'error', error: action.error };
    case 'SET_STALE':
      return { ...state, status: 'stale' };
    case 'SET_EXPIRED':
      return { ...state, status: 'expired' };
    case 'SET_UNAVAILABLE':
      return { ...state, status: 'unavailable' };
    case 'TICK': {
      if (!state.signalState || state.status !== 'success') return state;
      const newAge = state.signalState.age + 1;
      const newRemaining = Math.max(0, state.signalState.ttl - newAge);
      const updatedSignalState = { ...state.signalState, age: newAge, ttl_remaining: newRemaining };
      if (newRemaining <= 0) {
        return { ...state, status: 'expired', signalState: updatedSignalState };
      }
      return { ...state, signalState: updatedSignalState };
    }
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

interface DeepInsightContextValue {
  state: DeepInsightState;
  symbol: string;
  refresh: (symbol?: string) => Promise<void>;
  evaluate: (symbol?: string) => Promise<void>;
  setSymbol: (symbol: string) => void;
  reset: () => void;
}

const DeepInsightContext = createContext<DeepInsightContextValue | null>(null);

export function DeepInsightProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(deepInsightReducer, initialState);
  const [symbol, setSymbolState] = React.useState('NIFTY');
  const abortControllerRef = useRef<AbortController | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const tickIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const setSymbol = useCallback((s: string) => {
    setSymbolState(s);
  }, []);

  const refresh = useCallback(async (sym?: string) => {
    const targetSymbol = sym || symbol;
    dispatch({ type: 'FETCH_START' });

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/deep-insight/${targetSymbol}`, {
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: DeepInsightApiResponse = await response.json();

      if (data.error && !data.data) {
        throw new Error(data.error);
      }

      dispatch({ type: 'FETCH_SUCCESS', payload: data.data });
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      const msg = err instanceof Error ? err.message : 'Unknown error';
      dispatch({ type: 'FETCH_ERROR', error: msg });
    }
  }, [symbol]);

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    if (tickIntervalRef.current) {
      clearInterval(tickIntervalRef.current);
      tickIntervalRef.current = null;
    }
    dispatch({ type: 'RESET' });
  }, []);

  // Auto-refresh every 10s when active
  useEffect(() => {
    if (state.status === 'success' && state.signalState?.state === 'ACTIVE') {
      pollIntervalRef.current = setInterval(() => {
        refresh();
      }, 10000);
    } else if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [state.status, state.signalState?.state, refresh]);

  // Tick every second to update age/remaining
  useEffect(() => {
    if (state.status === 'success' && state.signalState?.state === 'ACTIVE') {
      tickIntervalRef.current = setInterval(() => {
        dispatch({ type: 'TICK' });
      }, 1000);
    } else if (tickIntervalRef.current) {
      clearInterval(tickIntervalRef.current);
      tickIntervalRef.current = null;
    }
    return () => {
      if (tickIntervalRef.current) {
        clearInterval(tickIntervalRef.current);
      }
    };
  }, [state.status, state.signalState?.state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (tickIntervalRef.current) clearInterval(tickIntervalRef.current);
    };
  }, []);

  return (
    <DeepInsightContext.Provider value={{ state, symbol, refresh, evaluate: refresh, setSymbol, reset }}>
      {children}
    </DeepInsightContext.Provider>
  );
}

export function useDeepInsight() {
  const ctx = useContext(DeepInsightContext);
  if (!ctx) throw new Error('useDeepInsight must be used within DeepInsightProvider');
  return ctx;
}
