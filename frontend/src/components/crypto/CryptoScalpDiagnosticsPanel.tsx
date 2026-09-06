'use client';

import React, { useState } from 'react';
import {
  Activity,
  Send,
  Clock,
  Database,
  RefreshCw,
  Cpu,
  Layers,
} from 'lucide-react';
import { CryptoScalpDiagnostics } from '@/lib/types';
import { api } from '@/lib/api';

interface CryptoScalpDiagnosticsPanelProps {
  diagnostics: CryptoScalpDiagnostics | null;
  onRefresh: () => void;
  scanning: boolean;
}

export function CryptoScalpDiagnosticsPanel({
  diagnostics,
  onRefresh,
  scanning,
}: CryptoScalpDiagnosticsPanelProps) {
  const [updatingConfig, setUpdatingConfig] = useState(false);
  const [currentInterval, setCurrentInterval] = useState(diagnostics?.scan_interval_seconds || 30);
  const [telegramOn, setTelegramOn] = useState(diagnostics?.telegram_enabled ?? true);

  const handleIntervalChange = async (val: number) => {
    setCurrentInterval(val);
    try {
      setUpdatingConfig(true);
      await api.updateCryptoScalpConfig({
        scan_interval_seconds: val,
        telegram_enabled: telegramOn,
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to update scan interval:', err);
    } finally {
      setUpdatingConfig(false);
    }
  };

  const handleToggleTelegram = async () => {
    const nextVal = !telegramOn;
    setTelegramOn(nextVal);
    try {
      setUpdatingConfig(true);
      await api.updateCryptoScalpConfig({
        scan_interval_seconds: currentInterval,
        telegram_enabled: nextVal,
      });
      onRefresh();
    } catch (err) {
      console.error('Failed to update telegram setting:', err);
    } finally {
      setUpdatingConfig(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 shadow-xs">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        {/* Left: Engine Status & Telemetry */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-xs font-bold text-foreground">24/7 Scalp Engine:</span>
            <span className="text-xs font-mono text-emerald-400 font-semibold">
              {diagnostics?.worker_running ? 'Autonomous Scanning Active' : 'Standby / Polling'}
            </span>
          </div>

          <div className="h-4 w-px bg-border hidden sm:block" />

          {/* Supabase Persistence Indicator */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Database className="w-3.5 h-3.5 text-emerald-400" />
            <span>Supabase Sync:</span>
            <span className="font-mono text-foreground font-medium">
              {diagnostics?.supabase_persisted_count ?? 0} persisted
            </span>
          </div>

          <div className="h-4 w-px bg-border hidden sm:block" />

          {/* Strategies Evaluated */}
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Layers className="w-3.5 h-3.5 text-primary" />
            <span>Strategies:</span>
            <span className="font-mono text-foreground font-medium">5 Strategies (VWAP, EMA, Squeeze, Vol, Depth)</span>
          </div>
        </div>

        {/* Right: Controls (Interval, Telegram Toggle, Manual Trigger) */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Configurable Scan Interval */}
          <div className="flex items-center gap-1.5 bg-secondary/80 px-2.5 py-1 rounded-lg border border-border">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-[11px] text-muted-foreground">Cadence:</span>
            <select
              value={currentInterval}
              onChange={(e) => handleIntervalChange(Number(e.target.value))}
              disabled={updatingConfig}
              className="bg-transparent text-xs font-semibold text-foreground focus:outline-hidden cursor-pointer"
            >
              <option value={15} className="bg-card text-foreground">15s (Aggressive)</option>
              <option value={30} className="bg-card text-foreground">30s (Default)</option>
              <option value={60} className="bg-card text-foreground">60s (Balanced)</option>
              <option value={120} className="bg-card text-foreground">120s (Conservative)</option>
            </select>
          </div>

          {/* Telegram Toggle Button */}
          <button
            type="button"
            onClick={handleToggleTelegram}
            disabled={updatingConfig}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer ${
              telegramOn
                ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 hover:bg-blue-500/20'
                : 'bg-secondary text-muted-foreground border-border hover:text-foreground'
            }`}
          >
            <Send className="w-3 h-3" />
            <span>Telegram: {telegramOn ? 'ON' : 'OFF'}</span>
          </button>

          {/* Scan Now Button */}
          <button
            type="button"
            onClick={onRefresh}
            disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shadow-xs"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Scanning...' : 'Scan Now'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
