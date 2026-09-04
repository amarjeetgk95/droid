'use client';

import React, { createContext, useContext, useReducer, useCallback, useEffect, useRef } from 'react';

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
import type {
  DeepInsightState,
  DeepInsightApiResponse,
  DeepInsightSignal,
  DeepInsightMarket,
  DeepInsightTimeframe,
  DeepInsightOptions,
  DeepInsightHistorical,
  DeepInsightEvidence,
  DeepInsightRisk,
  DeepInsightSetup,
  DeepInsightValidation,
  DeepInsightExecution,
  DeepInsightProvider,
  DeepInsightDataQuality,
  DeepInsightDecision,
  DeepInsightRegime,
  DeepInsightDirection,
  DeepInsightVolatility,
  DeepInsightSetupType,
} from '@/lib/deep-insight-types';

type DeepInsightAction =
  | { type: 'FETCH_START'; symbol: string }
  | { type: 'FETCH_SUCCESS'; payload: DeepInsightApiResponse; symbol: string }
  | { type: 'FETCH_ERROR'; error: string }
  | { type: 'SET_STALE'; message: string }
  | { type: 'SET_EXPIRED' }
  | { type: 'SET_UNAVAILABLE'; message: string }
  | { type: 'TICK' }
  | { type: 'RESET' };

const initialState: DeepInsightState = {
  status: 'idle',
  market: null,
  signal: null,
  multiTimeframe: [],
  options: null,
  historical: null,
  evidence: null,
  risk: null,
  setup: null,
  validation: null,
  execution: null,
  provider: null,
  dataQuality: null,
  lastUpdated: null,
  error: null,
  staleMessage: null,
};

function deepInsightReducer(state: DeepInsightState, action: DeepInsightAction): DeepInsightState {
  switch (action.type) {
    case 'FETCH_START':
      return {
        ...initialState,
        status: 'loading',
      };
    case 'FETCH_SUCCESS': {
      const { signal, execution } = action.payload.data;
      const now = new Date().toISOString();
      const signalTime = new Date(signal.timestamp);
      const age = Math.floor((Date.now() - signalTime.getTime()) / 1000);
      const ttlRemaining = signal.expires_at
        ? Math.max(0, Math.floor((new Date(signal.expires_at).getTime() - Date.now()) / 1000))
        : signal.ttl_seconds - age;

      return {
        ...state,
        status: 'success',
        signal: mapSignal(signal, age, ttlRemaining),
        execution: mapExecution(execution),
        validation: mapValidation(signal),
        provider: mapProvider(signal),
        setup: mapSetup(signal),
        risk: mapRisk(signal),
        evidence: mapEvidence(signal),
        lastUpdated: now,
        error: null,
        staleMessage: null,
      };
    }
    case 'FETCH_ERROR':
      return {
        ...state,
        status: 'error',
        error: action.error,
      };
    case 'SET_STALE':
      return {
        ...state,
        status: 'stale',
        staleMessage: action.message,
      };
    case 'SET_EXPIRED':
      return {
        ...state,
        status: 'expired',
      };
    case 'SET_UNAVAILABLE':
      return {
        ...state,
        status: 'unavailable',
        error: action.message,
      };
    case 'TICK': {
      if (!state.signal || state.status !== 'success') return state;
      const age = state.signal.age + 1;
      const ttlRemaining = Math.max(0, state.signal.ttl - age);
      if (ttlRemaining <= 0) {
        return { ...state, status: 'expired' };
      }
      return {
        ...state,
        signal: { ...state.signal, age, ttlRemaining },
      };
    }
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

function mapSignal(
  s: DeepInsightApiResponse['data']['signal'],
  age: number,
  ttlRemaining: number
): DeepInsightSignal {
  return {
    signalId: s.signal_id,
    symbol: s.symbol,
    timestamp: s.timestamp,
    state: ttlRemaining <= 0 ? 'EXPIRED' : 'ACTIVE',
    age,
    ttl: s.ttl_seconds,
    ttlRemaining,
    regime: s.regime as DeepInsightRegime,
    direction: s.direction as DeepInsightDirection,
    volatility: 'NORMAL' as DeepInsightVolatility,
    aiBias: s.decision as DeepInsightDecision,
    confidence: s.raw_confidence,
    calibratedConfidence: s.calibrated_confidence || s.raw_confidence,
    setupType: s.setup_type as DeepInsightSetupType,
    timeframe: '5M',
  };
}

function mapExecution(e: DeepInsightApiResponse['data']['execution']): DeepInsightExecution {
  return {
    decision: e.decision,
    reasonCode: e.reason_code,
    reasonDetail: e.reason_detail,
  };
}

function mapValidation(s: DeepInsightApiResponse['data']['signal']): DeepInsightValidation {
  return {
    decision: s.validation_result,
    rejectionReason: s.rejection_reason_code,
    rejectionDetail: s.rejection_detail,
  };
}

function mapProvider(s: DeepInsightApiResponse['data']['signal']): DeepInsightProvider {
  return {
    name: s.provider || 'AI Engine',
    model: s.model || 'Configured model',
    latencyMs: s.latency_ms,
  };
}

function mapSetup(s: DeepInsightApiResponse['data']['signal']): DeepInsightSetup {
  const entry = s.entry;
  const stop = s.stop_loss;
  const target = s.target;
  const risk = Math.abs(entry - stop);
  const reward = Math.abs(target - entry);
  const rr = risk > 0 ? reward / risk : 0;

  return {
    entryZone: `${entry.toFixed(0)}`,
    stopLoss: stop,
    target: `${target.toFixed(0)}`,
    riskReward: parseFloat(rr.toFixed(1)),
    setupType: s.setup_type as DeepInsightSetupType,
  };
}

function mapRisk(s: DeepInsightApiResponse['data']['signal']): DeepInsightRisk {
  return {
    mainRisks: s.invalidation.slice(0, 3),
    invalidation: s.rejection_reason_code
      ? [`Rejection: ${s.rejection_reason_code}`]
      : [],
  };
}

function mapEvidence(s: DeepInsightApiResponse['data']['signal']): DeepInsightEvidence {
  return {
    positive: s.reasons.slice(0, 4),
    supporting: s.reasons.slice(4, 8),
  };
}

interface DeepInsightContextValue {
  state: DeepInsightState;
  symbol: string;
  evaluate: (symbol?: string, regimeHint?: string) => Promise<void>;
  setSymbol: (symbol: string) => void;
  reset: () => void;
}

const DeepInsightContext = createContext<DeepInsightContextValue | null>(null);

export function DeepInsightProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(deepInsightReducer, initialState);
  const [symbol, setSymbolState] = React.useState('NIFTY');
  const abortControllerRef = useRef<AbortController | null>(null);
  const tickIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const setSymbol = useCallback((s: string) => {
    setSymbolState(s);
  }, []);

  const evaluate = useCallback(async (sym?: string, regimeHint?: string) => {
    const targetSymbol = sym || symbol;
    dispatch({ type: 'FETCH_START', symbol: targetSymbol });

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch(`${API_BASE}/api/v1/ai/v2/evaluate/${targetSymbol}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: targetSymbol,
          regime_hint: regimeHint,
        }),
        signal: abortControllerRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data: DeepInsightApiResponse = await response.json();

      if (data.error) {
        throw new Error(data.error);
      }

      dispatch({ type: 'FETCH_SUCCESS', payload: data, symbol: targetSymbol });
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
    if (tickIntervalRef.current) {
      clearInterval(tickIntervalRef.current);
      tickIntervalRef.current = null;
    }
    dispatch({ type: 'RESET' });
  }, []);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (tickIntervalRef.current) {
        clearInterval(tickIntervalRef.current);
      }
    };
  }, []);

  return (
    <DeepInsightContext.Provider value={{ state, symbol, evaluate, setSymbol, reset }}>
      {children}
    </DeepInsightContext.Provider>
  );
}

export function useDeepInsight() {
  const ctx = useContext(DeepInsightContext);
  if (!ctx) throw new Error('useDeepInsight must be used within DeepInsightProvider');
  return ctx;
}
