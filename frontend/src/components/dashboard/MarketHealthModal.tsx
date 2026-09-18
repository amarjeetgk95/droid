'use client';

import { useState, useEffect, useRef } from 'react';
import { MarketHealthStatus } from '@/lib/types';
import { StreamConnectionState } from '@/hooks/useMarketStream';
import { useMarketSession } from '@/hooks/useMarketSession';
import { api } from '@/lib/api';
import { Activity, Server, Radio, ShieldCheck, Zap, Database, RefreshCw, KeyRound, ExternalLink } from 'lucide-react';
import { toNumber } from '@/lib/coerce';
import { safeStr } from '@/lib/utils';
import { getStoredSettings } from '@/lib/settings';
import { FreshnessClock } from '@/components/common/FreshnessClock';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface CacheStatsInfo {
  hit_ratio_percent?: number;
  items_count?: number;
}

interface PipelineStatsInfo {
  timeseries_store?: Record<string, unknown>;
  write_pipeline?: { queue_depth?: number; total_flushed?: number } & Record<string, unknown>;
}

interface TokenStatusInfo {
  is_token_valid?: boolean;
  provider?: string;
  state?: string;
  uptime_seconds?: number;
  reconnect_count?: number;
}

function numOrNull(v: unknown): number | null {
  return toNumber(v);
}

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
  const { phase } = useMarketSession();
  const marketOpen = phase === 'OPEN';
  const [cacheStats, setCacheStats] = useState<CacheStatsInfo | null>(null);
  const [pipelineStats, setPipelineStats] = useState<PipelineStatsInfo | null>(null);
  const [tokenStatus, setTokenStatus] = useState<TokenStatusInfo | null>(null);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [telemetryAt, setTelemetryAt] = useState<Date | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeBroker, setActiveBroker] = useState<string | null>(null);
  const hasTelemetryRef = useRef(false);

  useEffect(() => {
    try {
      const stored = getStoredSettings();
      if (stored?.broker?.provider) setActiveBroker(stored.broker.provider);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Stored broker settings unreadable');
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    let delay = 3000;
    let timeout: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;
    const ctrl = new AbortController();

    const schedule = (ms: number) => {
      if (!isMounted || ctrl.signal.aborted) return;
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(() => {
        timeout = null;
        void run();
      }, ms);
    };

    const run = async (): Promise<void> => {
      if (!isMounted || ctrl.signal.aborted) return;
      if (typeof document !== 'undefined' && document.hidden) {
        schedule(3000);
        return;
      }
      if (inFlight) return;
      inFlight = true;
      try {
        const [cRes, pRes, tRes] = await Promise.all([
          api.getCacheStats(),
          api.getPipelineStats(),
          api.getBrokerTokenStatus(),
        ]);
        if (!isMounted || ctrl.signal.aborted) return;
        setCacheStats(cRes.data as unknown as CacheStatsInfo);
        setPipelineStats(pRes.data as unknown as PipelineStatsInfo);
        setTokenStatus(tRes.data as unknown as TokenStatusInfo);
        setTelemetryError(null);
        setTelemetryAt(new Date());
        hasTelemetryRef.current = true;
        delay = 3000;
      } catch (err) {
        if (!isMounted || ctrl.signal.aborted) return;
        delay = Math.min(30000, delay * 2);
        setTelemetryError(err instanceof Error ? err.message : 'Telemetry unavailable');
      } finally {
        inFlight = false;
        if (isMounted && !ctrl.signal.aborted && (marketOpen || !hasTelemetryRef.current)) {
          schedule(delay + Math.random() * 500);
        }
      }
    };

    void run();
    const onVis = () => {
      if (document.hidden) return;
      if (timeout) {
        clearTimeout(timeout);
        timeout = null;
      }
      void run();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      isMounted = false;
      ctrl.abort();
      if (timeout) clearTimeout(timeout);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [isOpen, marketOpen]);

  const handleResetCircuitBreaker = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      await api.resetCircuitBreaker();
      const [cRes, pRes, tRes] = await Promise.all([
        api.getCacheStats(),
        api.getPipelineStats(),
        api.getBrokerTokenStatus(),
      ]);
      setCacheStats(cRes.data as unknown as CacheStatsInfo);
      setPipelineStats(pRes.data as unknown as PipelineStatsInfo);
      setTokenStatus(tRes.data as unknown as TokenStatusInfo);
      setTelemetryAt(new Date());
      hasTelemetryRef.current = true;
      setTelemetryError(null);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Circuit breaker reset failed');
    } finally {
      setActionLoading(false);
    }
  };

  const handleClearCache = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      await api.clearCache();
      const cRes = await api.getCacheStats();
      setCacheStats(cRes.data as unknown as CacheStatsInfo);
      setTelemetryAt(new Date());
      hasTelemetryRef.current = true;
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Cache flush failed');
    } finally {
      setActionLoading(false);
    }
  };

  const breaker = health?.circuit_breaker_state ?? null;
  const breakerTone =
    breaker === 'OPEN' ? 'text-down-strong' : breaker === 'HALF_OPEN' ? 'text-warn-strong' : 'text-foreground';
  const breakerNote =
    breaker === 'OPEN'
      ? 'Protection tripped — new risk is blocked'
      : breaker === 'HALF_OPEN'
        ? 'Probing recovery'
        : breaker === 'CLOSED'
          ? 'No active protection'
          : 'State unavailable';

  const bufferDepth = numOrNull(health?.buffer_depth);
  const broker = safeStr(tokenStatus?.provider, '') || activeBroker;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="sm:max-w-xl max-h-[85vh] flex flex-col gap-0 p-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="p-4 border-b border-border bg-secondary/30">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-primary" />
              <DialogTitle className="font-bold text-sm text-foreground">
                High-Frequency &amp; Ingestion Telemetry
              </DialogTitle>
            </div>
            <FreshnessClock
              lastAt={telemetryAt}
              fetching={actionLoading}
              marketClosed={!marketOpen}
              dataQuality={telemetryError ? 'DEGRADED' : null}
              sourceLabel={marketOpen ? 'REST · 3s poll' : 'REST · paused'}
            />
          </div>
        </DialogHeader>

        {/* Content */}
        <div className="p-5 space-y-4 text-xs overflow-y-auto flex-1">
          {telemetryError && (
            <div role="status" className="rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-[11px] text-muted-foreground">
              Telemetry degraded — showing last known values. {telemetryError}
            </div>
          )}
          {actionError && (
            <div role="alert" className="rounded-lg border border-down-line bg-down-wash px-3 py-2 text-[11px] text-down-strong">
              {actionError}
            </div>
          )}
          {!marketOpen && (
            <div role="status" className="rounded-lg border border-border bg-surface-subtle px-3 py-2 text-[11px] text-ink-3">
              Market session {phase} — telemetry polling paused; last check stays on screen.
            </div>
          )}
          {/* Main Status Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            <div className="bg-secondary/50 p-2.5 rounded-lg border border-border">
              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
                <Server className="w-3.5 h-3.5 text-primary" /> Provider
              </span>
              <p className="font-bold text-foreground capitalize">{safeStr(health?.provider, '—')}</p>
              <span className="text-[10px] bg-warn/15 text-warn px-1.5 py-0.2 rounded font-mono">
                {health?.mode || '—'}
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
                Reconnects: {health?.reconnect_count !== undefined ? health.reconnect_count : '—'}
              </span>
            </div>

            <div className="bg-secondary/50 p-2.5 rounded-lg border border-border sm:col-span-1 col-span-2">
              <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
                <ShieldCheck className="w-3.5 h-3.5 text-primary" /> Circuit Breaker
              </span>
              <p className={`font-bold ${breakerTone}`}>{breaker ?? '—'}</p>
              <span className={`text-[10px] ${breaker === 'OPEN' ? 'text-down-strong' : 'text-muted-foreground'}`}>
                {breakerNote}
              </span>
            </div>
          </div>

          {/* Broker Auth Status */}
          <div className="bg-secondary/50 p-2.5 rounded-lg border border-border">
            <span className="text-[11px] text-muted-foreground flex items-center gap-1.5 mb-1">
              <KeyRound className="w-3.5 h-3.5 text-primary" /> Broker Auth
            </span>
            <p className={`font-bold ${tokenStatus === null ? 'text-muted-foreground' : tokenStatus.is_token_valid ? 'text-success' : 'text-warning'}`}>
              {tokenStatus === null ? 'UNAVAILABLE' : tokenStatus.is_token_valid ? 'VALID' : 'EXPIRED / NONE'}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-muted-foreground capitalize">{broker || '—'}</span>
              {Boolean(tokenStatus?.state) && (
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono bg-primary/10 text-primary">
                  {String(tokenStatus?.state)}
                </span>
              )}
            </div>
            {tokenStatus !== null && tokenStatus.is_token_valid !== true && broker && (
              <a
                href={`${api.getBaseUrl()}/api/v1/tokens/${broker}/login`}
                target="_blank"
                rel="noreferrer"
                className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-warn hover:underline"
              >
                Re-authenticate <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>

          {/* Buffer & Queue Metrics */}
          <div className="border border-border rounded-lg p-3 bg-secondary/30 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-foreground flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-warn" /> High-Frequency Ring Buffer
              </span>
              <span className="text-xs text-muted-foreground font-mono">
                Depth: {bufferDepth !== null ? bufferDepth.toLocaleString('en-IN') : '—'} / 10,000
              </span>
            </div>

            <div className="w-full bg-secondary h-2 rounded-full overflow-hidden">
              <div
                className="bg-primary h-full transition-all duration-300"
                style={{ width: `${bufferDepth !== null ? Math.min(100, (bufferDepth / 10000) * 100) : 0}%` }}
              />
            </div>

            <div className="flex justify-between text-[11px] text-muted-foreground pt-1">
              <span>Subscriptions: {health?.subscriptions !== undefined ? health.subscriptions : '—'}</span>
              <span>Dropped Events: {health?.dropped_events !== undefined ? health.dropped_events : '—'}</span>
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
                    {cacheStats?.hit_ratio_percent !== undefined ? `${cacheStats.hit_ratio_percent}%` : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Cached Items:</span>
                  <span className="font-mono font-medium text-foreground">
                    {cacheStats?.items_count !== undefined ? String(cacheStats.items_count) : '—'}
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
                    {pipelineStats?.write_pipeline?.queue_depth !== undefined
                      ? String(pipelineStats.write_pipeline.queue_depth)
                      : '—'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Total Flushed:</span>
                  <span className="font-mono font-medium text-foreground">
                    {pipelineStats?.write_pipeline?.total_flushed !== undefined
                      ? String(pipelineStats.write_pipeline.total_flushed)
                      : '—'}
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
                {tokenStatus?.uptime_seconds !== undefined
                  ? `${Math.round(Number(tokenStatus?.uptime_seconds))}s`
                  : '—'}
              </span>
            </div>
            <div className="text-right">
              <span className="text-muted-foreground">Broker Reconnects:</span>
              <span className="font-mono font-medium ml-1.5 text-foreground">
                {tokenStatus?.reconnect_count !== undefined ? String(tokenStatus.reconnect_count) : '—'}
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
