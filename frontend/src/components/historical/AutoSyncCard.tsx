'use client';

import { useState, useEffect } from 'react';
import { Clock, Play, Power, CheckCircle2, AlertCircle, RefreshCw, Layers } from 'lucide-react';
import { api } from '@/lib/api';
import type { AutoSyncStatus } from '@/lib/api/historical';
import { useToast } from '@/components/ui/toast';

interface AutoSyncCardProps {
  onSyncComplete?: () => void;
}

export function AutoSyncCard({ onSyncComplete }: AutoSyncCardProps) {
  const { push } = useToast();
  const [status, setStatus] = useState<AutoSyncStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isToggling, setIsToggling] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await api.getHistoricalAutoSyncStatus();
      setStatus(res);
    } catch (err: any) {
      console.warn('Failed to load auto-sync status:', err);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, []);

  const handleToggle = async () => {
    if (!status) return;
    setIsToggling(true);
    try {
      const nextState = !status.enabled;
      const res = await api.toggleHistoricalAutoSync(nextState);
      setStatus(res);
      push(
        nextState ? 'success' : 'info',
        nextState ? 'Auto-Sync Enabled' : 'Auto-Sync Paused',
        nextState
          ? 'Daily delta sync will run automatically at 16:30 IST post-market settlement.'
          : 'Automatic daily ingestion is now paused.'
      );
    } catch (err: any) {
      push('error', 'Toggle Failed', err?.message || 'Could not toggle auto-sync.');
    } finally {
      setIsToggling(false);
    }
  };

  const handleTriggerNow = async () => {
    setIsTriggering(true);
    try {
      const res = await api.triggerHistoricalAutoSync();
      const syncedCount = res.synced?.length || 0;
      if (syncedCount > 0) {
        push(
          'success',
          'EOD Ingestion Complete',
          res.message || `Successfully synced ${syncedCount} missing delta sessions.`
        );
      } else {
        push(
          'info',
          'Datasets Up To Date',
          res.message || 'All datasets already match the latest completed market session.'
        );
      }
      await fetchStatus();
      if (onSyncComplete) onSyncComplete();
    } catch (err: any) {
      push('error', 'Manual Sync Failed', err?.message || 'Failed to trigger delta sync.');
    } finally {
      setIsTriggering(false);
    }
  };

  const isEnabled = status?.enabled ?? true;
  const isRunning = status?.is_running ?? false;

  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        {/* Left: Service Details */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold tracking-tight text-foreground">
              Automated Daily Ingestion (16:30 IST)
            </h2>
            {isRunning ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                <RefreshCw className="h-3 w-3 animate-spin" /> Ingestion Running
              </span>
            ) : isEnabled ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-bull/10 px-2 py-0.5 text-[11px] font-medium text-bull">
                <span className="h-1.5 w-1.5 rounded-full bg-bull animate-pulse" /> Active Daily
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                <Power className="h-3 w-3" /> Paused
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground max-w-2xl">
            Automatically queries missing 1-minute sessions post-market settlement, validates OHLC continuity, merges into Parquet and Supabase, and cascades all higher timeframes (5m, 15m, 30m, 1h, 1D).
          </p>
        </div>

        {/* Right: Actions */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleToggle}
            disabled={isToggling || isRunning}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors disabled:opacity-50 ${
              isEnabled
                ? 'border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground'
                : 'border-bull/30 bg-bull/10 text-bull hover:bg-bull/20'
            }`}
          >
            <Power className="h-3.5 w-3.5" />
            {isToggling ? 'Updating...' : isEnabled ? 'Pause Schedule' : 'Enable Schedule'}
          </button>

          <button
            onClick={handleTriggerNow}
            disabled={isTriggering || isRunning}
            className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 shadow-sm"
          >
            {isTriggering || isRunning ? (
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {isTriggering ? 'Syncing Deltas...' : 'Run EOD Sync Now'}
          </button>
        </div>
      </div>

      {/* Info Pills Footer */}
      <div className="mt-4 grid grid-cols-1 gap-2 pt-3 border-t border-border sm:grid-cols-3 text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="font-medium text-foreground">Next Scheduled Run:</span>
          <span className="font-mono text-primary">{status?.next_run_ist || 'Loading...'}</span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <span className="font-medium text-foreground">Last Session Sync:</span>
          <span className="font-mono">
            {status?.last_sync_at ? new Date(status.last_sync_at).toLocaleString() : 'Bootstrapped'}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Layers className="h-3.5 w-3.5 text-bull" />
          <span>Auto Startup Catch-Up Active</span>
        </div>
      </div>
    </div>
  );
}
