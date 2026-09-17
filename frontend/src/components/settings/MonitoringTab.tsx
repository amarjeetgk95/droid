'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  RotateCcw,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Database,
  Cpu,
  Server,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Card } from '@/components/ui/desk';

export function MonitoringTab() {
  const [healthData, setHealthData] = useState<any>(null);
  const [configData, setConfigData] = useState<any>(null);
  const [cbStatus, setCbStatus] = useState<any>(null);
  const [cacheStats, setCacheStats] = useState<any>(null);
  const [pipelineStats, setPipelineStats] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [telemetryError, setTelemetryError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<'reset' | 'trip' | 'clear' | null>(null);
  const [actionMsg, setActionMsg] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const fetchAllTelemetry = useCallback(async () => {
    setLoading(true);
    setActionMsg(null);
    try {
      const [healthRes, configRes, cbRes, cacheRes, pipeRes] = await Promise.allSettled([
        api.getForecastHealth(30),
        api.getForecastConfig(),
        api.getCircuitBreakerStatus(),
        api.getCacheStats(),
        api.getPipelineStats(),
      ]);

      const failed: string[] = [];
      if (healthRes.status === 'fulfilled') setHealthData(healthRes.value);
      else { setHealthData(null); failed.push('forecast health'); }
      if (configRes.status === 'fulfilled') setConfigData(configRes.value);
      else { setConfigData(null); failed.push('forecast config'); }
      if (cbRes.status === 'fulfilled') setCbStatus(cbRes.value?.data ?? null);
      else { setCbStatus(null); failed.push('circuit breaker'); }
      if (cacheRes.status === 'fulfilled') setCacheStats(cacheRes.value?.data ?? null);
      else { setCacheStats(null); failed.push('cache stats'); }
      if (pipeRes.status === 'fulfilled') setPipelineStats(pipeRes.value?.data ?? null);
      else { setPipelineStats(null); failed.push('pipeline stats'); }
      setTelemetryError(failed.length > 0 ? `Unavailable: ${failed.join(', ')}` : null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAllTelemetry();
  }, [fetchAllTelemetry]);

  // Circuit Breaker Actions
  const handleResetCircuitBreaker = async () => {
    setBusyAction('reset');
    setActionMsg(null);
    try {
      await api.resetCircuitBreaker();
      setActionMsg({ text: 'Circuit breaker reset to CLOSED state', type: 'success' });
      void fetchAllTelemetry();
    } catch (err: any) {
      setActionMsg({ text: `Reset failed: ${err?.message || 'Error'}`, type: 'error' });
    } finally {
      setBusyAction(null);
    }
  };

  const handleTripCircuitBreaker = async () => {
    if (!window.confirm('Are you sure you want to manually TRIP the circuit breaker for testing?')) return;
    setBusyAction('trip');
    setActionMsg(null);
    try {
      await api.tripCircuitBreaker();
      setActionMsg({ text: 'Circuit breaker manually TRIPPED to OPEN state', type: 'success' });
      void fetchAllTelemetry();
    } catch (err: any) {
      setActionMsg({ text: `Trip failed: ${err?.message || 'Error'}`, type: 'error' });
    } finally {
      setBusyAction(null);
    }
  };

  // Cache Actions
  const handleClearCache = async () => {
    if (!window.confirm('Clear the in-memory telemetry and summary cache? Dashboards may briefly slow down while it refills.')) return;
    setBusyAction('clear');
    setActionMsg(null);
    try {
      await api.clearCache();
      setActionMsg({ text: 'In-memory telemetry and summary cache cleared', type: 'success' });
      void fetchAllTelemetry();
    } catch (err: any) {
      setActionMsg({ text: `Clear failed: ${err?.message || 'Error'}`, type: 'error' });
    } finally {
      setBusyAction(null);
    }
  };

  const healthStatus = healthData?.status || 'unknown';
  const isDegraded = healthData?.degraded || healthStatus === 'degraded' || healthStatus === 'failing';
  const cacheItemCount = cacheStats?.items_count ?? cacheStats?.cached_count;
  const droppedCount = pipelineStats?.write_pipeline?.duplicates_dropped;
  const enqueuedCount = pipelineStats?.write_pipeline?.total_enqueued;
  const dropRate =
    typeof droppedCount === 'number' && typeof enqueuedCount === 'number' && enqueuedCount > 0
      ? `${((droppedCount / enqueuedCount) * 100).toFixed(2)}%`
      : '—';
  const queueDepth = pipelineStats?.write_pipeline?.queue_depth;

  return (
    <div className="space-y-4">
      {/* Header with refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-[var(--ds-text)]">System Telemetry & Health Monitoring</h2>
          <p className="text-xs text-[var(--ds-muted)]">
            Live pipeline diagnostics, circuit breakers, cache statistics & forecast calibration telemetry
          </p>
        </div>
        <button
          type="button"
          className="btn btn-sm flex items-center gap-1.5"
          onClick={fetchAllTelemetry}
          disabled={loading || busyAction !== null}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh All</span>
        </button>
      </div>

      {telemetryError && (
        <div className="p-2.5 rounded text-xs flex items-center gap-2 border bg-[var(--ds-warn-wash)] border-[var(--ds-warn-line)] text-[var(--ds-warn-strong)]">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>Some telemetry endpoints failed — {telemetryError}. Affected fields show —.</span>
        </div>
      )}

      {actionMsg && (
        <div
          className={`p-2.5 rounded text-xs flex items-center gap-2 border ${
            actionMsg.type === 'success'
              ? 'bg-[var(--ds-bull-wash)] border-[var(--ds-bull-line)] text-[var(--ds-bull-strong)]'
              : 'bg-[var(--ds-bear-wash)] border-[var(--ds-bear-line)] text-[var(--ds-bear-strong)]'
          }`}
        >
          {actionMsg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertTriangle className="w-4 h-4 shrink-0" />}
          <span>{actionMsg.text}</span>
        </div>
      )}

      {/* 1. Forecast Health Telemetry Deck */}
      <Card title="Forecast Engine Health & Settlement Diagnostics" meta="Endpoint /api/v1/monitoring/forecast-health">
        <div className="space-y-3 text-xs">
          <div className="grid sm:grid-cols-4 gap-3 items-center">
            <div>
              <div className="stat-l">Engine Status</div>
              <div className="mt-1 flex items-center gap-1.5">
                <span
                  className={`badge ${
                    healthStatus === 'healthy'
                      ? 'b-bull'
                      : healthStatus === 'degraded'
                      ? 'b-warn'
                      : healthStatus === 'failing'
                      ? 'b-bear'
                      : 'b-neutral'
                  } font-bold`}
                >
                  {healthStatus.toUpperCase()}
                </span>
                {isDegraded && <span className="badge b-warn text-[10px]">DEGRADED</span>}
              </div>
              <div className="muted text-[11px] mt-0.5">
                Window:{' '}
                <span className="font-semibold">
                  {healthData?.window ?? '—'}
                </span>{' '}
                predictions
                {healthData?.metrics?.n != null ? ` · settled ${healthData.metrics.n}` : ''}
              </div>
            </div>

            <div>
              <div className="stat-l">Hit Rate</div>
              <div className="num font-bold text-base mt-0.5">
                {healthData?.metrics?.hit_rate != null ? `${(healthData.metrics.hit_rate * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="muted text-[11px]">
                Min sample: n &ge; {healthData?.thresholds?.min_n ?? '—'}
              </div>
            </div>

            <div>
              <div className="stat-l">Mean Brier Score</div>
              <div className="num font-bold text-base mt-0.5">
                {healthData?.metrics?.brier != null ? Number(healthData.metrics.brier).toFixed(3) : '—'}
              </div>
              <div className="muted text-[11px]">
                Max baseline slack: {healthData?.thresholds?.brier_slack ?? '—'}
              </div>
            </div>

            <div>
              <div className="stat-l">Calibration ECE</div>
              <div className="num font-bold text-base mt-0.5">
                {healthData?.metrics?.ece != null ? Number(healthData.metrics.ece).toFixed(3) : '—'}
              </div>
              <div className="muted text-[11px]">
                Max: {healthData?.thresholds?.ece_max ?? '—'}
              </div>
            </div>
          </div>

          {healthData?.reasons?.length > 0 && (
            <div className="p-2.5 rounded bg-[var(--ds-warn-wash)] border border-[var(--ds-warn-line)] text-[var(--ds-warn-strong)]">
              <div className="font-semibold flex items-center gap-1 mb-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Active Degradation Warnings</span>
              </div>
              <ul className="list-disc list-inside space-y-0.5 text-[11px]">
                {healthData.reasons.map((r: string, idx: number) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>

      {/* 2. Circuit Breaker & High-Speed Cache Grid */}
      <div className="grid md:grid-cols-2 gap-4">
        {/* Circuit Breaker */}
        <Card title="Circuit Breaker Guard" meta="Endpoint /api/v1/circuit-breaker/status">
          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between">
              <div>
                <div className="stat-l">Breaker State</div>
                <div className="mt-1">
                  <span
                    className={`badge ${
                      cbStatus?.state === 'CLOSED'
                        ? 'b-bull'
                        : cbStatus?.state === 'OPEN'
                          ? 'b-bear'
                          : 'b-neutral'
                    } font-bold`}
                  >
                    {cbStatus?.state ?? '—'}
                  </span>
                </div>
              </div>

              <div className="text-right">
                <div className="stat-l">Consecutive Failures</div>
                <div className="num font-bold text-sm mt-0.5">
                  {cbStatus?.failure_count ?? '—'}
                </div>
              </div>
            </div>

            <p className="muted leading-snug">
              Protects external broker APIs from cascading connection exhaustion. Trips to OPEN automatically after repeated 5xx errors.
            </p>

            <div className="flex items-center gap-2 pt-1">
              <button
                type="button"
                className="btn btn-sm btn-primary flex items-center gap-1.5 disabled:opacity-50"
                onClick={handleResetCircuitBreaker}
                disabled={busyAction !== null}
              >
                <RotateCcw className={`w-3.5 h-3.5 ${busyAction === 'reset' ? 'animate-spin' : ''}`} />
                <span>{busyAction === 'reset' ? 'Resetting…' : 'Reset Breaker'}</span>
              </button>
              <button
                type="button"
                className="btn btn-sm flex items-center gap-1.5 text-[var(--ds-bear)] disabled:opacity-50"
                onClick={handleTripCircuitBreaker}
                disabled={busyAction !== null}
              >
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>{busyAction === 'trip' ? 'Tripping…' : 'Trip for Test'}</span>
              </button>
            </div>
          </div>
        </Card>

        {/* Cache Stats */}
        <Card title="In-Memory Cache Telemetry" meta="Endpoint /api/v1/cache/stats">
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="p-2 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="muted text-[10px]">Total Keys</div>
                <div className="num font-bold text-sm mt-0.5">
                  {cacheItemCount ?? '—'}
                </div>
              </div>
              <div className="p-2 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="muted text-[10px]">Hit Rate</div>
                <div className="num font-bold text-sm mt-0.5">
                  {cacheStats?.hit_ratio_percent != null
                    ? `${Number(cacheStats.hit_ratio_percent).toFixed(1)}%`
                    : '—'}
                </div>
              </div>
              <div className="p-2 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="muted text-[10px]">Status</div>
                <div
                  className={`num font-bold text-xs mt-0.5 ${
                    cacheStats ? 'text-[var(--ds-bull)]' : 'muted'
                  }`}
                >
                  {cacheStats ? (cacheStats.backend ?? 'RESPONDING') : 'UNAVAILABLE'}
                </div>
              </div>
            </div>

            <p className="muted leading-snug">
              High-throughput LRU and pre-warmed dashboard summary memory cache. Auto-refreshed on live market ticks.
            </p>

            <div className="pt-1">
              <button
                type="button"
                className="btn btn-sm flex items-center gap-1.5 text-[var(--ds-bear)] disabled:opacity-50"
                onClick={handleClearCache}
                disabled={busyAction !== null}
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>{busyAction === 'clear' ? 'Clearing…' : 'Clear Cache'}</span>
              </button>
            </div>
          </div>
        </Card>
      </div>

      {/* 3. Micro-Batch Write Pipeline & Timeseries Store Stats */}
      {pipelineStats && (
        <Card title="Micro-Batch Write Pipeline & Timeseries Engine" meta="Zero Disk Lag Architecture">
          <div className="space-y-3 text-xs">
            <div className="grid sm:grid-cols-3 gap-3">
              <div className="p-3 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="font-semibold flex items-center gap-1.5 mb-2 text-[var(--ds-text)]">
                  <Database className="w-3.5 h-3.5 text-[var(--ds-info)]" />
                  <span>Timeseries Store</span>
                </div>
                <div className="space-y-1 text-[11px]">
                  <div className="flex justify-between">
                    <span className="muted">Tracked Series:</span>
                    <span className="num font-semibold">
                      {pipelineStats.timeseries_store?.tracked_series ?? '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="muted">Candles Stored:</span>
                    <span className="num font-semibold">
                      {pipelineStats.timeseries_store?.total_candles_stored ?? '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="muted">Ticks Stored:</span>
                    <span className="num font-semibold">
                      {pipelineStats.timeseries_store?.total_ticks_stored ?? '—'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-3 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="font-semibold flex items-center gap-1.5 mb-2 text-[var(--ds-text)]">
                  <Cpu className="w-3.5 h-3.5 text-[var(--ds-bull)]" />
                  <span>Write Pipeline</span>
                </div>
                <div className="space-y-1 text-[11px]">
                  <div className="flex justify-between">
                    <span className="muted">Flushed Batches:</span>
                    <span className="num font-semibold">
                      {pipelineStats.write_pipeline?.total_flushed ?? '—'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="muted">Queue Depth:</span>
                    <span className="num font-semibold">
                      {queueDepth ?? '—'}
                      {typeof queueDepth === 'number' ? (
                        <span className={`ml-1.5 ${queueDepth === 0 ? 'text-[var(--ds-bull)]' : 'text-[var(--ds-warn)]'}`}>
                          {queueDepth === 0 ? 'IDLE' : 'DRAINING'}
                        </span>
                      ) : null}
                    </span>
                  </div>
                </div>
              </div>

              <div className="p-3 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)]">
                <div className="font-semibold flex items-center gap-1.5 mb-2 text-[var(--ds-text)]">
                  <Server className="w-3.5 h-3.5 text-[var(--ds-warn)]" />
                  <span>Reliability Guard</span>
                </div>
                <div className="space-y-1 text-[11px]">
                  <div className="flex justify-between">
                    <span className="muted">Duplicates Dropped:</span>
                    <span className="num font-semibold">{droppedCount ?? '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="muted">Drop Rate:</span>
                    <span className="num font-semibold">{dropRate}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* 4. Forecast Configuration Flags */}
      {configData && (
        <Card title="Forecast Engine Feature Schema & Targets" meta="Endpoint /api/v1/monitoring/forecast-config">
          <div className="space-y-3 text-xs">
            {configData.status !== 'ok' && (
              <div className="p-2.5 rounded bg-[var(--ds-bear-wash)] border border-[var(--ds-bear-line)] text-[var(--ds-bear-strong)]">
                Release bundle unavailable — {configData.error ?? `status ${configData.status}`}
              </div>
            )}
            <div className="grid sm:grid-cols-2 gap-3">
              <div>
                <div className="font-semibold text-[var(--ds-muted)] mb-1">Engine Configuration Flags</div>
                <div className="p-2 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] font-mono text-[11px] max-h-40 overflow-y-auto">
                  <pre>{JSON.stringify(configData.bundle?.code ?? {}, null, 2)}</pre>
                </div>
              </div>

              <div>
                <div className="font-semibold text-[var(--ds-muted)] mb-1">Target Spec &amp; Artifacts</div>
                <div className="p-2 bg-[var(--ds-surface-elevated)] rounded border border-[var(--ds-border)] font-mono text-[11px] max-h-40 overflow-y-auto">
                  <pre>
                    {JSON.stringify(
                      {
                        target_spec: configData.bundle?.target_spec ?? null,
                        model: configData.bundle?.model ?? null,
                        calibrator: configData.bundle?.calibrator ?? null,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
