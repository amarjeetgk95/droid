'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import {
  Calendar,
  Clock,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  ArrowUpRight,
  Filter,
  CheckCircle2,
  Lock,
  Layers,
  Building2,
  Info,
  Bell,
  Check,
  TrendingUp,
  Activity,
  SlidersHorizontal,
} from 'lucide-react';
import { api } from '@/lib/api';
import type {
  CanonicalEvent,
  EventAlert,
  ShadowSignalRecord,
  EventTrackRecord,
  SourceHealthTelemetry,
  EventRiskParameters,
} from '@/lib/event-types';

export default function EventsDashboardPage() {
  const [events, setEvents] = useState<CanonicalEvent[]>([]);
  const [alerts, setAlerts] = useState<EventAlert[]>([]);
  const [shadowSignals, setShadowSignals] = useState<ShadowSignalRecord[]>([]);
  const [trackRecord, setTrackRecord] = useState<EventTrackRecord | null>(null);
  const [sourceHealth, setSourceHealth] = useState<SourceHealthTelemetry | null>(null);
  const [riskOverlay, setRiskOverlay] = useState<EventRiskParameters | null>(null);

  const [loading, setLoading] = useState(true);
  const [syncingRbi, setSyncingRbi] = useState(false);
  const [syncingCorp, setSyncingCorp] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [filterCategory, setFilterCategory] = useState<string>('ALL');
  const [filterPhase, setFilterPhase] = useState<string>('ALL');
  const [showAlertQueue, setShowAlertQueue] = useState(false);
  const [showTrackRecord, setShowTrackRecord] = useState(false);
  const [showSourceHealth, setShowSourceHealth] = useState(false);
  const [acknowledgingId, setAcknowledgingId] = useState<string | null>(null);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [eventsData, alertsData, signalsData, trackData, healthData, riskData] = await Promise.all([
        api.getUpcomingEvents(100),
        api.getAlertsQueue().catch(() => [] as EventAlert[]),
        api.getShadowSignals().catch(() => [] as ShadowSignalRecord[]),
        api.getEventTrackRecord().catch(() => null),
        api.getSourceHealth().catch(() => null),
        api.getEventRiskOverlay('BANKNIFTY').catch(() => null),
      ]);
      setEvents(eventsData);
      setAlerts(alertsData);
      setShadowSignals(signalsData);
      setTrackRecord(trackData);
      setSourceHealth(healthData);
      setRiskOverlay(riskData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load events');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    Promise.all([
      api.getUpcomingEvents(100),
      api.getAlertsQueue().catch(() => [] as EventAlert[]),
      api.getShadowSignals().catch(() => [] as ShadowSignalRecord[]),
      api.getEventTrackRecord().catch(() => null),
      api.getSourceHealth().catch(() => null),
      api.getEventRiskOverlay('BANKNIFTY').catch(() => null),
    ])
      .then(([eventsData, alertsData, signalsData, trackData, healthData, riskData]) => {
        if (active) {
          setEvents(eventsData);
          setAlerts(alertsData);
          setShadowSignals(signalsData);
          setTrackRecord(trackData);
          setSourceHealth(healthData);
          setRiskOverlay(riskData);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load events');
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const handleSyncRbi = async () => {
    try {
      setSyncingRbi(true);
      await api.syncRbiEvents();
      await fetchDashboardData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to sync RBI official schedule');
    } finally {
      setSyncingRbi(false);
    }
  };

  const handleSyncCorporate = async () => {
    try {
      setSyncingCorp(true);
      await api.syncCorporateEvents();
      await fetchDashboardData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to sync corporate announcements');
    } finally {
      setSyncingCorp(false);
    }
  };

  const handleCalibrate = async () => {
    try {
      setCalibrating(true);
      await api.triggerCalibration();
      await fetchDashboardData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to calibrate market impact');
    } finally {
      setCalibrating(false);
    }
  };

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      setAcknowledgingId(alertId);
      const updated = await api.acknowledgeAlert(alertId, 'OPS_DESK');
      setAlerts((prev) => prev.map((a) => (a.alert_id === alertId ? updated : a)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to acknowledge alert');
    } finally {
      setAcknowledgingId(null);
    }
  };

  const pendingAlerts = useMemo(() => {
    return alerts.filter((a) => a.status === 'PENDING_REVIEW');
  }, [alerts]);

  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      // Phase match
      if (filterPhase !== 'ALL' && e.temporal_phase !== filterPhase) {
        return false;
      }
      // Category match
      if (filterCategory === 'CENTRAL_BANK') {
        return e.event_type === 'CENTRAL_BANK' || e.event_type === 'MACRO';
      }
      if (filterCategory === 'CORPORATE') {
        return e.event_type === 'EARNINGS' || e.event_type === 'COMPANY' || e.event_type === 'CORPORATE_ACTION';
      }
      if (filterCategory === 'REGULATORY') {
        return e.event_type === 'REGULATORY' || e.event_type === 'POLICY';
      }
      return true;
    });
  }, [events, filterPhase, filterCategory]);

  const nextMajorEvent = events[0] || null;

  return (
    <div className="space-y-6 pb-12">
      {/* Header Banner */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-border/40 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-6 items-center rounded-md bg-emerald-500/10 px-2 text-xs font-semibold text-emerald-400 border border-emerald-500/20">
              Phase 3 · Production Expansion & Statistical Validation
            </span>
            <span className="text-xs text-muted-foreground font-mono">Engine v3.0 · Risk Overlays Active</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground mt-1">
            Event Intelligence & Opportunity Engine
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Institutional context, empirical impact calibration, event-aware risk overlays, and statistical edge verification.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Track Record Toggle */}
          <button
            onClick={() => setShowTrackRecord(!showTrackRecord)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              showTrackRecord
                ? 'bg-primary text-primary-foreground border-primary shadow'
                : 'bg-card/70 border-border/60 text-muted-foreground hover:text-foreground'
            }`}
          >
            <TrendingUp className="h-3.5 w-3.5" />
            <span>Track Record (§23)</span>
          </button>

          {/* Source Health Toggle */}
          <button
            onClick={() => setShowSourceHealth(!showSourceHealth)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              sourceHealth?.overall_status === 'HEALTHY'
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
            }`}
          >
            <Activity className="h-3.5 w-3.5" />
            <span>Sources: {sourceHealth?.overall_status || 'HEALTHY'}</span>
          </button>

          {/* Alerts Queue */}
          <button
            onClick={() => setShowAlertQueue(!showAlertQueue)}
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
              pendingAlerts.length > 0
                ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                : 'bg-card/70 border-border/60 text-muted-foreground hover:text-foreground'
            }`}
          >
            <Bell className="h-3.5 w-3.5" />
            <span>Alerts</span>
            {pendingAlerts.length > 0 && (
              <span className="rounded-full bg-amber-500 text-black px-1.5 py-0.2 text-[10px] font-black">
                {pendingAlerts.length}
              </span>
            )}
          </button>

          {/* Calibrate Market Impact */}
          <button
            onClick={handleCalibrate}
            disabled={calibrating}
            className="flex items-center gap-1.5 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 border border-sky-500/20 px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50"
          >
            <SlidersHorizontal className={`h-3.5 w-3.5 ${calibrating ? 'animate-spin' : ''}`} />
            {calibrating ? 'Calibrating...' : 'Calibrate Impact'}
          </button>

          {/* Sync Corporate */}
          <button
            onClick={handleSyncCorporate}
            disabled={syncingCorp}
            className="flex items-center gap-1.5 rounded-lg bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncingCorp ? 'animate-spin' : ''}`} />
            {syncingCorp ? 'Syncing...' : 'Sync Corp'}
          </button>

          {/* Sync RBI */}
          <button
            onClick={handleSyncRbi}
            disabled={syncingRbi}
            className="flex items-center gap-1.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 px-3 py-1.5 text-xs font-semibold transition disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncingRbi ? 'animate-spin' : ''}`} />
            {syncingRbi ? 'Syncing...' : 'Sync RBI'}
          </button>
        </div>
      </div>

      {/* Event-Aware Risk Overlay Banner (§28) */}
      {riskOverlay && (
        <div
          className={`rounded-xl border p-4 shadow-sm transition backdrop-blur-md ${
            riskOverlay.proximity_state === 'BLACKOUT_WINDOW'
              ? 'border-rose-500/50 bg-rose-950/20 text-rose-300 animate-pulse'
              : riskOverlay.proximity_state === 'APPROACHING_WINDOW'
              ? 'border-amber-500/50 bg-amber-950/20 text-amber-300'
              : 'border-emerald-500/30 bg-emerald-950/10 text-emerald-300'
          }`}
        >
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2.5">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              <div>
                <span className="font-bold">
                  Central Risk Engine Overlay (§28) · {riskOverlay.underlying}:{' '}
                </span>
                <span className="font-mono">
                  {riskOverlay.proximity_state === 'BLACKOUT_WINDOW'
                    ? 'BLACKOUT WINDOW ACTIVE (0.0x Sizing — All Orders Rejected)'
                    : riskOverlay.proximity_state === 'APPROACHING_WINDOW'
                    ? `APPROACHING HIGH-IMPACT CATALYST (50% Sizing Dampener: ${riskOverlay.sizing_multiplier}x Lots)`
                    : 'NORMAL PROXIMITY (1.0x Full Envelope Ceiling)'}
                </span>
                {riskOverlay.triggering_event_title && (
                  <span className="block text-[11px] text-muted-foreground mt-0.5">
                    Catalyst: {riskOverlay.triggering_event_title} ({riskOverlay.minutes_to_event} min)
                  </span>
                )}
              </div>
            </div>

            <span className="font-mono font-bold rounded bg-background/50 border border-border/40 px-2 py-1 text-[11px]">
              Can Enter: {riskOverlay.can_enter ? 'YES' : 'BLOCKED'}
            </span>
          </div>
        </div>
      )}

      {/* Statistical Edge Validation & Track Record Drawer (§23, §24) */}
      {showTrackRecord && trackRecord && (
        <div className="rounded-xl border border-primary/40 bg-card/90 p-5 shadow-lg space-y-4 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-bold text-foreground">
                Statistical Edge Validation & Track Record Benchmarking (§23, §24)
              </h3>
            </div>
            <button
              onClick={() => setShowTrackRecord(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Sample Size (N)</span>
              <div className="text-sm font-bold font-mono text-foreground">
                {trackRecord.settled_events_count} / {trackRecord.minimum_sample_required}
              </div>
              <div className="text-[10px] text-muted-foreground">
                {trackRecord.sample_size_gate_passed ? 'Gate Passed' : 'Accumulating (<30)'}
              </div>
            </div>

            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Directional Accuracy</span>
              <div className="text-sm font-bold font-mono text-emerald-400">
                {trackRecord.directional_accuracy_pct}%
              </div>
              <div className="text-[10px] text-muted-foreground">Predicted vs Actual</div>
            </div>

            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Shadow Win Rate</span>
              <div className="text-sm font-bold font-mono text-purple-400">
                {trackRecord.shadow_win_rate_pct}%
              </div>
              <div className="text-[10px] text-muted-foreground">{trackRecord.shadow_trades_count} Shadow Trades</div>
            </div>

            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Profit Factor</span>
              <div className="text-sm font-bold font-mono text-foreground">
                {trackRecord.profit_factor}x
              </div>
              <div className="text-[10px] text-muted-foreground">Expectancy: {trackRecord.average_expectancy_r}R</div>
            </div>

            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Avg MFE vs MAE</span>
              <div className="text-sm font-bold font-mono text-emerald-400">
                +{trackRecord.average_mfe_pct}%
              </div>
              <div className="text-[10px] text-rose-400 font-mono">MAE: -{trackRecord.average_mae_pct}%</div>
            </div>

            <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">System Gate Status</span>
              <div className="text-xs font-bold text-foreground">
                <span
                  className={`rounded px-1.5 py-0.5 ${
                    trackRecord.recommendation === 'READY_FOR_PAPER_PILOT'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : 'bg-amber-500/20 text-amber-300'
                  }`}
                >
                  {trackRecord.recommendation}
                </span>
              </div>
              <div className="text-[10px] text-muted-foreground">Strict Shadow Guard (§3)</div>
            </div>
          </div>
        </div>
      )}

      {/* Source Health Telemetry Panel (§5, §34) */}
      {showSourceHealth && sourceHealth && (
        <div className="rounded-xl border border-border/60 bg-card/80 p-5 shadow-lg space-y-4 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-foreground">
                Official Adapter Health & Circuit Breaker Telemetry (§5, §34)
              </h3>
            </div>
            <button
              onClick={() => setShowSourceHealth(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {Object.values(sourceHealth.sources).map((src) => (
              <div
                key={src.source_name}
                className="rounded-lg bg-background/50 border border-border/40 p-3.5 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-foreground font-mono">{src.source_name}</span>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                      src.status === 'HEALTHY'
                        ? 'bg-emerald-500/20 text-emerald-300'
                        : src.status === 'DEGRADED'
                        ? 'bg-amber-500/20 text-amber-300'
                        : 'bg-rose-500/20 text-rose-300'
                    }`}
                  >
                    {src.status}
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground text-[11px]">
                  <span>Circuit State:</span>
                  <span className="font-mono text-foreground">{src.circuit_state}</span>
                </div>
                <div className="flex justify-between text-muted-foreground text-[11px]">
                  <span>Latency:</span>
                  <span className="font-mono text-foreground">{src.last_latency_ms.toFixed(1)} ms</span>
                </div>
                <div className="flex justify-between text-muted-foreground text-[11px]">
                  <span>Success / Failures:</span>
                  <span className="font-mono text-foreground">
                    {src.success_count} / {src.error_count}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Internal Alert & Review Queue Drawer / Section (§29) */}
      {showAlertQueue && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/10 p-5 shadow-md space-y-4 backdrop-blur-md">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-amber-400" />
              <h3 className="text-sm font-bold text-foreground">
                Internal Alert & Review Queue (§29)
              </h3>
              <span className="text-[11px] rounded bg-amber-500/20 text-amber-300 px-2 py-0.5 font-mono">
                15m Dedup Cooldown Active
              </span>
            </div>
            <button
              onClick={() => setShowAlertQueue(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Close
            </button>
          </div>

          {alerts.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">
              No alerts in queue. State-change alerts appear here with strict 15-minute signature cooldowns.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  className={`rounded-lg border p-3.5 space-y-2 text-xs transition ${
                    alert.status === 'PENDING_REVIEW'
                      ? 'border-amber-500/40 bg-card/80 shadow-sm'
                      : 'border-border/40 bg-card/30 opacity-70'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                        alert.severity === 'CRITICAL'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          : alert.severity === 'HIGH'
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                          : 'bg-sky-500/20 text-sky-300 border border-sky-500/30'
                      }`}
                    >
                      {alert.severity} · {alert.alert_type}
                    </span>
                    <span className="font-mono text-[10px] text-muted-foreground">
                      {new Date(alert.created_at).toLocaleTimeString('en-IN', {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        timeZone: 'Asia/Kolkata',
                      })} IST
                    </span>
                  </div>

                  <h4 className="font-semibold text-foreground">{alert.title}</h4>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">{alert.message}</p>

                  <div className="flex items-center justify-between pt-2 border-t border-border/30 text-[11px]">
                    <span className="text-muted-foreground font-mono">ID: {alert.canonical_event_id}</span>
                    {alert.status === 'PENDING_REVIEW' ? (
                      <button
                        onClick={() => handleAcknowledgeAlert(alert.alert_id)}
                        disabled={acknowledgingId === alert.alert_id}
                        className="inline-flex items-center gap-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 px-2 py-0.5 text-[10px] font-semibold transition"
                      >
                        <Check className="h-3 w-3" />
                        {acknowledgingId === alert.alert_id ? 'Ack...' : 'Acknowledge'}
                      </button>
                    ) : (
                      <span className="text-emerald-400 flex items-center gap-1 font-semibold text-[10px]">
                        <CheckCircle2 className="h-3 w-3" /> Acknowledged ({alert.acknowledged_by})
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Principle Disclaimer Box (§1) */}
      <div className="rounded-xl border border-border/60 bg-card/40 p-4 shadow-sm backdrop-blur-md">
        <div className="flex items-start gap-3">
          <Info className="h-5 w-5 text-sky-400 shrink-0 mt-0.5" />
          <div className="text-xs space-y-1">
            <span className="font-semibold text-foreground">Core Architecture Principle (§1 & §3):</span>
            <p className="text-muted-foreground leading-relaxed">
              <span className="text-sky-300 font-mono">EVENT IMPORTANCE</span>,{' '}
              <span className="text-amber-300 font-mono">EXPECTED MARKET IMPACT</span>, and{' '}
              <span className="text-emerald-300 font-mono">TRADING OPPORTUNITY</span> remain three strictly independent dimensions.
              All signal integration operates exclusively in <span className="text-purple-300 font-mono font-bold">SHADOW_MODE (§3)</span> without live execution risk until statistical edge is proven across realized outcomes.
            </p>
          </div>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-border/60 bg-card/50 p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Next Major Event</span>
            <Calendar className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 text-lg font-bold text-foreground truncate">
            {nextMajorEvent ? nextMajorEvent.title : 'None Scheduled'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            {nextMajorEvent
              ? new Date(nextMajorEvent.event_timestamp).toLocaleDateString('en-IN', {
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })
              : 'N/A'}
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-card/50 p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Official Adapters Ingested</span>
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-lg font-bold text-emerald-400">RBI · NSE · BSE · SEBI</div>
          <div className="mt-1 text-xs text-muted-foreground">
            {events.length} canonical event dossiers
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-card/50 p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Pending Review Alerts</span>
            <Bell className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-lg font-bold text-amber-400">
            {pendingAlerts.length} Actionable
          </div>
          <div className="mt-1 text-xs text-muted-foreground">Internal Desk Review Queue (§29)</div>
        </div>

        <div className="rounded-xl border border-border/60 bg-card/50 p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground text-xs">
            <span>Forward Shadow Signals</span>
            <Lock className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-2 text-lg font-bold text-purple-400">
            {shadowSignals.length} Active in Shadow
          </div>
          <div className="mt-1 text-xs text-muted-foreground">Zero Real Capital Order Routing (§3)</div>
        </div>
      </div>

      {/* Multi-tier Filter Bar */}
      <div className="space-y-3 border-b border-border/40 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Domain / Category Filter */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mr-1">Domain:</span>
            {[
              { label: 'All Sources', id: 'ALL' },
              { label: 'Central Bank & Macro', id: 'CENTRAL_BANK' },
              { label: 'Corporate & Earnings', id: 'CORPORATE' },
              { label: 'Regulatory & Policy', id: 'REGULATORY' },
            ].map((cat) => (
              <button
                key={cat.id}
                onClick={() => setFilterCategory(cat.id)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  filterCategory === cat.id
                    ? 'bg-foreground text-background font-semibold shadow'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'
                }`}
              >
                {cat.label}
              </button>
            ))}
          </div>

          <div className="text-xs text-muted-foreground">
            Showing {filteredEvents.length} event{filteredEvents.length === 1 ? '' : 's'}
          </div>
        </div>

        {/* Phase Filter */}
        <div className="flex flex-wrap items-center gap-1.5">
          <Filter className="h-3.5 w-3.5 text-muted-foreground mr-1" />
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mr-1">Phase:</span>
          {['ALL', 'SCHEDULED', 'APPROACHING', 'ACTIVE', 'POST_EVENT'].map((phase) => (
            <button
              key={phase}
              onClick={() => setFilterPhase(phase)}
              className={`rounded-md px-2.5 py-0.5 text-xs font-medium transition ${
                filterPhase === phase
                  ? 'bg-primary/20 text-primary border border-primary/30 font-semibold'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/40'
              }`}
            >
              {phase}
            </button>
          ))}
        </div>
      </div>

      {/* Events Feed */}
      {loading ? (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-border/60 rounded-xl">
          <RefreshCw className="h-8 w-8 text-primary animate-spin" />
          <p className="text-sm text-muted-foreground mt-3">Ingesting multi-source event dossiers...</p>
        </div>
      ) : error ? (
        <div className="p-6 border border-rose-500/20 bg-rose-500/5 rounded-xl text-center">
          <AlertTriangle className="h-6 w-6 text-rose-400 mx-auto" />
          <p className="text-sm font-medium text-rose-300 mt-2">{error}</p>
          <button
            onClick={fetchDashboardData}
            className="mt-3 inline-flex items-center gap-2 text-xs text-primary underline"
          >
            Retry Fetch
          </button>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-border/60 rounded-xl text-center p-6">
          <Calendar className="h-10 w-10 text-muted-foreground/40" />
          <p className="text-sm font-medium text-foreground mt-2">No events match the selected filters</p>
          <p className="text-xs text-muted-foreground mt-1">Switch filter back to ALL or trigger a sync</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredEvents.map((event) => {
            const importanceScore = event.scores?.importance.final_score ?? 0;
            const dateStr = new Date(event.event_timestamp).toLocaleDateString('en-IN', {
              weekday: 'short',
              day: 'numeric',
              month: 'short',
              year: 'numeric',
            });
            const timeStr = new Date(event.event_timestamp).toLocaleTimeString('en-IN', {
              hour: '2-digit',
              minute: '2-digit',
              timeZone: 'Asia/Kolkata',
            });

            return (
              <div
                key={event.canonical_event_id}
                className="group relative rounded-xl border border-border/60 bg-card/40 hover:bg-card/70 transition p-5 shadow-sm hover:shadow-md backdrop-blur-sm"
              >
                <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                  {/* Event Info */}
                  <div className="space-y-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex items-center gap-1 rounded bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-xs font-semibold text-sky-400">
                        <Building2 className="h-3 w-3" />
                        {event.entity_name}
                      </span>
                      <span className="rounded bg-muted/60 px-2 py-0.5 text-xs font-medium text-muted-foreground">
                        {event.sub_type?.replace(/_/g, ' ') || event.event_type}
                      </span>
                      <span
                        className={`rounded px-2 py-0.5 text-xs font-semibold ${
                          event.temporal_phase === 'ACTIVE'
                            ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30 animate-pulse'
                            : event.temporal_phase === 'APPROACHING'
                            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                            : 'bg-muted/40 text-muted-foreground'
                        }`}
                      >
                        {event.temporal_phase}
                      </span>
                      <span className="flex items-center gap-1 text-[11px] text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" />
                        {event.verification_status} ({event.certainty})
                      </span>
                    </div>

                    <h2 className="text-base font-bold text-foreground group-hover:text-primary transition">
                      {event.title}
                    </h2>
                    {event.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                        {event.description}
                      </p>
                    )}

                    {/* Impact mappings tags */}
                    <div className="flex items-center gap-1.5 pt-1">
                      <Layers className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="text-xs text-muted-foreground">Affects:</span>
                      <div className="flex flex-wrap gap-1">
                        {event.impact_mappings.slice(0, 5).map((m) => (
                          <span
                            key={m.target_symbol}
                            className="rounded bg-secondary/80 border border-border/40 px-1.5 py-0.5 text-[11px] font-mono text-secondary-foreground"
                          >
                            {m.target_symbol}
                          </span>
                        ))}
                        {event.impact_mappings.length > 5 && (
                          <span className="text-[11px] text-muted-foreground self-center">
                            +{event.impact_mappings.length - 5} more
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 3 Independent Scores Matrix (§1, §30) */}
                  <div className="flex flex-wrap sm:flex-nowrap items-center gap-4 border-t lg:border-t-0 lg:border-l border-border/40 pt-3 lg:pt-0 lg:pl-6 shrink-0">
                    {/* Importance Score */}
                    <div className="text-center min-w-[90px]">
                      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                        Importance
                      </div>
                      <div className="mt-1 flex items-baseline justify-center gap-1">
                        <span className="text-xl font-extrabold text-sky-400">
                          {importanceScore}
                        </span>
                        <span className="text-[10px] text-muted-foreground">/100</span>
                      </div>
                      <span className="inline-block rounded-full bg-sky-500/10 px-2 py-0.2 text-[10px] font-medium text-sky-300 mt-0.5">
                        {event.entity_id} Authority
                      </span>
                    </div>

                    {/* Expected Impact */}
                    <div className="text-center min-w-[100px]">
                      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                        Market Impact
                      </div>
                      <div className="mt-1.5">
                        <span
                          className={`rounded-md px-2 py-1 text-xs font-semibold ${
                            event.scores?.market_impact.status === 'SCORED'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                              : 'bg-amber-500/10 border border-amber-500/20 text-amber-300'
                          }`}
                        >
                          {event.scores?.market_impact.status === 'SCORED' && event.scores.market_impact.final_score != null
                            ? `${event.scores.market_impact.final_score} / 100`
                            : event.scores?.market_impact.status || 'INSUFFICIENT'}
                        </span>
                      </div>
                      <span className="block text-[10px] text-muted-foreground mt-1">
                        {event.scores?.market_impact.status === 'SCORED' ? 'Calibrated (§14)' : 'Pending Vol'}
                      </span>
                    </div>

                    {/* Opportunity Score */}
                    <div className="text-center min-w-[100px]">
                      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                        Opportunity
                      </div>
                      <div className="mt-1.5">
                        <span className="rounded-md bg-zinc-500/10 border border-zinc-500/20 px-2 py-1 text-xs font-semibold text-zinc-300">
                          {event.scores?.opportunity.final_score != null
                            ? `${event.scores.opportunity.final_score}/100`
                            : 'Live Gates'}
                        </span>
                      </div>
                      <span className="block text-[10px] text-muted-foreground mt-1">
                        Perishable (§15)
                      </span>
                    </div>

                    {/* Final Gate Decision */}
                    <div className="text-center min-w-[105px] border-l border-border/40 pl-4">
                      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
                        Setup Verdict
                      </div>
                      <div className="mt-1.5">
                        <span
                          className={`rounded-md px-2.5 py-1 text-xs font-bold ${
                            event.scores?.final_decision === 'EXECUTE_SHADOW'
                              ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                              : event.scores?.final_decision === 'WAIT_FOR_CONFIRMATION'
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                              : 'bg-rose-500/15 border border-rose-500/30 text-rose-400'
                          }`}
                        >
                          {event.scores?.final_decision || 'NO_TRADE'}
                        </span>
                      </div>
                      <span className="block text-[10px] text-muted-foreground mt-1 font-mono">
                        SHADOW_MODE
                      </span>
                    </div>

                    {/* Detail Link */}
                    <div className="pl-2">
                      <Link
                        href={`/events/${encodeURIComponent(event.canonical_event_id)}`}
                        className="flex items-center justify-center h-9 w-9 rounded-lg bg-secondary hover:bg-primary hover:text-primary-foreground border border-border/60 transition shadow-sm"
                        title="View Full Breakdown & Options Intelligence"
                      >
                        <ArrowUpRight className="h-4 w-4" />
                      </Link>
                    </div>
                  </div>
                </div>

                {/* Timing Footer */}
                <div className="mt-3 pt-3 border-t border-border/30 flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                    <span>
                      {dateStr} · {timeStr} IST ({event.timestamp_precision})
                    </span>
                  </div>
                  <div className="font-mono text-[11px] text-muted-foreground/70">
                    ID: {event.canonical_event_id}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
