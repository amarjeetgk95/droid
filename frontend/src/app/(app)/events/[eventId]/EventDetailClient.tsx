'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Clock,
  ShieldCheck,
  AlertTriangle,
  Layers,
  Building2,
  ExternalLink,
  History,
  FileCheck2,
  CheckCircle2,
  Activity,
  Zap,
  TrendingUp,
  RefreshCw,
  Lock,
  XCircle,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type {
  CanonicalEvent,
  LiveOpportunityResponse,
  EventOutcome,
  ShadowSignalRecord,
} from '@/lib/event-types';

function SectionTitle({ icon, tint, title, right }: { icon: React.ReactNode; tint: string; title: string; right?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('flex h-7 w-7 items-center justify-center rounded-lg shrink-0', tint)}>{icon}</span>
        <h2 className="text-sm font-bold truncate">{title}</h2>
      </div>
      {right}
    </div>
  );
}

export default function EventDetailClient({ eventId }: { eventId: string }) {
  const [event, setEvent] = useState<CanonicalEvent | null>(null);
  const [liveOpportunity, setLiveOpportunity] = useState<LiveOpportunityResponse | null>(null);
  const [outcome, setOutcome] = useState<EventOutcome | null>(null);
  const [shadowSignals, setShadowSignals] = useState<ShadowSignalRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshingLive, setRefreshingLive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    Promise.all([
      api.getEventDetail(eventId),
      api.getLiveOpportunity(eventId).catch(() => null),
      api.getEventOutcome(eventId).catch(() => null),
      api.getShadowSignals().catch(() => [] as ShadowSignalRecord[]),
    ])
      .then(([eventData, liveData, outcomeData, signalsData]) => {
        if (active) {
          setEvent(eventData);
          setLiveOpportunity(liveData);
          setOutcome(outcomeData);
          setShadowSignals(signalsData.filter((s) => s.canonical_event_id === eventData.canonical_event_id));
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active) {
          setError(err instanceof Error ? err.message : 'Failed to load event details');
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [eventId]);

  const handleRefreshLive = async () => {
    if (!event) return;
    try {
      setRefreshingLive(true);
      const [liveData, outcomeData, signalsData] = await Promise.all([
        api.getLiveOpportunity(event.canonical_event_id).catch(() => null),
        api.getEventOutcome(event.canonical_event_id).catch(() => null),
        api.getShadowSignals().catch(() => [] as ShadowSignalRecord[]),
      ]);
      setLiveOpportunity(liveData);
      setOutcome(outcomeData);
      setShadowSignals(signalsData.filter((s) => s.canonical_event_id === event.canonical_event_id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to refresh live metrics');
    } finally {
      setRefreshingLive(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96 rounded-xl border border-dashed border-border bg-card">
        <Activity className="h-7 w-7 text-primary animate-spin" />
        <p className="text-sm text-muted-foreground mt-3">
          Loading event dossier, options intelligence &amp; prediction snapshot…
        </p>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="p-8 border border-rose-500/30 bg-rose-50 dark:bg-rose-950/20 rounded-xl text-center max-w-lg mx-auto mt-12">
        <AlertTriangle className="h-8 w-8 text-rose-600 dark:text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold mt-2">Event dossier not found</h2>
        <p className="text-xs text-muted-foreground mt-1">{error || 'Unknown error'}</p>
        <Link
          href="/events"
          className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to events dashboard
        </Link>
      </div>
    );
  }

  const importance = event.scores?.importance;
  const marketImpact = event.scores?.market_impact;
  const opportunity = liveOpportunity?.opportunity_score ?? event.scores?.opportunity;
  const prediction = event.latest_prediction;
  const liveOptions = liveOpportunity?.live_options;

  const dateStr = new Date(event.event_timestamp).toLocaleDateString('en-IN', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
  const timeStr = new Date(event.event_timestamp).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  });

  return (
    <div className="space-y-4 pb-16 max-w-6xl mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center justify-between gap-2">
        <Link
          href="/events"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Event Intelligence
        </Link>

        <Button
          variant="outline"
          size="sm"
          onClick={handleRefreshLive}
          disabled={refreshingLive}
          className="h-8 text-xs cursor-pointer"
        >
          <RefreshCw className={cn('h-3.5 w-3.5', refreshingLive && 'animate-spin')} />
          {refreshingLive ? 'Refreshing live…' : 'Refresh live options'}
        </Button>
      </div>

      {/* Hero header */}
      <div className="rounded-xl border border-border bg-card p-5 sm:p-6 shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant="secondary" className="bg-sky-500/10 text-sky-700 border-sky-500/25 dark:text-sky-300">
              <Building2 className="h-3 w-3" />
              {event.entity_name} ({event.entity_id})
            </Badge>
            <Badge variant="secondary" className="font-normal">
              {event.event_type} · {event.sub_type?.replace(/_/g, ' ')}
            </Badge>
            <Badge
              variant="secondary"
              className={cn(
                event.temporal_phase === 'ACTIVE' && 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300',
                event.temporal_phase === 'APPROACHING' && 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300',
              )}
            >
              {event.temporal_phase === 'ACTIVE' && <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />}
              Phase: {event.temporal_phase}
            </Badge>
            <Badge variant="success">
              <ShieldCheck className="h-3 w-3" />
              {event.verification_status} · {event.certainty}
            </Badge>
          </div>

          <span className="font-mono text-[11px] text-muted-foreground truncate max-w-full" title={event.canonical_event_id}>
            ID: {event.canonical_event_id}
          </span>
        </div>

        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight leading-tight">
            {event.title}
          </h1>
          {event.description && (
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed max-w-3xl">
              {event.description}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-3 border-t border-border text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" />
            <span className="font-medium text-foreground">{dateStr}</span>
            <span>at</span>
            <span className="font-medium text-foreground tabular-nums">{timeStr} IST</span>
          </div>
          <div className="tabular-nums">
            Precision: <span className="font-semibold text-foreground">{event.timestamp_precision}</span>
          </div>
          <div>
            Horizon: <span className="font-semibold text-foreground">{event.time_horizon}</span>
          </div>
          <div>
            Direction bias: <span className="font-semibold text-foreground">{event.expected_direction}</span>
          </div>
        </div>
      </div>

      {/* Live options & volatility surface intelligence (§18) */}
      <section className="rounded-xl border border-sky-500/30 bg-sky-50 dark:bg-sky-950/20 p-4 sm:p-5 shadow-sm space-y-4">
        <SectionTitle
          icon={<Zap className="h-4 w-4" />}
          tint="bg-sky-500/15 text-sky-700 dark:text-sky-300"
          title="Live Options Context & Volatility Surface (§18)"
          right={
            liveOptions ? (
              <div className="flex items-center gap-2 text-xs font-mono flex-wrap">
                <Badge variant="secondary" className="bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300 font-bold">
                  {liveOptions.underlying}
                </Badge>
                <span className="text-muted-foreground tabular-nums">
                  DTE {liveOptions.days_to_expiry.toFixed(1)}d ({liveOptions.expiry})
                </span>
              </div>
            ) : undefined
          }
        />

        {liveOptions ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Spot / Futures</span>
              <div className="text-sm font-bold font-mono tabular-nums">
                ₹{liveOptions.spot_price.toLocaleString('en-IN')}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono tabular-nums">
                Basis <span className="text-sky-700 dark:text-sky-300 font-semibold">{liveOptions.basis_points > 0 ? `+${liveOptions.basis_points}` : liveOptions.basis_points} pts</span>
              </div>
            </div>

            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">ATM Strike &amp; Straddle</span>
              <div className="text-sm font-bold font-mono tabular-nums">
                {liveOptions.atm_strike.toLocaleString('en-IN')}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono tabular-nums">
                LTP ₹{liveOptions.atm_straddle_price ? liveOptions.atm_straddle_price.toFixed(1) : 'N/A'}
              </div>
            </div>

            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">ATM Implied Vol</span>
              <div className="text-sm font-bold font-mono tabular-nums text-amber-700 dark:text-amber-300">
                {liveOptions.atm_iv ? `${liveOptions.atm_iv.toFixed(1)}%` : 'N/A'}
              </div>
              <div className="text-[10px] text-muted-foreground">Volatility surface</div>
            </div>

            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Expected Move (±)</span>
              <div className="text-sm font-bold font-mono tabular-nums text-sky-700 dark:text-sky-300">
                {liveOptions.expected_move_points ? `±${liveOptions.expected_move_points.toFixed(0)} pts` : 'N/A'}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono tabular-nums">
                {liveOptions.expected_move_pct ? `±${liveOptions.expected_move_pct.toFixed(2)}%` : 'Calibrating'}
              </div>
            </div>

            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Bid/Ask Spread</span>
              <div className="text-sm font-bold font-mono tabular-nums">
                {liveOptions.bid_ask_spread_pct.toFixed(2)}%
              </div>
              <div className="text-[10px] font-semibold">
                {liveOptions.spread_acceptable ? (
                  <span className="text-emerald-600 dark:text-emerald-400">Acceptable</span>
                ) : (
                  <span className="text-rose-600 dark:text-rose-400">High friction</span>
                )}
              </div>
            </div>

            <div className="rounded-lg bg-background border border-border p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">IV Crush Risk</span>
              <div>
                <Badge
                  variant="secondary"
                  className={cn(
                    'text-[11px] font-bold',
                    liveOptions.iv_crush_risk_level === 'EXTREME' || liveOptions.iv_crush_risk_level === 'HIGH'
                      ? 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-300'
                      : 'bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300',
                  )}
                >
                  {liveOptions.iv_crush_risk_level}
                </Badge>
              </div>
              <div className="text-[10px] text-muted-foreground">Post-event deflation</div>
            </div>
          </div>
        ) : (
          <div className="rounded-lg bg-background border border-border p-4 text-center text-xs text-muted-foreground">
            Live options connection pending for this underlying. Showing offline risk envelope.
          </div>
        )}
      </section>

      {/* 3 independent dimensions grid (§1, §12, §14, §15) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Dimension 1 */}
        <section className="rounded-xl border border-sky-500/30 bg-sky-50 dark:bg-sky-950/20 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] uppercase font-bold tracking-wider text-sky-700 dark:text-sky-300">
              1 · Event importance
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§12 formula</span>
          </div>
          <div className="flex items-baseline gap-1.5 tabular-nums">
            <span className="text-4xl font-extrabold text-sky-700 dark:text-sky-300">{importance?.final_score ?? 0}</span>
            <span className="text-xs text-muted-foreground">/ 100</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Institutional weight from source authority ({event.entity_id}), policy impact, and macroeconomic scope.
          </p>

          {importance && (
            <dl className="pt-3 border-t border-sky-500/25 space-y-1.5 text-xs">
              <dt className="text-[11px] font-semibold text-sky-700 dark:text-sky-300">Factor breakdown</dt>
              {([
                ['Source authority (25%)', importance.source_authority],
                ['Scope (20%)', importance.scope],
                ['Historical significance (20%)', importance.historical_significance],
                ['Policy impact (15%)', importance.policy_impact],
                ['Surprise potential (20%)', importance.surprise_potential],
              ] as const).map(([label, value]) => (
                <div key={label} className="flex justify-between gap-2 text-muted-foreground">
                  <span>{label}</span>
                  <span className="font-mono font-semibold text-foreground tabular-nums">{value}</span>
                </div>
              ))}
            </dl>
          )}
        </section>

        {/* Dimension 2 */}
        <section className="rounded-xl border border-amber-500/30 bg-amber-50 dark:bg-amber-950/20 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] uppercase font-bold tracking-wider text-amber-700 dark:text-amber-300">
              2 · Expected market impact
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§14 regimes</span>
          </div>
          <div className="tabular-nums">
            <span className="text-2xl font-extrabold text-amber-700 dark:text-amber-300">
              {marketImpact?.final_score != null
                ? `${marketImpact.final_score} / 100`
                : marketImpact?.status || 'INSUFFICIENT'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {marketImpact?.reason || 'Dynamic volatility & historical sensitivity regime.'}
          </p>
          <div className="pt-3 border-t border-amber-500/25 text-xs text-muted-foreground space-y-1">
            <div className="text-[11px] font-semibold text-amber-700 dark:text-amber-300">Integrity rule (§33)</div>
            <p>Values are strictly grounded in empirical variance. Zero placeholder fabrication.</p>
          </div>
        </section>

        {/* Dimension 3 */}
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] uppercase font-bold tracking-wider text-muted-foreground">
              3 · Trading opportunity
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§15 perishable</span>
          </div>
          <div className="tabular-nums">
            <span
              className={cn(
                'text-2xl font-extrabold',
                opportunity?.final_decision === 'EXECUTE_SHADOW' && 'text-purple-700 dark:text-purple-300',
                opportunity?.final_decision === 'WAIT_FOR_CONFIRMATION' && 'text-amber-700 dark:text-amber-300',
                (!opportunity?.final_decision || opportunity?.final_decision === 'NO_TRADE' || opportunity?.final_decision === 'EXECUTE_ACTIVE') && 'text-rose-600 dark:text-rose-400',
              )}
            >
              {opportunity?.final_score != null ? `${opportunity.final_score} / 100` : opportunity?.final_decision || 'NO_TRADE'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {opportunity?.reason || 'Live hard-gates evaluation against liquidity, spread, and signal confidence.'}
          </p>

          <div className="pt-3 border-t border-border text-xs space-y-2">
            <div className="text-[11px] font-semibold">Hard gates (§16)</div>
            <div className="space-y-1 font-mono text-[11px]">
              {opportunity?.passed_gates?.map((g) => (
                <div key={g} className="flex items-center justify-between text-emerald-600 dark:text-emerald-400">
                  <span className="truncate mr-2">{g}</span>
                  <span className="flex items-center gap-1 font-semibold shrink-0">
                    <CheckCircle2 className="h-3 w-3" /> PASSED
                  </span>
                </div>
              ))}
              {opportunity?.failed_gates?.map((g) => (
                <div key={g} className="flex items-center justify-between text-rose-600 dark:text-rose-400">
                  <span className="truncate mr-2">{g}</span>
                  <span className="flex items-center gap-1 font-semibold shrink-0">
                    <XCircle className="h-3 w-3" /> FAILED
                  </span>
                </div>
              ))}
              {!opportunity?.passed_gates?.length && !opportunity?.failed_gates?.length && (
                <div className="text-muted-foreground">No gate data available.</div>
              )}
            </div>

            <div className="pt-2 border-t border-border flex items-center justify-between font-semibold">
              <span className="text-muted-foreground">Decision</span>
              <Badge
                variant="secondary"
                className={cn(
                  'font-mono text-[11px] font-bold',
                  opportunity?.final_decision === 'EXECUTE_SHADOW'
                    ? 'bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300'
                    : 'bg-rose-500/10 text-rose-700 border-rose-500/25 dark:text-rose-300',
                )}
              >
                {opportunity?.final_decision || 'NO_TRADE'}
              </Badge>
            </div>
          </div>
        </section>
      </div>

      {/* Shadow-mode signal block (§3, §27) */}
      <section className="rounded-xl border border-purple-500/30 bg-purple-50 dark:bg-purple-950/20 p-4 sm:p-5 shadow-sm space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-500/15 text-purple-700 dark:text-purple-300 shrink-0">
              <Lock className="h-4 w-4" />
            </span>
            <h3 className="text-sm font-bold">Event → Signal Integration · SHADOW_MODE (§3, §27)</h3>
          </div>
          <Badge variant="secondary" className="font-mono text-[10px] font-bold bg-purple-500/15 text-purple-700 border-purple-500/30 dark:text-purple-300">
            ZERO REAL-CAPITAL RISK
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          In strict compliance with §3 and §27, this engine operates in full forward-testing SHADOW_MODE. No live broker orders are placed automatically.
        </p>

        {shadowSignals.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
            {shadowSignals.map((sig) => (
              <div key={sig.shadow_signal_id} className="rounded-lg bg-background border border-border p-3 space-y-1.5 text-xs font-mono">
                <div className="flex items-center justify-between gap-2 font-bold">
                  <span className="text-purple-700 dark:text-purple-300 truncate" title={sig.shadow_signal_id}>{sig.shadow_signal_id}</span>
                  <Badge variant="secondary" className="text-[10px] shrink-0">{sig.shadow_status}</Badge>
                </div>
                <div className="flex justify-between gap-2 text-muted-foreground">
                  <span>Strategy</span>
                  <span className="text-foreground font-sans font-medium">{sig.strategy} ({sig.direction})</span>
                </div>
                <div className="flex justify-between gap-2 text-muted-foreground">
                  <span>Underlying</span>
                  <span className="text-foreground">{sig.underlying}</span>
                </div>
                <div className="flex justify-between gap-2 text-muted-foreground">
                  <span>Simulated entry</span>
                  <span className="text-foreground tabular-nums">₹{sig.simulated_entry_price?.toFixed(2) || 'MARKET'}</span>
                </div>
                <div className="flex justify-between gap-2 text-muted-foreground">
                  <span>Sizing factor</span>
                  <span className="text-foreground tabular-nums">{sig.suggested_sizing_factor}x</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg bg-background border border-border p-3 text-xs text-muted-foreground">
            No active shadow execution record generated yet for this canonical event.
          </div>
        )}
      </section>

      {/* Post-event outcome (§24) */}
      <section className="rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-4">
        <SectionTitle
          icon={<TrendingUp className="h-4 w-4" />}
          tint="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          title="Post-Event Market Reaction & Outcome (§24)"
          right={
            <Badge variant="secondary" className="font-mono text-[10px]">
              {outcome ? (outcome.is_settled ? 'SETTLED' : 'MONITORING') : 'PENDING TRIGGER'}
            </Badge>
          }
        />

        {outcome ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Direction</span>
                <div className="text-sm font-bold">
                  {outcome.prediction_correct ? (
                    <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Correct
                    </span>
                  ) : (
                    <span className="text-rose-600 dark:text-rose-400 flex items-center gap-1">
                      <XCircle className="h-3.5 w-3.5" /> Incorrect
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-muted-foreground">Act: {outcome.actual_direction}</div>
              </div>

              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Initial move (1m)</span>
                <div className="text-sm font-bold font-mono tabular-nums">
                  {outcome.initial_move_pct > 0 ? `+${outcome.initial_move_pct}%` : `${outcome.initial_move_pct}%`}
                </div>
                <div className="text-[10px] text-muted-foreground">Immediate spike</div>
              </div>

              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Maximum move</span>
                <div className="text-sm font-bold font-mono tabular-nums text-sky-700 dark:text-sky-300">
                  {outcome.maximum_move_pct > 0 ? `+${outcome.maximum_move_pct}%` : `${outcome.maximum_move_pct}%`}
                </div>
                <div className="text-[10px] text-muted-foreground">Peak displacement</div>
              </div>

              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">MFE / MAE</span>
                <div className="text-sm font-bold font-mono tabular-nums text-emerald-600 dark:text-emerald-400">
                  +{outcome.mfe_pct}%
                </div>
                <div className="text-[10px] text-rose-600 dark:text-rose-400 font-mono tabular-nums">
                  MAE −{outcome.mae_pct}%
                </div>
              </div>

              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Time to peak</span>
                <div className="text-sm font-bold font-mono tabular-nums">
                  {outcome.time_to_peak_min} min
                </div>
                <div className="text-[10px] text-muted-foreground tabular-nums">
                  Rev: {outcome.time_to_reversal_min ? `${outcome.time_to_reversal_min}m` : 'None'}
                </div>
              </div>

              <div className="rounded-lg bg-muted/40 border border-border p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">IV crush realized</span>
                <div className="text-sm font-bold font-mono tabular-nums text-rose-600 dark:text-rose-400">
                  {outcome.iv_change_pct != null ? `${outcome.iv_change_pct}%` : 'N/A'}
                </div>
                <div className="text-[10px] text-muted-foreground">Vol deflation</div>
              </div>
            </div>

            {outcome.monitoring_snapshots && outcome.monitoring_snapshots.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-semibold">
                  Standardized horizon progression (T-15M → EOD)
                </div>
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-muted/60 text-muted-foreground border-b border-border">
                      <tr>
                        <th className="p-2.5 font-sans font-semibold">Horizon</th>
                        <th className="p-2.5 font-sans font-semibold">Time</th>
                        <th className="p-2.5 font-sans font-semibold">Price</th>
                        <th className="p-2.5 font-sans font-semibold">Move %</th>
                        <th className="p-2.5 font-sans font-semibold">IV</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {outcome.monitoring_snapshots.map((snap, idx) => (
                        <tr key={idx} className="hover:bg-muted/40">
                          <td className="p-2.5 font-bold font-sans">{snap.interval_label}</td>
                          <td className="p-2.5 text-muted-foreground tabular-nums">
                            {new Date(snap.timestamp).toLocaleTimeString('en-IN', {
                              hour: '2-digit',
                              minute: '2-digit',
                              timeZone: 'Asia/Kolkata',
                            })}
                          </td>
                          <td className="p-2.5 tabular-nums">₹{snap.price.toFixed(1)}</td>
                          <td
                            className={cn(
                              'p-2.5 font-bold tabular-nums',
                              snap.move_from_baseline_pct > 0
                                ? 'text-emerald-600 dark:text-emerald-400'
                                : snap.move_from_baseline_pct < 0
                                ? 'text-rose-600 dark:text-rose-400'
                                : 'text-muted-foreground',
                            )}
                          >
                            {snap.move_from_baseline_pct > 0
                              ? `+${snap.move_from_baseline_pct.toFixed(2)}%`
                              : `${snap.move_from_baseline_pct.toFixed(2)}%`}
                          </td>
                          <td className="p-2.5 text-amber-700 dark:text-amber-300 tabular-nums">
                            {snap.iv ? `${snap.iv.toFixed(1)}%` : 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-lg bg-muted/40 border border-border p-4 text-center text-xs text-muted-foreground space-y-1">
            <p className="font-semibold text-foreground">Awaiting event realization</p>
            <p>
              Once this event becomes ACTIVE, the quantitative outcome engine records tick-level trajectory, MFE/MAE, and IV crush across T-15M to EOD.
            </p>
          </div>
        )}
      </section>

      {/* Impact mapping hierarchy (§11) */}
      <section className="rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-4">
        <SectionTitle
          icon={<Layers className="h-4 w-4" />}
          tint="bg-primary/10 text-primary"
          title="Impact Mapping Hierarchy (§11)"
          right={<span className="text-[11px] text-muted-foreground hidden sm:block">Event → Sector → Stock → Index → Derivative</span>}
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {event.impact_mappings.map((mapping, idx) => (
            <div key={idx} className="rounded-lg border border-border bg-muted/40 p-3.5 space-y-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold font-mono text-sm truncate" title={mapping.target_symbol}>
                  {mapping.target_symbol}
                </span>
                <Badge variant="secondary" className="text-[10px] shrink-0">
                  {mapping.target_type}
                </Badge>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>Impact strength</span>
                <span className="font-semibold text-rose-600 dark:text-rose-400">{mapping.impact_strength}</span>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>Relationship confidence</span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400 tabular-nums">
                  {Math.round(mapping.relationship_confidence * 100)}%
                </span>
              </div>
              {mapping.notes && (
                <p className="text-[11px] text-muted-foreground pt-1.5 border-t border-border">
                  {mapping.notes}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* Two-column: prediction snapshot & historical comparables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-3">
          <SectionTitle
            icon={<FileCheck2 className="h-4 w-4" />}
            tint="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
            title="Immutable Prediction Snapshot (§20)"
            right={
              <Badge variant="success" className="text-[10px]">
                Anti-lookahead protected
              </Badge>
            }
          />
          <p className="text-xs text-muted-foreground">
            Preserved at decision cutoff to strictly prevent hindsight bias. Cannot be modified retroactively.
          </p>

          {prediction ? (
            <dl className="rounded-lg bg-muted/40 border border-border p-3.5 space-y-2 font-mono text-xs">
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground font-sans">Prediction ID</dt>
                <dd className="truncate" title={prediction.prediction_id}>{prediction.prediction_id}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground font-sans">Data cutoff</dt>
                <dd className="text-sky-700 dark:text-sky-300 text-[11px] truncate" title={new Date(prediction.data_cutoff_timestamp).toISOString()}>
                  {new Date(prediction.data_cutoff_timestamp).toISOString()}
                </dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground font-sans">Decision verdict</dt>
                <dd className="text-rose-600 dark:text-rose-400 font-bold">{prediction.decision}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-muted-foreground font-sans">Formula version</dt>
                <dd className="text-muted-foreground">{prediction.formula_version}</dd>
              </div>
            </dl>
          ) : (
            <div className="rounded-lg bg-muted/40 border border-border p-3 text-xs text-muted-foreground">
              No immutable prediction snapshot recorded for this event yet.
            </div>
          )}
        </section>

        <section className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-3">
          <SectionTitle
            icon={<History className="h-4 w-4" />}
            tint="bg-amber-500/10 text-amber-600 dark:text-amber-400"
            title="Historical Comparables (§22)"
            right={<span className="text-[10px] text-muted-foreground">Strict time cutoffs</span>}
          />

          <div className="space-y-2.5">
            {event.comparables.length === 0 && (
              <div className="rounded-lg bg-muted/40 border border-border p-3 text-xs text-muted-foreground">
                No historical comparables linked to this dossier.
              </div>
            )}
            {event.comparables.map((comp, idx) => (
              <div key={idx} className="rounded-lg bg-muted/40 border border-border p-3 text-xs space-y-1">
                <div className="flex items-center justify-between gap-2 font-semibold">
                  <span className="truncate">{comp.key_comparison_factor}</span>
                  <span className="text-amber-700 dark:text-amber-300 font-mono tabular-nums shrink-0">
                    {Math.round(comp.similarity_score * 100)}% match
                  </span>
                </div>
                <div className="text-muted-foreground text-[11px] tabular-nums">
                  Date: {comp.past_event_date} · ID: {comp.past_event_id}
                </div>
                {comp.past_market_reaction && (
                  <div className="flex gap-3 text-[11px] pt-1 text-muted-foreground font-mono tabular-nums">
                    <span>15m: +{String(comp.past_market_reaction.banknifty_15m_move_pct ?? '0')}%</span>
                    <span>Day: +{String(comp.past_market_reaction.banknifty_day_move_pct ?? '0')}%</span>
                    <span className="text-rose-600 dark:text-rose-400">
                      IV: {String(comp.past_market_reaction.iv_crush_pct ?? '0')}%
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>

      {/* Ingested sources lineage (§5) */}
      <section className="rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm space-y-3">
        <SectionTitle
          icon={<ShieldCheck className="h-4 w-4" />}
          tint="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
          title="Ingested Source Lineage & Verification (§5)"
        />
        <div className="space-y-2">
          {event.sources.map((source, idx) => (
            <div
              key={idx}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-muted/40 border border-border px-3.5 py-2.5 text-xs"
            >
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="font-semibold truncate">{source.source_name}</span>
                <Badge variant="secondary" className="text-[10px] font-normal">
                  {source.source_type}
                </Badge>
                {source.is_verified && (
                  <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1 text-[11px] font-medium">
                    <CheckCircle2 className="h-3 w-3" /> Verified official
                  </span>
                )}
              </div>

              {source.source_url && (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-primary hover:underline text-[11px] shrink-0"
                >
                  Source URL <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
