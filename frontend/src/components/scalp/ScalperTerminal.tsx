'use client';

import { useState, useEffect, useCallback } from 'react';
import { ScalperChart } from './ScalperChart';
import { QuickScalpTicket } from './QuickScalpTicket';
import { ScalpAlertsHUD } from './ScalpAlertsHUD';
import { ActiveScalpPositions } from './ActiveScalpPositions';
import { api } from '@/lib/api';

export function ScalperTerminal() {
  const [underlying, setUnderlying] = useState<'NIFTY' | 'BANKNIFTY' | 'SENSEX'>('NIFTY');
  const [spotPrice, setSpotPrice] = useState<number>(24500.0);
  const [timeframe, setTimeframe] = useState<'1m' | '3m' | '5m'>('1m');
  const [positionsTrigger, setPositionsTrigger] = useState<number>(0);

  const fetchQuote = useCallback(async () => {
    try {
      const sym = underlying === 'NIFTY' ? 'NIFTY 50' : underlying;
      const res = await api.getQuote(sym);
      if (res.data?.ltp && res.data.ltp > 0) {
        setSpotPrice(res.data.ltp);
      }
    } catch {
      // ignore poll error
    }
  }, [underlying]);

  useEffect(() => {
    fetchQuote();
    const interval = setInterval(fetchQuote, 3000); // 3s quote refresh
    return () => clearInterval(interval);
  }, [fetchQuote]);

  const handleOrderExecuted = useCallback(() => {
    setPositionsTrigger((prev) => prev + 1);
  }, []);

  const handleExecuteSignal = useCallback(async (signalId: string) => {
    try {
      await api.executeSignalPaper(signalId);
      setPositionsTrigger((prev) => prev + 1);
    } catch {
      // toast handled in subcomponents
    }
  }, []);

  return (
    <div className="flex flex-col gap-3 min-h-[calc(100vh-120px)] select-none">
      {/* Upper Grid: Left = 1M Chart, Right = Quick Ticket + Fast Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 flex-1 min-h-[500px]">
        {/* Main Chart Column (7 cols on lg) */}
        <div className="lg:col-span-7 xl:col-span-8 flex flex-col h-full min-h-[380px]">
          <ScalperChart
            symbol={underlying === 'NIFTY' ? 'NIFTY 50' : underlying}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
            spotPrice={spotPrice}
          />
        </div>

        {/* Scalp Tools Column (5 cols on lg) */}
        <div className="lg:col-span-5 xl:col-span-4 flex flex-col gap-3">
          <QuickScalpTicket
            underlying={underlying}
            spotPrice={spotPrice}
            onUnderlyingChange={setUnderlying}
            onOrderPlaced={handleOrderExecuted}
          />

          <div className="flex-1 min-h-[220px]">
            <ScalpAlertsHUD
              currentSpot={spotPrice}
              onExecuteSignal={handleExecuteSignal}
            />
          </div>
        </div>
      </div>

      {/* Bottom Span: Active Scalp Positions with Panic Square-Off All */}
      <div className="w-full">
        <ActiveScalpPositions
          refreshTrigger={positionsTrigger}
          onPositionsUpdated={handleOrderExecuted}
        />
      </div>
    </div>
  );
}
