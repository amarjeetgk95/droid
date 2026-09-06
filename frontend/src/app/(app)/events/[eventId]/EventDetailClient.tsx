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
import type {
  CanonicalEvent,
  LiveOpportunityResponse,
  EventOutcome,
  ShadowSignalRecord,
} from '@/lib/event-types';

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
      <div className="flex flex-col items-center justify-center h-96">
        <Activity className="h-8 w-8 text-primary animate-spin" />
        <p className="text-sm text-muted-foreground mt-3">
          Loading event dossier, options intelligence & prediction snapshot...
        </p>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="p-8 border border-rose-500/20 bg-rose-500/5 rounded-xl text-center max-w-lg mx-auto mt-12">
        <AlertTriangle className="h-8 w-8 text-rose-400 mx-auto" />
        <h2 className="text-lg font-bold text-foreground mt-2">Event Dossier Not Found</h2>
        <p className="text-xs text-muted-foreground mt-1">{error || 'Unknown error'}</p>
        <Link
          href="/events"
          className="mt-4 inline-flex items-center gap-1.5 text-xs text-primary underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Events Dashboard
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
    <div className="space-y-6 pb-16 max-w-6xl mx-auto">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href="/events"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Event Intelligence
        </Link>

        <button
          onClick={handleRefreshLive}
          disabled={refreshingLive}
          className="flex items-center gap-1.5 text-xs font-semibold text-primary bg-primary/10 hover:bg-primary/20 border border-primary/20 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshingLive ? 'animate-spin' : ''}`} />
          {refreshingLive ? 'Refreshing Live...' : 'Refresh Live Options'}
        </button>
      </div>

      {/* Hero Header */}
      <div className="rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md shadow-sm space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 rounded-md bg-sky-500/10 border border-sky-500/20 px-2.5 py-1 text-xs font-bold text-sky-400">
              <Building2 className="h-3.5 w-3.5" />
              {event.entity_name} ({event.entity_id})
            </span>
            <span className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              {event.event_type} · {event.sub_type?.replace(/_/g, ' ')}
            </span>
            <span
              className={`rounded-md px-2.5 py-1 text-xs font-semibold ${
                event.temporal_phase === 'ACTIVE'
                  ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30 animate-pulse'
                  : event.temporal_phase === 'APPROACHING'
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              Phase: {event.temporal_phase}
            </span>
            <span className="flex items-center gap-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 text-xs font-semibold text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              {event.verification_status} · {event.certainty}
            </span>
          </div>

          <span className="font-mono text-xs text-muted-foreground">
            ID: {event.canonical_event_id}
          </span>
        </div>

        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
            {event.title}
          </h1>
          {event.description && (
            <p className="text-sm text-muted-foreground mt-2 leading-relaxed max-w-3xl">
              {event.description}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-6 pt-2 border-t border-border/40 text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-sky-400" />
            <span className="font-medium text-foreground">{dateStr}</span> at{' '}
            <span className="font-medium text-foreground">{timeStr} IST</span>
          </div>
          <div>
            Precision: <span className="font-semibold text-foreground">{event.timestamp_precision}</span>
          </div>
          <div>
            Horizon: <span className="font-semibold text-foreground">{event.time_horizon}</span>
          </div>
          <div>
            Direction Bias: <span className="font-semibold text-foreground">{event.expected_direction}</span>
          </div>
        </div>
      </div>

      {/* Institutional Options & Volatility Surface Intelligence (§18) */}
      <div className="rounded-xl border border-sky-500/30 bg-sky-950/10 p-6 shadow-sm space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-sky-400" />
            <h2 className="text-base font-bold text-foreground">
              Live Options Context & Volatility Surface Intelligence (§18)
            </h2>
          </div>
          {liveOptions && (
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="rounded bg-sky-500/20 text-sky-300 border border-sky-500/30 px-2 py-0.5 font-bold">
                Underlying: {liveOptions.underlying}
              </span>
              <span className="text-muted-foreground">
                DTE: {liveOptions.days_to_expiry.toFixed(1)}d ({liveOptions.expiry})
              </span>
            </div>
          )}
        </div>

        {liveOptions ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {/* Spot vs Futures */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Spot / Futures</span>
              <div className="text-sm font-bold font-mono text-foreground">
                ₹{liveOptions.spot_price.toLocaleString('en-IN')}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono">
                Basis: <span className="text-sky-300">{liveOptions.basis_points > 0 ? `+${liveOptions.basis_points}` : liveOptions.basis_points} pts</span>
              </div>
            </div>

            {/* ATM Strike & Straddle */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">ATM Strike & Straddle</span>
              <div className="text-sm font-bold font-mono text-foreground">
                {liveOptions.atm_strike.toLocaleString('en-IN')}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono">
                LTP: ₹{liveOptions.atm_straddle_price ? liveOptions.atm_straddle_price.toFixed(1) : 'N/A'}
              </div>
            </div>

            {/* ATM Implied Vol */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">ATM Implied Vol (IV)</span>
              <div className="text-sm font-bold font-mono text-amber-300">
                {liveOptions.atm_iv ? `${liveOptions.atm_iv.toFixed(1)}%` : 'N/A'}
              </div>
              <div className="text-[10px] text-muted-foreground">Volatility Surface</div>
            </div>

            {/* Expected Move */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Expected Move (±)</span>
              <div className="text-sm font-bold font-mono text-sky-400">
                {liveOptions.expected_move_points ? `±${liveOptions.expected_move_points.toFixed(0)} pts` : 'N/A'}
              </div>
              <div className="text-[10px] text-muted-foreground font-mono">
                {liveOptions.expected_move_pct ? `±${liveOptions.expected_move_pct.toFixed(2)}%` : 'Calibrating'}
              </div>
            </div>

            {/* Bid/Ask Spread friction */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">Bid/Ask Spread</span>
              <div className="text-sm font-bold font-mono text-foreground">
                {liveOptions.bid_ask_spread_pct.toFixed(2)}%
              </div>
              <div className="text-[10px] flex items-center gap-1 font-semibold">
                {liveOptions.spread_acceptable ? (
                  <span className="text-emerald-400">Acceptable</span>
                ) : (
                  <span className="text-rose-400">High Friction</span>
                )}
              </div>
            </div>

            {/* IV Crush Risk */}
            <div className="rounded-lg bg-background/60 border border-border/50 p-3 space-y-1">
              <span className="text-[11px] text-muted-foreground">IV Crush Risk</span>
              <div className="text-sm font-bold font-mono text-foreground">
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs font-bold ${
                    liveOptions.iv_crush_risk_level === 'EXTREME' || liveOptions.iv_crush_risk_level === 'HIGH'
                      ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                      : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  }`}
                >
                  {liveOptions.iv_crush_risk_level}
                </span>
              </div>
              <div className="text-[10px] text-muted-foreground">Post-Event Deflation</div>
            </div>
          </div>
        ) : (
          <div className="rounded-lg bg-background/40 border border-border/40 p-4 text-center text-xs text-muted-foreground">
            Live options connection pending for this underlying. Showing offline risk envelope.
          </div>
        )}
      </div>

      {/* 3 Independent Dimensions Grid (§1, §12, §14, §15) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Dimension 1: Event Importance */}
        <div className="rounded-xl border border-sky-500/30 bg-sky-950/10 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase font-bold tracking-wider text-sky-400">
              1. Event Importance Score
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§12 Formula</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-4xl font-black text-sky-400">{importance?.final_score ?? 0}</span>
            <span className="text-xs text-muted-foreground">/ 100</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Institutional weight derived from source authority ({event.entity_id}), policy impact, and macroeconomic scope.
          </p>

          {/* Explainability Breakdown (§32) */}
          {importance && (
            <div className="pt-3 border-t border-sky-500/20 space-y-1.5 text-xs">
              <div className="text-[11px] font-semibold text-sky-300">Factor Breakdown:</div>
              <div className="flex justify-between text-muted-foreground">
                <span>Source Authority (25%):</span>
                <span className="font-mono text-foreground">{importance.source_authority}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Scope (20%):</span>
                <span className="font-mono text-foreground">{importance.scope}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Historical Significance (20%):</span>
                <span className="font-mono text-foreground">{importance.historical_significance}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Policy Impact (15%):</span>
                <span className="font-mono text-foreground">{importance.policy_impact}</span>
              </div>
              <div className="flex justify-between text-muted-foreground">
                <span>Surprise Potential (20%):</span>
                <span className="font-mono text-foreground">{importance.surprise_potential}</span>
              </div>
            </div>
          )}
        </div>

        {/* Dimension 2: Expected Market Impact */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/10 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase font-bold tracking-wider text-amber-400">
              2. Expected Market Impact
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§14 Regimes</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-amber-400">
              {marketImpact?.final_score != null
                ? `${marketImpact.final_score} / 100`
                : marketImpact?.status || 'INSUFFICIENT'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {marketImpact?.reason || 'Dynamic volatility & historical sensitivity regime.'}
          </p>
          <div className="pt-3 border-t border-amber-500/20 text-xs text-muted-foreground space-y-1">
            <div className="text-[11px] font-semibold text-amber-300">Integrity Rule (§33):</div>
            <p>
              Values are strictly grounded in empirical variance. Zero placeholder fabrication.
            </p>
          </div>
        </div>

        {/* Dimension 3: Trading Opportunity & Hard Gates (§15, §16) */}
        <div className="rounded-xl border border-border/80 bg-card/50 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs uppercase font-bold tracking-wider text-muted-foreground">
              3. Trading Opportunity Score
            </span>
            <span className="text-[11px] text-muted-foreground font-mono">§15 Perishable</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-black ${
                opportunity?.final_decision === 'EXECUTE_SHADOW'
                  ? 'text-purple-400'
                  : opportunity?.final_decision === 'WAIT_FOR_CONFIRMATION'
                  ? 'text-amber-400'
                  : 'text-rose-400'
              }`}
            >
              {opportunity?.final_score != null ? `${opportunity.final_score} / 100` : opportunity?.final_decision || 'NO_TRADE'}
            </span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {opportunity?.reason || 'Live hard-gates evaluation against liquidity, spread, and signal confidence.'}
          </p>

          <div className="pt-3 border-t border-border/40 text-xs space-y-2">
            <div className="text-[11px] font-semibold text-foreground">Hard Gates Breakdown (§16):</div>
            <div className="space-y-1 font-mono text-[11px]">
              {opportunity?.passed_gates && opportunity.passed_gates.map((g) => (
                <div key={g} className="flex items-center justify-between text-emerald-400">
                  <span>{g}:</span>
                  <span className="flex items-center gap-1 font-semibold">
                    <CheckCircle2 className="h-3 w-3" /> PASSED
                  </span>
                </div>
              ))}
              {opportunity?.failed_gates && opportunity.failed_gates.map((g) => (
                <div key={g} className="flex items-center justify-between text-rose-400">
                  <span>{g}:</span>
                  <span className="flex items-center gap-1 font-semibold">
                    <XCircle className="h-3 w-3" /> FAILED
                  </span>
                </div>
              ))}
              {(!opportunity?.passed_gates?.length && !opportunity?.failed_gates?.length) && (
                <div className="text-muted-foreground">No gate data available.</div>
              )}
            </div>

            <div className="pt-2 border-t border-border/30 flex items-center justify-between font-semibold">
              <span className="text-muted-foreground">Decision:</span>
              <span
                className={`rounded px-2 py-0.5 text-xs font-mono font-bold ${
                  opportunity?.final_decision === 'EXECUTE_SHADOW'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                }`}
              >
                {opportunity?.final_decision || 'NO_TRADE'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Shadow Mode Signal Forward-Testing Block (§3, §27) */}
      <div className="rounded-xl border border-purple-500/30 bg-purple-950/10 p-5 shadow-sm space-y-3 backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 text-purple-400" />
            <h3 className="text-sm font-bold text-foreground">
              Event → Signal Integration · SHADOW_MODE (§3, §27)
            </h3>
          </div>
          <span className="text-[10px] rounded bg-purple-500/20 text-purple-300 border border-purple-500/40 px-2 py-0.5 font-mono font-bold">
            Zero Real Capital Risk
          </span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          In strict compliance with §3 and §27, this engine operates in full forward-testing SHADOW_MODE. No live broker orders are placed automatically.
        </p>

        {shadowSignals.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
            {shadowSignals.map((sig) => (
              <div
                key={sig.shadow_signal_id}
                className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1.5 text-xs font-mono"
              >
                <div className="flex items-center justify-between font-bold text-foreground">
                  <span className="text-purple-300">{sig.shadow_signal_id}</span>
                  <span className="rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] text-purple-300">
                    {sig.shadow_status}
                  </span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Strategy:</span>
                  <span className="text-foreground">{sig.strategy} ({sig.direction})</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Underlying:</span>
                  <span className="text-foreground">{sig.underlying}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Simulated Entry:</span>
                  <span className="text-foreground">₹{sig.simulated_entry_price?.toFixed(2) || 'MARKET'}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Sizing Factor:</span>
                  <span className="text-foreground">{sig.suggested_sizing_factor}x</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg bg-background/40 border border-border/30 p-3 text-xs text-muted-foreground">
            No active shadow execution record generated yet for this canonical event.
          </div>
        )}
      </div>

      {/* Post-Event Market Reaction & Quantitative Outcome Card (§24) */}
      <div className="rounded-xl border border-border/60 bg-card/50 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-emerald-400" />
            <h2 className="text-base font-bold text-foreground">
              Post-Event Market Reaction & Outcome (§24)
            </h2>
          </div>
          <span className="text-xs text-muted-foreground font-mono">
            {outcome ? (outcome.is_settled ? 'STATUS: SETTLED' : 'STATUS: MONITORING') : 'STATUS: PENDING TRIGGER'}
          </span>
        </div>

        {outcome ? (
          <div className="space-y-4">
            {/* Outcome KPI Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Direction Accuracy</span>
                <div className="text-sm font-bold text-foreground">
                  {outcome.prediction_correct ? (
                    <span className="text-emerald-400 flex items-center gap-1">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Correct
                    </span>
                  ) : (
                    <span className="text-rose-400 flex items-center gap-1">
                      <XCircle className="h-3.5 w-3.5" /> Incorrect
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-muted-foreground">
                  Act: {outcome.actual_direction}
                </div>
              </div>

              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Initial Reaction (1m)</span>
                <div className="text-sm font-bold font-mono text-foreground">
                  {outcome.initial_move_pct > 0 ? `+${outcome.initial_move_pct}%` : `${outcome.initial_move_pct}%`}
                </div>
                <div className="text-[10px] text-muted-foreground">Immediate Spike</div>
              </div>

              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Maximum Move</span>
                <div className="text-sm font-bold font-mono text-sky-400">
                  {outcome.maximum_move_pct > 0 ? `+${outcome.maximum_move_pct}%` : `${outcome.maximum_move_pct}%`}
                </div>
                <div className="text-[10px] text-muted-foreground">Peak Displacement</div>
              </div>

              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">MFE / MAE</span>
                <div className="text-sm font-bold font-mono text-emerald-400">
                  +{outcome.mfe_pct}%
                </div>
                <div className="text-[10px] text-rose-400 font-mono">
                  MAE: -{outcome.mae_pct}%
                </div>
              </div>

              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">Time to Peak</span>
                <div className="text-sm font-bold font-mono text-foreground">
                  {outcome.time_to_peak_min} min
                </div>
                <div className="text-[10px] text-muted-foreground">
                  Rev: {outcome.time_to_reversal_min ? `${outcome.time_to_reversal_min}m` : 'None'}
                </div>
              </div>

              <div className="rounded-lg bg-background/60 border border-border/40 p-3 space-y-1">
                <span className="text-[11px] text-muted-foreground">IV Crush Realized</span>
                <div className="text-sm font-bold font-mono text-rose-400">
                  {outcome.iv_change_pct != null ? `${outcome.iv_change_pct}%` : 'N/A'}
                </div>
                <div className="text-[10px] text-muted-foreground">Vol Deflation</div>
              </div>
            </div>

            {/* Monitoring Snapshots Timeline Table */}
            {outcome.monitoring_snapshots && outcome.monitoring_snapshots.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-semibold text-foreground">
                  Standardized Horizon Progression (T-15M → EOD):
                </div>
                <div className="overflow-x-auto rounded-lg border border-border/40">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-muted/40 text-muted-foreground border-b border-border/40">
                      <tr>
                        <th className="p-2.5">Horizon</th>
                        <th className="p-2.5">Time</th>
                        <th className="p-2.5">Price</th>
                        <th className="p-2.5">Move %</th>
                        <th className="p-2.5">IV</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                      {outcome.monitoring_snapshots.map((snap, idx) => (
                        <tr key={idx} className="hover:bg-muted/20">
                          <td className="p-2.5 font-bold text-foreground">{snap.interval_label}</td>
                          <td className="p-2.5 text-muted-foreground">
                            {new Date(snap.timestamp).toLocaleTimeString('en-IN', {
                              hour: '2-digit',
                              minute: '2-digit',
                              timeZone: 'Asia/Kolkata',
                            })}
                          </td>
                          <td className="p-2.5 text-foreground">₹{snap.price.toFixed(1)}</td>
                          <td
                            className={`p-2.5 font-bold ${
                              snap.move_from_baseline_pct > 0
                                ? 'text-emerald-400'
                                : snap.move_from_baseline_pct < 0
                                ? 'text-rose-400'
                                : 'text-muted-foreground'
                            }`}
                          >
                            {snap.move_from_baseline_pct > 0
                              ? `+${snap.move_from_baseline_pct.toFixed(2)}%`
                              : `${snap.move_from_baseline_pct.toFixed(2)}%`}
                          </td>
                          <td className="p-2.5 text-amber-300">
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
          <div className="rounded-lg bg-background/40 border border-border/30 p-4 text-center text-xs text-muted-foreground space-y-1">
            <p className="font-semibold text-foreground">Awaiting Event Realization</p>
            <p>
              Once this event becomes ACTIVE, the quantitative outcome engine records tick-level trajectory, MFE/MAE, and IV crush across T-15M to EOD.
            </p>
          </div>
        )}
      </div>

      {/* Impact Mapping Hierarchy (§11) */}
      <div className="rounded-xl border border-border/60 bg-card/50 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-4 w-4 text-primary" />
            <h2 className="text-base font-bold text-foreground">
              Impact Mapping Hierarchy (§11)
            </h2>
          </div>
          <span className="text-xs text-muted-foreground">Event → Sector → Stock → Index → Derivative</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {event.impact_mappings.map((mapping, idx) => (
            <div
              key={idx}
              className="rounded-lg border border-border/50 bg-background/50 p-3.5 space-y-2 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-foreground font-mono text-sm">
                  {mapping.target_symbol}
                </span>
                <span className="rounded bg-secondary px-2 py-0.5 text-[10px] font-semibold text-secondary-foreground">
                  {mapping.target_type}
                </span>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>Impact Strength:</span>
                <span className="font-semibold text-rose-400">{mapping.impact_strength}</span>
              </div>
              <div className="flex items-center justify-between text-muted-foreground">
                <span>Relationship Confidence:</span>
                <span className="font-semibold text-emerald-400">
                  {Math.round(mapping.relationship_confidence * 100)}%
                </span>
              </div>
              {mapping.notes && (
                <p className="text-[11px] text-muted-foreground pt-1 border-t border-border/30">
                  {mapping.notes}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Two Column Section: Prediction Snapshot & Historical Comparables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Immutable Prediction Snapshot (§20, §21) */}
        <div className="rounded-xl border border-border/60 bg-card/50 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCheck2 className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-foreground">
                Immutable Prediction Snapshot (§20)
              </h3>
            </div>
            <span className="text-[10px] rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 font-semibold">
              Anti-Lookahead Protected
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Preserved at decision cutoff to strictly prevent hindsight bias. Cannot be modified retroactively.
          </p>

          {prediction && (
            <div className="rounded-lg bg-background/60 border border-border/40 p-3.5 space-y-2 font-mono text-xs">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Prediction ID:</span>
                <span className="text-foreground">{prediction.prediction_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Data Cutoff:</span>
                <span className="text-sky-300">
                  {new Date(prediction.data_cutoff_timestamp).toISOString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Decision Verdict:</span>
                <span className="text-rose-400 font-bold">{prediction.decision}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Formula Version:</span>
                <span className="text-muted-foreground">{prediction.formula_version}</span>
              </div>
            </div>
          )}
        </div>

        {/* Historical Precedents (§22) */}
        <div className="rounded-xl border border-border/60 bg-card/50 p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="h-4 w-4 text-amber-400" />
              <h3 className="text-sm font-bold text-foreground">
                Historical Comparables (§22)
              </h3>
            </div>
            <span className="text-[10px] text-muted-foreground">Strict Time Cutoffs</span>
          </div>

          <div className="space-y-2.5">
            {event.comparables.map((comp, idx) => (
              <div
                key={idx}
                className="rounded-lg bg-background/60 border border-border/40 p-3 text-xs space-y-1"
              >
                <div className="flex items-center justify-between font-semibold text-foreground">
                  <span>{comp.key_comparison_factor}</span>
                  <span className="text-amber-400 font-mono">
                    {Math.round(comp.similarity_score * 100)}% match
                  </span>
                </div>
                <div className="text-muted-foreground text-[11px]">
                  Date: {comp.past_event_date} · ID: {comp.past_event_id}
                </div>
                {comp.past_market_reaction && (
                  <div className="flex gap-3 text-[11px] pt-1 text-muted-foreground font-mono">
                    <span>15m: +{String(comp.past_market_reaction.banknifty_15m_move_pct ?? '0')}%</span>
                    <span>Day: +{String(comp.past_market_reaction.banknifty_day_move_pct ?? '0')}%</span>
                    <span className="text-rose-400">
                      IV: {String(comp.past_market_reaction.iv_crush_pct ?? '0')}%
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Ingested Sources Lineage (§5) */}
      <div className="rounded-xl border border-border/60 bg-card/50 p-5 shadow-sm space-y-3">
        <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          Ingested Source Lineage & Verification (§5)
        </h3>
        <div className="space-y-2">
          {event.sources.map((source, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between rounded-lg bg-background/40 border border-border/30 px-3.5 py-2.5 text-xs"
            >
              <div className="flex items-center gap-2">
                <span className="font-semibold text-foreground">{source.source_name}</span>
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {source.source_type}
                </span>
                {source.is_verified && (
                  <span className="text-emerald-400 flex items-center gap-1 text-[11px]">
                    <CheckCircle2 className="h-3 w-3" /> Verified Official
                  </span>
                )}
              </div>

              {source.source_url && (
                <a
                  href={source.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-primary hover:underline text-[11px]"
                >
                  Source URL <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
