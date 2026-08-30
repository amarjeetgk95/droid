'use client';

import { useState, useEffect } from 'react';
import { MarketHealthStatus } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { api } from '@/lib/api';
import { X, Activity, Server, Radio, ShieldCheck, Zap, Database, RefreshCw } from 'lucide-react';

export function MarketHealthModal({
  isOpen,
  onClose,
  health,
  streamState,
}: {
  isOpen: boolean;
  onClose: () => void;
  health: MarketHealthStatus | null;
  streamState: StreamConnectionState;
}) {
  const [cacheStats, setCacheStats] = useState<Record<string, unknown> | null>(null);
  const [pipelineStats, setPipelineStats] = useState<{ timeseries_store: Record<string, unknown>; write_pipeline: Record<string, unknown> } | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    const fetchTelemetry = async () => {
      try {
        const [cRes, pRes] = await Promise.all([
          api.getCacheStats(),
          api.getPipelineStats(),
        ]);
        if (!isMounted) return;
        setCacheStats(cRes.data);
        setPipelineStats(pRes.data);
      } catch {
        // Ignore background telemetry errors
      }
    };

    fetchTelemetry();
    const interval = setInterval(fetchTelemetry, 3000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isOpen]);

  const handleResetCircuitBreaker = async () => {
    setActionLoading(true);
    try {
      await api.resetCircuitBreaker();
    } catch {
      // Ignore
    } finally {
      setActionLoading(false);
    }
  };

  const handleClearCache = async () => {
    setActionLoading(true);
    try {
      await api.clearCache();
      const cRes = await api.getCacheStats();
      setCacheStats(cRes.data);
    } catch {
      // Ignore
    } finally {
      setActionLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-xl shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border bg-muted/40">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            <h2 className="font-bold text-base text-foreground">High-Frequency & Ingestion Telemetry</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-5 text-sm max-h-[80vh] overflow-y-auto">
          {/* Main Status Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="bg-secondary/70 p-3 rounded-lg border border-border">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                <Server className="w-3.5 h-3.5 text-primary" /> Provider
              </span>
               <p className="font-bold text-foreground capitalize">{health?.provider || 'Fyers'}</p>
              <span className="text-[10px] bg-amber-500/20 text-amber-400 px-1.5 py-0.5 rounded font-mono">
                {health?.mode || 'DEMO'}
              </span>
            </div>

            <div className="bg-secondary/70 p-3 rounded-lg border border-border">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                <Radio className="w-3.5 h-3.5 text-success" /> Feed Stream
              </span>
              <p className={`font-bold ${streamState === 'CONNECTED' ? 'text-success' : 'text-warning'}`}>
                {streamState}
              </p>
              <span className="text-[10px] text-muted-foreground">
                Reconnects: {health?.reconnect_count ?? 0}
              </span>
            </div>

            <div className="bg-secondary/70 p-3 rounded-lg border border-border sm:col-span-1 col-span-2">
              <span className="text-xs text-muted-foreground flex items-center gap-1.5 mb-1">
                <ShieldCheck className="w-3.5 h-3.5 text-primary" /> Circuit Breaker
              </span>
              <p className={`font-bold ${health?.circuit_breaker_state === 'OPEN' ? 'text-destructive' : 'text-foreground'}`}>
                {health?.circuit_breaker_state || 'CLOSED'}
              </p>
              <span className="text-[10px] text-success">Active Protection</span>
            </div>
          </div>

          {/* Buffer & Queue Metrics */}
          <div className="border border-border rounded-lg p-4 bg-muted/20 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-warning" /> High-Frequency Ring Buffer
              </span>
              <span className="text-xs text-muted-foreground font-mono">
                Depth: {health?.buffer_depth ?? 0} / 10,000
              </span>
            </div>

            <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
              <div
                className="bg-primary h-full transition-all duration-300"
                style={{ width: `${Math.min(100, ((health?.buffer_depth ?? 0) / 10000) * 100)}%` }}
              />
            </div>

            <div className="flex justify-between text-xs text-muted-foreground pt-1">
              <span>Subscriptions: {health?.subscriptions ?? 4}</span>
              <span>Dropped Events: {health?.dropped_events ?? 0}</span>
            </div>
          </div>

          {/* Phase 3 Infrastructure: Cache & Time-Series Batch Pipeline */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="border border-border rounded-lg p-3 bg-muted/20 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground flex items-center gap-1">
                  <Database className="w-3.5 h-3.5 text-primary" /> LRU Cache Layer
                </span>
                <button
                  onClick={handleClearCache}
                  disabled={actionLoading}
                  className="text-[10px] text-muted-foreground hover:text-foreground cursor-pointer"
                >
                  Flush
                </button>
              </div>
              <div className="text-xs space-y-1 text-muted-foreground">
                <div className="flex justify-between">
                  <span>Hit Ratio:</span>
                  <span className="font-mono font-medium text-foreground">
                    {cacheStats?.hit_ratio_percent !== undefined ? `${cacheStats.hit_ratio_percent}%` : 'N/A'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Cached Items:</span>
                  <span className="font-mono font-medium text-foreground">
                    {String(cacheStats?.items_count ?? 0)}
                  </span>
                </div>
              </div>
            </div>

            <div className="border border-border rounded-lg p-3 bg-muted/20 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground flex items-center gap-1">
                  <RefreshCw className="w-3.5 h-3.5 text-success" /> Batch Pipeline
                </span>
              </div>
              <div className="text-xs space-y-1 text-muted-foreground">
                <div className="flex justify-between">
                  <span>Write Queue:</span>
                  <span className="font-mono font-medium text-foreground">
                    {String(pipelineStats?.write_pipeline?.queue_depth ?? 0)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Total Flushed:</span>
                  <span className="font-mono font-medium text-foreground">
                    {String(pipelineStats?.write_pipeline?.total_flushed ?? 0)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Timing & Heartbeats */}
          <div className="grid grid-cols-2 gap-4 text-xs border-t border-border pt-3">
            <div>
              <span className="text-muted-foreground">Data Age:</span>
              <span className="font-mono font-medium ml-1.5 text-foreground">
                {health?.data_age_seconds !== null && health?.data_age_seconds !== undefined
                  ? `${health.data_age_seconds}s`
                  : 'N/A'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-muted-foreground">Network Latency:</span>
              <span className="font-mono font-medium ml-1.5 text-foreground">
                {health?.latency_ms ? `${health.latency_ms}ms` : 'N/A (Demo)'}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border bg-muted/40 flex items-center justify-between">
          <button
            onClick={handleResetCircuitBreaker}
            disabled={actionLoading}
            className="px-3 py-1.5 rounded-md bg-secondary hover:bg-secondary/80 text-foreground font-medium text-xs transition-colors cursor-pointer"
          >
            Reset Breaker
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 font-medium text-xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
