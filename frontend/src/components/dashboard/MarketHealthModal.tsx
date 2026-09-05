'use client';

import { useState, useEffect } from 'react';
import { MarketHealthStatus } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { api } from '@/lib/api';
import { Activity, Server, Radio, ShieldCheck, Zap, Database, RefreshCw, KeyRound, ExternalLink } from 'lucide-react';
import { safeStr } from '@/lib/utils';
import { getStoredSettings } from '@/lib/settings';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

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
  const [tokenStatus, setTokenStatus] = useState<Record<string, unknown> | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeBroker, setActiveBroker] = useState<string>('fyers');

  useEffect(() => {
    try {
      const stored = getStoredSettings();
      if (stored?.broker?.provider) setActiveBroker(stored.broker.provider);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    let delay = 3000;
    let timeout: ReturnType<typeof setTimeout> | null = null;

    const fetchTelemetry = async () => {
      try {
        const [cRes, pRes, tRes] = await Promise.all([
          api.getCacheStats(),
          api.getPipelineStats(),
          api.getTokenStatus(),
        ]);
        if (!isMounted) return;
        setCacheStats(cRes.data);
        setPipelineStats(pRes.data);
        setTokenStatus(tRes.data);
        delay = 3000;
      } catch {
        delay = Math.min(30000, delay * 2);
      } finally {
        if (!isMounted) return;
        timeout = setTimeout(fetchTelemetry, delay + Math.random() * 500);
      }
    };

    fetchTelemetry();
    return () => {
      isMounted = false;
      if (timeout) clearTimeout(timeout);
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

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] flex flex-col gap-0 p-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="p-4 border-b border-border bg-secondary/30">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-primary" />
            <DialogTitle className="font-bold text-sm text-foreground">
              High-Frequency &amp; Ingestion Telemetry
            </DialogTitle>
          </div>
        </DialogHeader>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs overflow-y-auto flex-1">
          {/* Main Status Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            <div className="bg-secondary/50 p-2.5 rounded-lg border border-border">
              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
                <Server className="w-3.5 h-3.5 text-primary" /> Provider
              </span>
              <p className="font-bold text-foreground capitalize">{safeStr(health?.provider, '—')}</p>
              <span className="text-[10px] bg-amber-500/15 text-amber-600 dark:text-amber-400 px-1.5 py-0.2 rounded font-mono">
                {health?.mode || 'OFFLINE'}
              </span>
            </div>

            <div className="bg-secondary/50 p-2.5 rounded-lg border border-border">
              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
                <Radio className="w-3.5 h-3.5 text-success" /> Feed Stream
              </span>
              <p className={`font-bold ${streamState === 'CONNECTED' ? 'text-success' : 'text-warning'}`}>
                {streamState}
              </p>
              <span className="text-[10px] text-muted-foreground">
                Reconnects: {health?.reconnect_count ?? 0}
              </span>
            </div>

            <div className="bg-secondary/50 p-2.5 rounded-lg border border-border sm:col-span-1 col-span-2">
              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
                <ShieldCheck className="w-3.5 h-3.5 text-primary" /> Circuit Breaker
              </span>
              <p className={`font-bold ${health?.circuit_breaker_state === 'OPEN' ? 'text-destructive' : 'text-foreground'}`}>
                {health?.circuit_breaker_state || 'CLOSED'}
              </p>
              <span className="text-[10px] text-emerald-600 dark:text-emerald-400">Active Protection</span>
            </div>
          </div>

          {/* Broker Auth Status */}
          <div className="bg-secondary/50 p-2.5 rounded-lg border border-border">
            <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
              <KeyRound className="w-3.5 h-3.5 text-primary" /> Broker Auth
            </span>
            <p className={`font-bold ${(tokenStatus as any)?.is_token_valid ? 'text-success' : 'text-warning'}`}>
              {(tokenStatus as any)?.is_token_valid ? 'VALID' : 'EXPIRED / NONE'}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-muted-foreground capitalize">{safeStr(String((tokenStatus as any)?.provider || activeBroker), '—')}</span>
              {Boolean((tokenStatus as any)?.state) && (
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-primary/10 text-primary">
                  {String((tokenStatus as any)?.state)}
                </span>
              )}
            </div>
            {!(tokenStatus as any)?.is_token_valid && (
              <a
                href={`https://droid-backend-emeq.onrender.com/api/v1/tokens/${activeBroker}/login`}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-amber-600 dark:text-amber-400 hover:underline"
              >
                Re-authenticate <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>

          {/* Buffer & Queue Metrics */}
          <div className="border border-border rounded-lg p-3 bg-secondary/30 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-500" /> High-Frequency Ring Buffer
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

            <div className="flex justify-between text-[11px] text-muted-foreground pt-1">
              <span>Subscriptions: {health?.subscriptions ?? 4}</span>
              <span>Dropped Events: {health?.dropped_events ?? 0}</span>
            </div>
          </div>

          {/* LRU Cache & Batch Pipeline */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <div className="border border-border rounded-lg p-2.5 bg-secondary/30 space-y-2">
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
              <div className="text-[11px] space-y-1 text-muted-foreground">
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

            <div className="border border-border rounded-lg p-2.5 bg-secondary/30 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs text-foreground flex items-center gap-1">
                  <RefreshCw className="w-3.5 h-3.5 text-success" /> Batch Pipeline
                </span>
              </div>
              <div className="text-[11px] space-y-1 text-muted-foreground">
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

          {/* System Uptime */}
          <div className="flex justify-between items-center text-[11px] border-t border-border pt-2">
            <div>
              <span className="text-muted-foreground">Provider Uptime:</span>
              <span className="font-mono font-medium ml-1.5 text-foreground">
                {(tokenStatus as any)?.uptime_seconds !== undefined
                  ? `${Math.round(Number((tokenStatus as any)?.uptime_seconds))}s`
                  : '—'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-muted-foreground">Broker Reconnects:</span>
              <span className="font-mono font-medium ml-1.5 text-foreground">
                {String((tokenStatus as any)?.reconnect_count ?? 0)}
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-border bg-secondary/30 flex items-center justify-between gap-2">
          <button
            onClick={handleResetCircuitBreaker}
            disabled={actionLoading}
            className="px-3 py-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground font-medium text-xs transition-colors cursor-pointer border border-border"
          >
            Reset Circuit Breaker
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-medium text-xs transition-colors cursor-pointer"
          >
            Close Telemetry
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
