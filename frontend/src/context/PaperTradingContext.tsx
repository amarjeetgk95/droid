'use client';

import React, { createContext, useContext } from 'react';
import {
  usePaperTrading,
  type UsePaperTradingOptions,
  type UsePaperTradingReturn,
} from '@/hooks/usePaperTrading';

const PaperTradingContext = createContext<UsePaperTradingReturn | null>(null);

export const PaperTradingProvider: React.FC<{
  children: React.ReactNode;
  pollIntervalMs?: number;
  enabled?: boolean;
}> = ({ children, pollIntervalMs, enabled }) => {
  const value = usePaperTrading({ pollIntervalMs, enabled });
  return <PaperTradingContext.Provider value={value}>{children}</PaperTradingContext.Provider>;
};

export function usePaperTradingData(options?: UsePaperTradingOptions): UsePaperTradingReturn {
  const ctx = useContext(PaperTradingContext);
  const fallback = usePaperTrading({
    pollIntervalMs: options?.pollIntervalMs,
    enabled: ctx === null && (options?.enabled ?? true),
  });
  return ctx ?? fallback;
}

export type { UsePaperTradingReturn };
