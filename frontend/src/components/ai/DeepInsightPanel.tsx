'use client';

import React from 'react';
import { useDeepInsight } from '@/context/DeepInsightContext';
import type { DeepInsightSignal, DeepInsightExecution, DeepInsightValidation, DeepInsightProvider, DeepInsightSetup, DeepInsightRisk, DeepInsightEvidence } from '@/lib/deep-insight-types';

function Badge({ variant = 'default', children }: { variant?: 'default' | 'success' | 'warning' | 'danger' | 'info'; children: React.ReactNode }) {
  const styles: Record<string, string> = {
    default: 'bg-muted text-muted-foreground border-border',
    success: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
    warning: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
    danger: 'bg-red-500/10 text-red-600 border-red-500/20',
    info: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${styles[variant]}`}>
      {children}
    </span>
  );
}

function SectionCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-card border border-border rounded-lg p-3 ${className}`}>
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, value, badge }: { label: string; value?: string | number | null; badge?: React.ReactNode }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="flex justify-between items-center py-1 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{badge || value}</span>
    </div>
  );
}

function SignalBadge({ decision }: { decision: string }) {
  switch (decision) {
    case 'LONG': return <Badge variant="success">LONG</Badge>;
    case 'SHORT': return <Badge variant="danger">SHORT</Badge>;
    default: return <Badge variant="default">NEUTRAL</Badge>;
  }
}

function ValidationBadge({ validation }: { validation: DeepInsightValidation | null }) {
  if (!validation) return null;
  if (validation.decision === 'ACCEPT') {
    return <Badge variant="success">APPROVED</Badge>;
  }
  return <Badge variant="danger">REJECTED</Badge>;
}

function ExecutionBadge({ execution }: { execution: DeepInsightExecution | null }) {
  if (!execution) return null;
  if (execution.decision === 'PASS') {
    return <Badge variant="success">PASS</Badge>;
  }
  return <Badge variant="danger">REJECT</Badge>;
}

function RegimeBadge({ regime }: { regime: string }) {
  const variant = regime === 'TREND' ? 'info' : regime === 'RANGE' ? 'default' : regime === 'BREAKOUT' ? 'success' : 'warning';
  return <Badge variant={variant}>{regime}</Badge>;
}

function DirectionBadge({ direction }: { direction: string }) {
  switch (direction) {
    case 'BULLISH': return <Badge variant="success">BULLISH</Badge>;
    case 'BEARISH': return <Badge variant="danger">BEARISH</Badge>;
    default: return <Badge variant="default">NEUTRAL</Badge>;
  }
}

function ConfidenceMeter({ value }: { value: number }) {
  const color = value >= 70 ? 'bg-emerald-500' : value >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-sm font-medium w-8 text-right">{value}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-12 text-muted-foreground">
      <div className="animate-pulse flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-sm">AI analysis in progress...</span>
      </div>
    </div>
  );
}

function ErrorState({ error }: { error: string }) {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-center">
        <div className="text-red-500 text-lg font-medium mb-2">AI Unavailable</div>
        <div className="text-muted-foreground text-sm">{error}</div>
      </div>
    </div>
  );
}

function StaleState({ message }: { message: string | null }) {
  return (
    <div className="flex items-center justify-center py-4">
      <Badge variant="warning">STALE{message ? `: ${message}` : ''}</Badge>
    </div>
  );
}

function ExpiredState() {
  return (
    <div className="flex items-center justify-center py-12">
      <Badge variant="danger">EXPIRED</Badge>
    </div>
  );
}

function UnavailableState({ message }: { message: string | null }) {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-center">
        <div className="text-muted-foreground text-lg font-medium mb-2">AI Unavailable</div>
        {message && <div className="text-sm text-muted-foreground">{message}</div>}
      </div>
    </div>
  );
}

function MarketSummaryCard({ signal }: { signal: DeepInsightSignal | null }) {
  if (!signal) return null;
  return (
    <SectionCard title="MARKET">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl font-bold">{signal.symbol}</span>
        <RegimeBadge regime={signal.regime} />
        <DirectionBadge direction={signal.direction} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Row label="AI Bias" value="" badge={<SignalBadge decision={signal.aiBias} />} />
        <Row label="Confidence" value="" badge={<ConfidenceMeter value={signal.confidence} />} />
        <Row label="Calibrated" value={`${signal.calibratedConfidence}`} />
        <Row label="Regime Strength" value={`${signal.confidence}/100`} />
      </div>
    </SectionCard>
  );
}

function SignalLifecycleCard({ signal }: { signal: DeepInsightSignal | null }) {
  if (!signal) return null;
  return (
    <SectionCard title="SIGNAL LIFECYCLE">
      <div className="grid grid-cols-2 gap-2">
        <Row label="State" value={signal.state} />
        <Row label="Age" value={`${signal.age}s`} />
        <Row label="TTL" value={`${signal.ttl}s`} />
        <Row label="Remaining" value={`${signal.ttlRemaining}s`} />
        <Row label="Setup" value={signal.setupType} />
        <Row label="Timeframe" value={signal.timeframe} />
      </div>
    </SectionCard>
  );
}

function SetupCard({ setup }: { setup: DeepInsightSetup | null }) {
  if (!setup) return null;
  return (
    <SectionCard title="AI TRADE IDEA">
      <div className="space-y-1">
        <Row label="Setup" value={setup.setupType} />
        <Row label="Entry Zone" value={setup.entryZone} />
        <Row label="Stop Loss" value={setup.stopLoss} />
        <Row label="Target" value={setup.target} />
        <Row label="Risk:Reward" value="" badge={<span className="text-emerald-600 font-bold">1:{setup.riskReward}</span>} />
      </div>
    </SectionCard>
  );
}

function EvidenceCard({ evidence }: { evidence: DeepInsightEvidence | null }) {
  if (!evidence) return null;
  return (
    <SectionCard title="WHY AI LIKES IT">
      <div className="space-y-1">
        {evidence.positive.map((item, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="text-emerald-500">✓</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function RiskCard({ risk, execution }: { risk: DeepInsightRisk | null; execution: DeepInsightExecution | null }) {
  if (!risk && !execution) return null;
  const reasons = risk?.mainRisks || [];
  const invalidations = risk?.invalidation || [];
  const execReason = execution?.decision === 'REJECT' ? execution.reasonDetail : null;

  const allRisks = [...reasons, ...invalidations];
  if (allRisks.length === 0 && !execReason) return null;

  return (
    <SectionCard title="WHAT CAN GO WRONG">
      <div className="space-y-1">
        {execReason && (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <span>✗</span>
            <span>{execReason}</span>
          </div>
        )}
        {allRisks.map((item, i) => (
          <div key={i} className="flex items-center gap-2 text-sm">
            <span className="text-amber-500">•</span>
            <span>{item}</span>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function ValidationCard({ validation, execution }: { validation: DeepInsightValidation | null; execution: DeepInsightExecution | null }) {
  if (!validation && !execution) return null;
  return (
    <SectionCard title="VALIDATION">
      <div className="flex items-center gap-3">
        <ValidationBadge validation={validation} />
        <ExecutionBadge execution={execution} />
        {validation?.rejectionReason && (
          <span className="text-xs text-muted-foreground">{validation.rejectionReason}</span>
        )}
      </div>
    </SectionCard>
  );
}

function SystemCard({ provider, dataQuality }: { provider: DeepInsightProvider | null; dataQuality: { completeness: number; status: string } | null }) {
  if (!provider && !dataQuality) return null;
  return (
    <SectionCard title="SYSTEM">
      <div className="grid grid-cols-2 gap-2">
        {provider && (
          <>
            <Row label="Provider" value={provider.name} />
            <Row label="Model" value={provider.model} />
            <Row label="Latency" value={`${provider.latencyMs}ms`} />
          </>
        )}
        {dataQuality && (
          <>
            <Row label="Data Quality" value="" badge={<span className="text-sm">{dataQuality.completeness}%</span>} />
            <Row label="Status" value={dataQuality.status} />
          </>
        )}
      </div>
    </SectionCard>
  );
}

export function DeepInsightPanel() {
  const { state } = useDeepInsight();

  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'error') return <ErrorState error={state.error || 'Unknown error'} />;
  if (state.status === 'stale') return <StaleState message={state.staleMessage} />;
  if (state.status === 'expired') return <ExpiredState />;
  if (state.status === 'unavailable') return <UnavailableState message={state.error} />;
  if (state.status === 'idle') return <UnavailableState message="Select a symbol to analyze" />;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <MarketSummaryCard signal={state.signal} />
        <SignalLifecycleCard signal={state.signal} />
      </div>

      <SetupCard setup={state.setup} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <EvidenceCard evidence={state.evidence} />
        <RiskCard risk={state.risk} execution={state.execution} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ValidationCard validation={state.validation} execution={state.execution} />
        <SystemCard provider={state.provider} dataQuality={state.dataQuality} />
      </div>
    </div>
  );
}
