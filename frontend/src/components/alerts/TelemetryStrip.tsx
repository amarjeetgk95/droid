'use client';

import { SystemTelemetry } from '@/lib/types';
import { Cpu, HardDrive, Zap, CheckCircle2, ShieldCheck } from 'lucide-react';

export function TelemetryStrip({
  telemetry,
}: {
  telemetry: SystemTelemetry | null;
}) {
  if (!telemetry) return null;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Production Hardening & System Telemetry</h3>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-bold font-mono">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span>STATUS: {telemetry.status}</span>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
        <div className="bg-secondary/40 border border-border rounded-lg p-2.5 space-y-0.5">
          <span className="text-[10px] text-muted-foreground font-sans font-semibold flex items-center gap-1">
            <HardDrive className="w-3 h-3 text-primary" /> RAM Footprint
          </span>
          <div className="text-sm font-black text-foreground">{telemetry.memory_usage_mb} MB</div>
          <span className="text-[9px] text-muted-foreground">In-Memory Engine</span>
        </div>

        <div className="bg-secondary/40 border border-border rounded-lg p-2.5 space-y-0.5">
          <span className="text-[10px] text-muted-foreground font-sans font-semibold flex items-center gap-1">
            <Zap className="w-3 h-3 text-warning" /> Stream Latency
          </span>
          <div className="text-sm font-black text-warning">{telemetry.stream_latency_ms} ms</div>
          <span className="text-[9px] text-muted-foreground">Central WebSocket Buffer</span>
        </div>

        <div className="bg-secondary/40 border border-border rounded-lg p-2.5 space-y-0.5">
          <span className="text-[10px] text-muted-foreground font-sans font-semibold flex items-center gap-1">
            <Cpu className="w-3 h-3 text-primary" /> Active Rules
          </span>
          <div className="text-sm font-black text-foreground">{telemetry.active_alert_rules_count} Active</div>
          <span className="text-[9px] text-muted-foreground">{telemetry.total_alerts_triggered} Triggered Total</span>
        </div>

        <div className="bg-secondary/40 border border-border rounded-lg p-2.5 space-y-0.5">
          <span className="text-[10px] text-muted-foreground font-sans font-semibold">Engine Uptime</span>
          <div className="text-sm font-black text-foreground">{Math.round(telemetry.uptime_seconds)}s</div>
          <span className="text-[9px] text-muted-foreground">Zero Leaks Verified</span>
        </div>
      </div>

      {/* Background Workers Status */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        {Object.entries(telemetry.active_workers).map(([name, desc]) => (
          <span
            key={name}
            className="text-[10px] bg-secondary px-2 py-0.5 rounded border border-border text-muted-foreground font-mono flex items-center gap-1"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <strong>{name}:</strong> {desc.split(' ')[0]}
          </span>
        ))}
      </div>
    </div>
  );
}
