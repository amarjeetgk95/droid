'use client';

import React, { useEffect, useCallback } from 'react';
import { useDeepInsight, DeepInsightProvider } from '@/context/DeepInsightContext';
import { DeepInsightPanel } from '@/components/ai/DeepInsightPanel';
import { RefreshCw, Bot } from 'lucide-react';

const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

function DeepInsightContent() {
  const { state, symbol, evaluate, setSymbol } = useDeepInsight();

  const handleRefresh = useCallback(() => {
    evaluate(symbol);
  }, [evaluate, symbol]);

  useEffect(() => {
    evaluate(symbol);
  }, [symbol, evaluate]);

  return (
    <div className="space-y-5 max-w-7xl mx-auto pb-8">
      {/* Top Header Bar */}
      <div className="bg-card border border-border rounded-2xl p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        {/* Symbol Selector Chips */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSymbol(sym)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                symbol === sym
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'bg-secondary/70 hover:bg-secondary text-muted-foreground hover:text-foreground'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        {/* Refresh Action */}
        <button
          onClick={handleRefresh}
          disabled={state.status === 'loading'}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${state.status === 'loading' ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Deep Insight Panel */}
      <DeepInsightPanel />
    </div>
  );
}

export default function DeepInsightPage() {
  return (
    <DeepInsightProvider>
      <DeepInsightContent />
    </DeepInsightProvider>
  );
}
