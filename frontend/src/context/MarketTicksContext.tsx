'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useMarketStream, type TimestampedTick, type StreamConnectionState } from '@/hooks/useMarketStream';

export type MarketTicksValue = {
  streamState: StreamConnectionState;
  latestTicks: Record<string, TimestampedTick>;
  ticksFresh: boolean;
  lastTickAt: Date | null;
  reconnectCount: number;
};

const MarketTicksContext = createContext<MarketTicksValue>({
  streamState: 'CONNECTING',
  latestTicks: {},
  ticksFresh: false,
  lastTickAt: null,
  reconnectCount: 0,
});

/**
 * Mounts the market-feed WebSocket exactly once per tab and shares the live
 * tick map with every consumer. Previously `useMarketStream` was defined but
 * never mounted anywhere, so the browser never opened
 * `/api/v1/ws/market-feed` and no realtime ticks ever loaded.
 */
export function MarketTicksProvider({ children }: { children: ReactNode }) {
  const value = useMarketStream();
  return <MarketTicksContext.Provider value={value}>{children}</MarketTicksContext.Provider>;
}

export function useMarketTicks(): MarketTicksValue {
  return useContext(MarketTicksContext);
}
