'use client';

import React, { useEffect, useCallback } from 'react';
import { useDeepInsight, DeepInsightProvider } from '@/context/DeepInsightContext';
import { DeepInsightPanel } from '@/components/ai/DeepInsightPanel';
import { RefreshCw, ShieldCheck, ShieldAlert, Clock } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

function DeepInsightToolbar() {
  const { state, symbol, evaluate, setSymbol } = useDeepInsight();

  const handleRefresh = useCallback(() => {
    evaluate(symbol);
  }, [evaluate, symbol]);

  const spot = state.market?.levels?.current_price;
  const regime = state.market?.regime;
  const bias = state.aiView?.bias;
  const valStatus = state.validation?.status;
  const ttlRemaining = state.signalState?.ttl_remaining ?? 0;

  return (
    <div className="bg-card/70 backdrop-blur-md border border-border/80 rounded-xl px-3.5 py-1.5 flex flex-wrap items-center justify-between gap-2.5 shadow-xs shrink-0">
      {/* Left: Symbol Chips + Live Spot Quote */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1 bg-muted/60 p-0.5 rounded-lg border border-border/40">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSymbol(sym)}
              className={`px-3 py-1 rounded-md text-xs font-bold transition-all cursor-pointer ${
                symbol === sym
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'text-muted-foreground hover:text-foreground hover:bg-background/60'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        {spot && (
          <div className="hidden sm:flex items-center gap-2 pl-2 border-l border-border/60">
            <span className="text-[11px] text-muted-foreground font-medium">{symbol}</span>
            <span className="text-sm font-bold font-mono text-foreground tabular-nums">
              {spot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {regime && regime !== 'UNKNOWN' && (
              <Badge variant="outline" className="text-[10px] font-semibold tracking-wider uppercase h-4.5 px-1.5">
                {regime}
              </Badge>
            )}
          </div>
        )}
      </div>

      {/* Right: Quick Telemetry Pills + Refresh */}
      <div className="flex items-center gap-2">
        {bias && (
          <Badge
            variant={bias === 'LONG' ? 'success' : bias === 'SHORT' ? 'destructive' : 'secondary'}
            className="text-[11px] font-bold px-2 py-0.5"
          >
            AI: {bias}
          </Badge>
        )}

        {valStatus && (
          <div className="hidden md:flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border border-border/60 bg-muted/40 font-medium">
            {valStatus === 'ACCEPT' || valStatus === 'PASS' ? (
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
            ) : (
              <ShieldAlert className="w-3.5 h-3.5 text-red-500 shrink-0" />
            )}
            <span className="text-muted-foreground">Validation:</span>
            <span className={valStatus === 'ACCEPT' || valStatus === 'PASS' ? 'text-emerald-500 font-semibold' : 'text-red-500 font-semibold'}>
              {valStatus}
            </span>
          </div>
        )}

        {state.signalState && (
          <div className="hidden lg:flex items-center gap-1 text-[11px] text-muted-foreground">
            <Clock className="w-3 h-3 text-muted-foreground" />
            <span>TTL: {ttlRemaining}s</span>
          </div>
        )}

        <button
          onClick={handleRefresh}
          disabled={state.status === 'loading'}
          title="Refresh AI analysis"
          className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold transition-all cursor-pointer shadow-xs disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${state.status === 'loading' ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>
    </div>
  );
}

function DeepInsightContent() {
  const { symbol, evaluate } = useDeepInsight();

  useEffect(() => {
    evaluate(symbol);
  }, [symbol, evaluate]);

  return (
    <div className="h-[calc(100vh-8rem)] min-h-[560px] flex flex-col min-h-0 gap-2">
      <DeepInsightToolbar />
      <div className="flex-1 min-h-0">
        <DeepInsightPanel />
      </div>
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
