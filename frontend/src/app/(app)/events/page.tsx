'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import {
  Calendar,
  CalendarDays,
  Clock,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  ArrowUpRight,
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
  X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type {
  CanonicalEvent,
  EventAlert,
  ShadowSignalRecord,
  EventTrackRecord,
  SourceHealthTelemetry,
  EventRiskParameters,
} from '@/lib/event-types';

const DOMAIN_FILTERS = [
  { label: 'All Sources', id: 'ALL' },
  { label: 'Central Bank & Macro', id: 'CENTRAL_BANK' },
  { label: 'Corporate & Earnings', id: 'CORPORATE' },
  { label: 'Regulatory & Policy', id: 'REGULATORY' },
] as const;

const PHASE_FILTERS = ['ALL', 'SCHEDULED', 'APPROACHING', 'ACTIVE', 'POST_EVENT'] as const;

function phaseDot(phase: string) {
  if (phase === 'ACTIVE') return 'bg-rose-500';
  if (phase === 'APPROACHING') return 'bg-amber-500';
  if (phase === 'SCHEDULED') return 'bg-sky-500';
  if (phase === 'POST_EVENT') return 'bg-emerald-500';
  return 'bg-muted-foreground/40';
}

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

  const fetchDashboardData = async (withSpinner = true) => {
    try {
      if (withSpinner) setLoading(true);
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
      if (withSpinner) setLoading(false);
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
      await fetchDashboardData(false);
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
      await fetchDashboardData(false);
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
      await fetchDashboardData(false);
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
      if (filterPhase !== 'ALL' && e.temporal_phase !== filterPhase) {
        return false;
      }
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
  const sourcesHealthy = (sourceHealth?.overall_status || 'HEALTHY') === 'HEALTHY';

  return (
    <div className="space-y-4 max-w-[1440px] mx-auto pb-12">
      {/* ── Header ── */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3 border-b border-border pb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="success" className="font-mono text-[10px] tracking-wide">
              PHASE 3 · PRODUCTION
            </Badge>
            <span className="text-[11px] text-muted-foreground font-mono truncate">
              Expansion &amp; Statistical Validation · Engine v3.0 · Risk overlays active
            </span>
          </div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2 mt-1">
            <CalendarDays className="w-5 h-5 text-primary shrink-0" />
            <span className="truncate">Event Intelligence &amp; Opportunity Engine</span>
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Institutional context, empirical impact calibration, event-aware risk overlays, and statistical edge verification.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <Button
            variant={showTrackRecord ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowTrackRecord(!showTrackRecord)}
            className="h-8 text-xs cursor-pointer"
            title="Statistical edge validation & track record (§23)"
          >
            <TrendingUp className="w-3.5 h-3.5" />
            Track Record
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSourceHealth(!showSourceHealth)}
            className="h-8 text-xs cursor-pointer"
            title="Official adapter health & circuit breaker telemetry"
          >
            <span className={cn('w-1.5 h-1.5 rounded-full', sourcesHealthy ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse')} />
            <Activity className="w-3.5 h-3.5" />
            <span className={sourcesHealthy ? 'text-emerald-600 dark:text-emerald-400 font-semibold' : 'text-amber-600 dark:text-amber-400 font-semibold'}>
              {sourceHealth?.overall_status || 'HEALTHY'}
            </span>
          </Button>

          <Button
            variant={showAlertQueue ? 'default' : 'outline'}
            size="sm"
            onClick={() => setShowAlertQueue(!showAlertQueue)}
            className="h-8 text-xs cursor-pointer"
            title="Internal desk review queue (§29)"
          >
            <Bell className="w-3.5 h-3.5" />
            Alerts
            {pendingAlerts.length > 0 && (
              <span className="rounded-full bg-amber-500 text-white dark:text-black px-1.5 py-px text-[10px] font-bold tabular-nums leading-none">
                {pendingAlerts.length}
              </span>
            )}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleCalibrate}
            disabled={calibrating}
            className="h-8 text-xs cursor-pointer"
          >
            <SlidersHorizontal className={cn('w-3.5 h-3.5', calibrating && 'animate-spin')} />
            {calibrating ? 'Calibrating…' : 'Calibrate'}
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncCorporate}
            disabled={syncingCorp}
            className="h-8 text-xs cursor-pointer"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', syncingCorp && 'animate-spin')} />
            {syncingCorp ? 'Syncing…' : 'Sync Corp'}
          </Button>

          <Button
            size="sm"
            onClick={handleSyncRbi}
            disabled={syncingRbi}
            className="h-8 text-xs cursor-pointer"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', syncingRbi && 'animate-spin')} />
            {syncingRbi ? 'Syncing…' : 'Sync RBI'}
          </Button>
        </div>
      </div>

      {/* ── Event-Aware Risk Overlay Banner (§28) ── */}
      {riskOverlay && (
        <div
          className={cn(
            'rounded-xl border p-3.5 flex flex-col sm:flex-row sm:items-center gap-3',
            riskOverlay.proximity_state === 'BLACKOUT_WINDOW' &&
              'border-rose-500/40 bg-rose-50 dark:bg-rose-950/25',
            riskOverlay.proximity_state === 'APPROACHING_WINDOW' &&
              'border-amber-500/40 bg-amber-50 dark:bg-amber-950/25',
            (riskOverlay.proximity_state === 'NORMAL' || riskOverlay.proximity_state === 'REACTION_WINDOW') &&
              'border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/20',
          )}
        >
          <div
            className={cn(
              'flex h-9 w-9 items-center justify-center rounded-lg border shrink-0',
              riskOverlay.proximity_state === 'BLACKOUT_WINDOW' &&
                'bg-rose-500/15 border-rose-500/30 text-rose-600 dark:text-rose-400',
              riskOverlay.proximity_state === 'APPROACHING_WINDOW' &&
                'bg-amber-500/15 border-amber-500/30 text-amber-600 dark:text-amber-400',
              (riskOverlay.proximity_state === 'NORMAL' || riskOverlay.proximity_state === 'REACTION_WINDOW') &&
                'bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-400',
            )}
          >
            <ShieldCheck className="h-4.5 w-4.5" />
          </div>
          <div className="flex-1 min-w-0">
            <p
              className={cn(
                'text-xs font-bold',
                riskOverlay.proximity_state === 'BLACKOUT_WINDOW' && 'text-rose-700 dark:text-rose-300',
                riskOverlay.proximity_state === 'APPROACHING_WINDOW' && 'text-amber-700 dark:text-amber-300',
                (riskOverlay.proximity_state === 'NORMAL' || riskOverlay.proximity_state === 'REACTION_WINDOW') &&
                  'text-emerald-700 dark:text-emerald-300',
              )}
            >
              Central Risk Engine Overlay (§28) · {riskOverlay.underlying} ·{' '}
              <span className="font-mono font-semibold">
                {riskOverlay.proximity_state === 'BLACKOUT_WINDOW'
                  ? 'BLACKOUT WINDOW — 0.0x sizing, orders rejected'
                  : riskOverlay.proximity_state === 'APPROACHING_WINDOW'
                  ? `APPROACHING CATALYST — ${riskOverlay.sizing_multiplier}x sizing dampener`
                  : 'NORMAL PROXIMITY — 1.0x full envelope'}
              </span>
            </p>
            {riskOverlay.triggering_event_title && (
              <p className="text-[11px] text-muted-foreground mt-0.5 truncate" title={riskOverlay.triggering_event_title}>
                Catalyst: {riskOverlay.triggering_event_title}
                {riskOverlay.minutes_to_event != null && (
                  <span className="font-mono tabular-nums"> · T-{riskOverlay.minutes_to_event}m</span>
                )}
              </p>
            )}
          </div>
          <Badge
            variant={riskOverlay.can_enter ? 'success' : 'destructive'}
            className="font-mono text-[11px] font-bold shrink-0 self-start sm:self-center"
          >
            {riskOverlay.can_enter ? 'CAN ENTER · YES' : 'ENTRY BLOCKED'}
          </Badge>
        </div>
      )}

      {/* ── Statistical Edge Validation Drawer (§23, §24) ── */}
      {showTrackRecord && trackRecord && (
        <section className="rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary shrink-0">
                <TrendingUp className="h-4 w-4" />
              </span>
              <h3 className="text-sm font-bold truncate">Statistical Edge Validation &amp; Track Record (§23–§24)</h3>
            </div>
            <Button variant="ghost" size="icon-xs" onClick={() => setShowTrackRecord(false)} aria-label="Close track record" className="cursor-pointer">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-2.5 text-xs">
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Sample Size (N)</span>
              <div className="text-sm font-bold font-mono tabular-nums">
                {trackRecord.settled_events_count} / {trackRecord.minimum_sample_required}
              </div>
              <div className={cn('text-[10px] font-semibold', trackRecord.sample_size_gate_passed ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400')}>
                {trackRecord.sample_size_gate_passed ? 'Gate passed' : 'Accumulating (<30)'}
              </div>
            </div>
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Directional Accuracy</span>
              <div className="text-sm font-bold font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                {trackRecord.directional_accuracy_pct}%
              </div>
              <div className="text-[10px] text-muted-foreground">Predicted vs actual</div>
            </div>
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Shadow Win Rate</span>
              <div className="text-sm font-bold font-mono tabular-nums text-purple-600 dark:text-purple-400">
                {trackRecord.shadow_win_rate_pct}%
              </div>
              <div className="text-[10px] text-muted-foreground tabular-nums">{trackRecord.shadow_trades_count} shadow trades</div>
            </div>
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Profit Factor</span>
              <div className="text-sm font-bold font-mono tabular-nums">{trackRecord.profit_factor}x</div>
              <div className="text-[10px] text-muted-foreground tabular-nums">Expectancy {trackRecord.average_expectancy_r}R</div>
            </div>
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Avg MFE / MAE</span>
              <div className="text-sm font-bold font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                +{trackRecord.average_mfe_pct}%
              </div>
              <div className="text-[10px] text-rose-600 dark:text-rose-400 font-mono tabular-nums">MAE −{trackRecord.average_mae_pct}%</div>
            </div>
            <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">System Gate</span>
              <div>
                <Badge variant={trackRecord.recommendation === 'READY_FOR_PAPER_PILOT' ? 'success' : 'secondary'} className="font-mono text-[10px]">
                  {trackRecord.recommendation}
                </Badge>
              </div>
              <div className="text-[10px] text-muted-foreground">Strict shadow guard (§3)</div>
            </div>
          </div>
        </section>
      )}

      {/* ── Source Health Telemetry Panel (§5, §34) ── */}
      {showSourceHealth && sourceHealth && (
        <section className="rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0">
                <Activity className="h-4 w-4" />
              </span>
              <h3 className="text-sm font-bold truncate">Adapter Health &amp; Circuit Breakers (§5, §34)</h3>
            </div>
            <Button variant="ghost" size="icon-xs" onClick={() => setShowSourceHealth(false)} aria-label="Close source health" className="cursor-pointer">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2.5">
            {Object.values(sourceHealth.sources).map((src) => (
              <div key={src.source_name} className="rounded-lg bg-muted/40 border border-border p-3.5 space-y-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold font-mono truncate">{src.source_name}</span>
                  <Badge
                    variant={src.status === 'HEALTHY' ? 'success' : 'secondary'}
                    className={cn(
                      'text-[10px] shrink-0',
                      src.status === 'DEGRADED' && 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300',
                      src.status === 'OFFLINE' && 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300',
                    )}
                  >
                    {src.status}
                  </Badge>
                </div>
                <dl className="space-y-1 text-[11px]">
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">Circuit</dt>
                    <dd className="font-mono font-semibold">{src.circuit_state}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">Latency</dt>
                    <dd className="font-mono tabular-nums">{src.last_latency_ms.toFixed(1)} ms</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-muted-foreground">OK / Err</dt>
                    <dd className="font-mono tabular-nums">{src.success_count} / {src.error_count}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Internal Alert & Review Queue (§29) ── */}
      {showAlertQueue && (
        <section className="rounded-xl border border-amber-500/30 bg-amber-50 dark:bg-amber-950/15 p-4 sm:p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0 flex-wrap">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/15 text-amber-600 dark:text-amber-400 shrink-0">
                <Bell className="h-4 w-4" />
              </span>
              <h3 className="text-sm font-bold">Internal Alert &amp; Review Queue (§29)</h3>
              <Badge variant="secondary" className="font-mono text-[10px] bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300">
                15m dedup cooldown
              </Badge>
            </div>
            <Button variant="ghost" size="icon-xs" onClick={() => setShowAlertQueue(false)} aria-label="Close alerts" className="cursor-pointer">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>

          {alerts.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">
              No alerts in queue. State-change alerts appear here with strict 15-minute signature cooldowns.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  className={cn(
                    'rounded-lg border bg-card p-3.5 space-y-2 text-xs',
                    alert.status === 'PENDING_REVIEW' ? 'border-amber-500/40 shadow-sm' : 'opacity-70',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <Badge
                      variant="secondary"
                      className={cn(
                        'text-[10px] font-bold',
                        alert.severity === 'CRITICAL' && 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300',
                        alert.severity === 'HIGH' && 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300',
                        (alert.severity === 'MEDIUM' || alert.severity === 'INFO') && 'bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300',
                      )}
                    >
                      {alert.severity} · {alert.alert_type}
                    </Badge>
                    <span className="font-mono text-[10px] text-muted-foreground tabular-nums shrink-0">
                      {new Date(alert.created_at).toLocaleTimeString('en-IN', {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        timeZone: 'Asia/Kolkata',
                      })} IST
                    </span>
                  </div>
                  <h4 className="font-semibold">{alert.title}</h4>
                  <p className="text-muted-foreground text-[11px] leading-relaxed line-clamp-3">{alert.message}</p>
                  <div className="flex items-center justify-between gap-2 pt-2 border-t border-border text-[11px]">
                    <span className="text-muted-foreground font-mono truncate" title={alert.canonical_event_id}>
                      {alert.canonical_event_id}
                    </span>
                    {alert.status === 'PENDING_REVIEW' ? (
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => handleAcknowledgeAlert(alert.alert_id)}
                        disabled={acknowledgingId === alert.alert_id}
                        className="shrink-0 cursor-pointer border-amber-500/40 text-amber-700 hover:bg-amber-500/10 dark:text-amber-300"
                      >
                        <Check className="h-3 w-3" />
                        {acknowledgingId === alert.alert_id ? 'Ack…' : 'Acknowledge'}
                      </Button>
                    ) : (
                      <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 font-semibold text-[10px] shrink-0">
                        <CheckCircle2 className="h-3 w-3" /> Ack{alert.acknowledged_by ? ` · ${alert.acknowledged_by}` : ''}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Architecture principle strip (§1) ── */}
      <div className="rounded-xl border border-border bg-card p-3.5 flex items-start gap-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 shrink-0">
          <Info className="h-4 w-4" />
        </span>
        <p className="text-xs leading-relaxed text-muted-foreground">
          <span className="font-semibold text-foreground">Core principle (§1 &amp; §3): </span>
          <span className="font-mono font-semibold text-sky-700 dark:text-sky-300">EVENT IMPORTANCE</span>,{' '}
          <span className="font-mono font-semibold text-amber-700 dark:text-amber-300">EXPECTED MARKET IMPACT</span>, and{' '}
          <span className="font-mono font-semibold text-emerald-700 dark:text-emerald-300">TRADING OPPORTUNITY</span>{' '}
          are three strictly independent dimensions. All signal integration runs in{' '}
          <span className="font-mono font-bold text-purple-700 dark:text-purple-300">SHADOW_MODE (§3)</span> with
          no live execution risk until statistical edge is proven.
        </p>
      </div>

      {/* ── Summary KPI cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border bg-card p-4 shadow-sm transition hover:shadow-md">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Next major event</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400">
              <Calendar className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-2 text-[15px] font-bold truncate" title={nextMajorEvent?.title || 'None scheduled'}>
            {nextMajorEvent ? nextMajorEvent.title : 'None scheduled'}
          </div>
          <div className="mt-1 text-xs text-muted-foreground flex items-center gap-1.5 tabular-nums">
            <Clock className="h-3 w-3 shrink-0" />
            {nextMajorEvent
              ? new Date(nextMajorEvent.event_timestamp).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
              : 'N/A'}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm transition hover:shadow-md">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Official adapters ingested</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              <ShieldCheck className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-2 text-[15px] font-bold text-emerald-700 dark:text-emerald-400 tabular-nums">RBI · NSE · BSE · SEBI</div>
          <div className="mt-1 text-xs text-muted-foreground tabular-nums">{events.length} canonical event dossiers</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm transition hover:shadow-md">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Pending review alerts</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
              <Bell className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-2 text-[15px] font-bold text-amber-700 dark:text-amber-400 tabular-nums">
            {pendingAlerts.length} Actionable
          </div>
          <div className="mt-1 text-xs text-muted-foreground">Internal desk review queue (§29)</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm transition hover:shadow-md">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Forward shadow signals</span>
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">
              <Lock className="h-4 w-4" />
            </span>
          </div>
          <div className="mt-2 text-[15px] font-bold text-purple-700 dark:text-purple-400 tabular-nums">
            {shadowSignals.length} Active in shadow
          </div>
          <div className="mt-1 text-xs text-muted-foreground">Zero real-capital order routing (§3)</div>
        </div>
      </div>

      {/* ── Filter bar ── */}
      <div className="rounded-xl border border-border bg-card p-3 space-y-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Domain</span>
            <div className="flex flex-wrap items-center gap-1 rounded-lg bg-secondary/70 p-1">
              {DOMAIN_FILTERS.map((cat) => (
                <button
                  key={cat.id}
                  onClick={() => setFilterCategory(cat.id)}
                  className={cn(
                    'rounded-md px-2.5 h-7 text-xs font-medium transition cursor-pointer whitespace-nowrap',
                    filterCategory === cat.id
                      ? 'bg-background text-foreground font-semibold shadow-sm border border-border'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {cat.label}
                </button>
              ))}
            </div>
          </div>
          <div className="text-xs text-muted-foreground tabular-nums">
            Showing <span className="font-bold text-foreground">{filteredEvents.length}</span> of {events.length} events
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Phase</span>
          <div className="flex flex-wrap items-center gap-1 rounded-lg bg-secondary/70 p-1">
            {PHASE_FILTERS.map((phase) => (
              <button
                key={phase}
                onClick={() => setFilterPhase(phase)}
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2.5 h-7 text-xs font-medium transition cursor-pointer',
                  filterPhase === phase
                    ? 'bg-background text-foreground font-semibold shadow-sm border border-border'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {phase !== 'ALL' && <span className={cn('w-1.5 h-1.5 rounded-full', phaseDot(phase))} />}
                {phase}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Events feed ── */}
      {loading ? (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-border rounded-xl bg-card">
          <RefreshCw className="h-7 w-7 text-primary animate-spin" />
          <p className="text-sm text-muted-foreground mt-3">Ingesting multi-source event dossiers…</p>
        </div>
      ) : error ? (
        <div className="p-6 border border-rose-500/30 bg-rose-50 dark:bg-rose-950/20 rounded-xl text-center">
          <AlertTriangle className="h-6 w-6 text-rose-600 dark:text-rose-400 mx-auto" />
          <p className="text-sm font-medium text-rose-700 dark:text-rose-300 mt-2">{error}</p>
          <Button variant="outline" size="sm" onClick={() => void fetchDashboardData(true)} className="mt-3 h-8 text-xs cursor-pointer">
            <RefreshCw className="h-3.5 w-3.5" /> Retry fetch
          </Button>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 border border-dashed border-border rounded-xl text-center p-6 bg-card">
          <Calendar className="h-9 w-9 text-muted-foreground/40" />
          <p className="text-sm font-medium mt-2">No events match the selected filters</p>
          <p className="text-xs text-muted-foreground mt-1">Switch the filter back to ALL or trigger a sync</p>
        </div>
      ) : (
        <div className="space-y-3">
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
            const detailHref = `/events/${encodeURIComponent(event.canonical_event_id)}`;

            return (
              <article
                key={event.canonical_event_id}
                className="group rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm transition hover:shadow-md hover:border-primary/30"
              >
                <div className="flex flex-col xl:flex-row gap-4">
                  {/* Event info */}
                  <div className="space-y-2 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary" className="bg-sky-500/10 text-sky-700 border-sky-500/25 hover:bg-sky-500/15 dark:text-sky-300 text-[11px]">
                        <Building2 className="h-3 w-3" />
                        {event.entity_name}
                      </Badge>
                      <Badge variant="secondary" className="text-[11px] font-normal">
                        {event.sub_type?.replace(/_/g, ' ') || event.event_type}
                      </Badge>
                      <Badge
                        variant="secondary"
                        className={cn(
                          'text-[11px] font-semibold',
                          event.temporal_phase === 'ACTIVE' && 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300',
                          event.temporal_phase === 'APPROACHING' && 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300',
                          (event.temporal_phase === 'SCHEDULED' || event.temporal_phase === 'POST_EVENT') && '',
                        )}
                      >
                        {event.temporal_phase === 'ACTIVE' && <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />}
                        {event.temporal_phase}
                      </Badge>
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3 w-3" />
                        {event.verification_status} ({event.certainty})
                      </span>
                    </div>

                    <Link href={detailHref} className="block">
                      <h2 className="text-[15px] font-bold leading-snug group-hover:text-primary transition-colors">
                        {event.title}
                      </h2>
                    </Link>
                    {event.description && (
                      <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                        {event.description}
                      </p>
                    )}

                    <div className="flex items-center gap-1.5 pt-0.5">
                      <Layers className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="text-[11px] text-muted-foreground shrink-0">Affects:</span>
                      <div className="flex flex-wrap gap-1 min-w-0">
                        {event.impact_mappings.slice(0, 5).map((m) => (
                          <span
                            key={m.target_symbol}
                            className="rounded-md bg-secondary border border-border px-1.5 py-0.5 text-[11px] font-mono tabular-nums"
                          >
                            {m.target_symbol}
                          </span>
                        ))}
                        {event.impact_mappings.length > 5 && (
                          <span className="text-[11px] text-muted-foreground self-center tabular-nums">
                            +{event.impact_mappings.length - 5} more
                          </span>
                        )}
                        {event.impact_mappings.length === 0 && (
                          <span className="text-[11px] text-muted-foreground">No mapped targets yet</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Independent scores matrix (§1, §30) */}
                  <div className="shrink-0 xl:w-[596px]">
                    <div className="grid grid-cols-2 min-[560px]:grid-cols-4 gap-2">
                      <div className="rounded-lg border border-border bg-muted/40 p-2.5 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                          Importance
                        </div>
                        <div className="mt-1 tabular-nums">
                          <span className="text-lg font-extrabold text-sky-700 dark:text-sky-300">{importanceScore}</span>
                          <span className="text-[10px] text-muted-foreground"> /100</span>
                        </div>
                        <div className="mt-0.5 text-[10px] text-muted-foreground truncate" title={`${event.entity_id} authority`}>
                          {event.entity_id} authority
                        </div>
                      </div>

                      <div className="rounded-lg border border-border bg-muted/40 p-2.5 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                          Mkt impact
                        </div>
                        <div className="mt-1.5">
                          <Badge
                            variant="secondary"
                            className="bg-amber-500/15 text-amber-700 border-amber-500/30 tabular-nums dark:text-amber-300 text-[11px]"
                          >
                            {event.scores?.market_impact.status === 'SCORED' && event.scores.market_impact.final_score != null
                              ? `${event.scores.market_impact.final_score}/100`
                              : event.scores?.market_impact.status || 'PENDING'}
                          </Badge>
                        </div>
                        <div className="mt-1 text-[10px] text-muted-foreground">
                          {event.scores?.market_impact.status === 'SCORED' ? 'Calibrated (§14)' : 'Pending vol'}
                        </div>
                      </div>

                      <div className="rounded-lg border border-border bg-muted/40 p-2.5 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                          Opportunity
                        </div>
                        <div className="mt-1.5">
                          <Badge variant="secondary" className="tabular-nums text-[11px]">
                            {event.scores?.opportunity.final_score != null
                              ? `${event.scores.opportunity.final_score}/100`
                              : 'Live gates'}
                          </Badge>
                        </div>
                        <div className="mt-1 text-[10px] text-muted-foreground">Perishable (§15)</div>
                      </div>

                      <div className="rounded-lg border border-border bg-muted/40 p-2.5 text-center">
                        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                          Verdict
                        </div>
                        <div className="mt-1.5">
                          <Badge
                            variant="secondary"
                            className={cn(
                              'text-[10px] font-bold max-w-full',
                              event.scores?.final_decision === 'EXECUTE_SHADOW' && 'bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300',
                              event.scores?.final_decision === 'WAIT_FOR_CONFIRMATION' && 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300',
                              (!event.scores?.final_decision || event.scores?.final_decision === 'NO_TRADE' || event.scores?.final_decision === 'EXECUTE_ACTIVE') && 'bg-rose-500/10 text-rose-700 border-rose-500/25 dark:text-rose-300',
                            )}
                          >
                            <span className="truncate">{event.scores?.final_decision || 'NO_TRADE'}</span>
                          </Badge>
                        </div>
                        <div className="mt-1 text-[10px] text-muted-foreground font-mono">SHADOW</div>
                      </div>
                    </div>

                    <div className="mt-2 flex items-center justify-end">
                      <Link href={detailHref}>
                        <Button variant="outline" size="xs" className="h-7 text-[11px] cursor-pointer">
                          Full breakdown &amp; options <ArrowUpRight className="h-3 w-3" />
                        </Button>
                      </Link>
                    </div>
                  </div>
                </div>

                {/* Timing footer */}
                <div className="mt-3 pt-2.5 border-t border-border flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Clock className="h-3 w-3 shrink-0" />
                    <span className="truncate tabular-nums">
                      {dateStr} · {timeStr} IST ({event.timestamp_precision})
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-muted-foreground/80 truncate max-w-[45%] shrink-0" title={event.canonical_event_id}>
                    {event.canonical_event_id}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
