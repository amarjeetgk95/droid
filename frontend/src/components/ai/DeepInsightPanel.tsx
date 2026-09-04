'use client';

import React from 'react';
import { useDeepInsight } from '@/context/DeepInsightContext';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import type { DeepInsightDirection, DeepInsightRegime, DeepInsightSignalState } from '@/lib/deep-insight-types';

function fmt(n: number | undefined | null, digits = 2): string {
  if (n === undefined || n === null || isNaN(n)) return '—';
  return n.toFixed(digits);
}

function directionVariant(d: DeepInsightDirection | string): 'default' | 'success' | 'destructive' | 'secondary' {
  switch (d) {
    case 'BULLISH': return 'success';
    case 'BEARISH': return 'destructive';
    case 'NEUTRAL': return 'secondary';
    default: return 'default';
  }
}

function regimeVariant(r: DeepInsightRegime | string): 'default' | 'success' | 'destructive' | 'secondary' {
  switch (r) {
    case 'TREND': return 'success';
    case 'RANGE': return 'secondary';
    case 'BREAKOUT': return 'success';
    case 'REVERSAL': return 'destructive';
    default: return 'default';
  }
}

function ConfidenceBar({ value }: { value: number }) {
  if (value <= 0) return null;
  const color = value >= 70 ? 'bg-emerald-500' : value >= 50 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      </div>
      <span className="text-xs font-medium w-7 text-right">{value}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-muted-foreground">Fetching market intelligence...</span>
      </div>
    </div>
  );
}

function ErrorState({ msg }: { msg: string }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <div className="text-red-500 font-semibold mb-1">Error</div>
        <div className="text-muted-foreground text-sm">{msg || 'Failed to load deep insight'}</div>
      </div>
    </div>
  );
}

function UnavailableState({ msg }: { msg?: string | null }) {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <div className="text-muted-foreground font-semibold mb-1">AI Unavailable</div>
        {msg && <div className="text-muted-foreground text-sm">{msg}</div>}
      </div>
    </div>
  );
}

function SignalBadge({ state }: { state: DeepInsightSignalState | null }) {
  if (!state) return null;
  const colors: Record<string, string> = {
    ACTIVE: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
    ANALYZING: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
    VALIDATING: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
    APPROVED: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
    REJECTED: 'bg-red-500/10 text-red-600 border-red-500/20',
    EXPIRED: 'bg-muted text-muted-foreground border-border',
    SUPERSEDED: 'bg-muted text-muted-foreground border-border',
    AI_UNAVAILABLE: 'bg-muted text-muted-foreground border-border',
  };
  return (
    <Badge className={`border ${colors[state.state] || colors.AI_UNAVAILABLE}`}>
      {state.state}
    </Badge>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN DECISION TABLE — the primary user-facing product per §4
// ─────────────────────────────────────────────────────────────────────────────
function MainDecisionTable() {
  const { state } = useDeepInsight();
  const { market, aiView, signalState, multiTimeframe, setup, validation } = state;

  const tfMap: Record<string, DeepInsightDirection> = {};
  const tfStruct: Record<string, string> = {};
  const tfStrength: Record<string, number> = {};
  for (const tf of multiTimeframe) {
    tfMap[tf.timeframe] = tf.direction;
    tfStruct[tf.timeframe] = tf.structure;
    tfStrength[tf.timeframe] = tf.strength;
  }

  type Row = [string, React.ReactNode, string];
  const rows: Row[] = [
    ['Market Regime', market ? (
      <div className="flex items-center gap-2">
        <Badge variant={regimeVariant(market.regime)}>{market.regime}</Badge>
        <Badge variant={directionVariant(market.direction)}>{market.direction}</Badge>
      </div>
    ) : '—', market ? `${fmt(market.regime_strength)}/100` : '—'],
    ['AI Bias', aiView ? (
      <div className="flex items-center gap-2">
        <Badge variant={aiView.bias === 'LONG' ? 'success' : aiView.bias === 'SHORT' ? 'destructive' : 'default'}>{aiView.bias}</Badge>
        <ConfidenceBar value={aiView.confidence} />
      </div>
    ) : '—', aiView ? `${aiView.confidence}/100` : '—'],
    ['1M', tfMap['1M'] ? <Badge variant={directionVariant(tfMap['1M'])}>{tfMap['1M']}</Badge> : '—', tfStruct['1M'] || '—'],
    ['3M', tfMap['3M'] ? <Badge variant={directionVariant(tfMap['3M'])}>{tfMap['3M']}</Badge> : '—', tfStruct['3M'] || '—'],
    ['5M', tfMap['5M'] ? <Badge variant={directionVariant(tfMap['5M'])}>{tfMap['5M']}</Badge> : '—', tfStruct['5M'] || '—'],
    ['15M', tfMap['15M'] ? <Badge variant={directionVariant(tfMap['15M'])}>{tfMap['15M']}</Badge> : '—', tfStruct['15M'] || '—'],
    ['VWAP', market?.levels ? (
      <span className={`font-medium ${market.levels.vwap_relation === 'Above' ? 'text-emerald-600' : market.levels.vwap_relation === 'Below' ? 'text-red-600' : 'text-muted-foreground'}`}>
        {market.levels.vwap_relation}
      </span>
    ) : '—', market?.levels?.vwap ? `${fmt(market.levels.vwap)}` : '—'],
    ['Momentum', market?.momentum ? (
      <span className={market.momentum.status === 'Positive' ? 'text-emerald-600' : market.momentum.status === 'Negative' ? 'text-red-600' : 'text-muted-foreground'}>
        {market.momentum.status}
      </span>
    ) : '—', market?.momentum?.value !== undefined ? `${fmt(market.momentum.value)}` : '—'],
    ['Volume', market?.volume ? (
      <Badge variant={market.volume.status === 'High' ? 'success' : market.volume.status === 'Low' ? 'destructive' : 'secondary'}>{market.volume.status}</Badge>
    ) : '—', market?.volume?.relative_value !== undefined ? `${fmt(market.volume.relative_value)}× avg` : '—'],
    ['Support', market?.levels?.support ? <span className="font-medium">{fmt(market.levels.support)}</span> : '—', 'Key level'],
    ['Resistance', market?.levels?.resistance ? <span className="font-medium">{fmt(market.levels.resistance)}</span> : '—', 'Decision level'],
    ['Setup', setup?.setup_type && setup.setup_type !== 'NO_SETUP' ? <Badge>{setup.setup_type}</Badge> : <span className="text-xs text-muted-foreground">No active setup</span>, setup && setup.risk_reward > 0 ? `R:R 1:${fmt(setup.risk_reward)}` : '—'],
    ['Entry Zone', setup && setup.entry_zone && setup.entry_zone !== '0' && setup.entry_zone !== '—' ? <span className="font-medium">{setup.entry_zone}</span> : '—', setup && setup.stop_loss > 0 ? `SL ${fmt(setup.stop_loss)}` : '—'],
    ['Target', setup && setup.target && setup.target !== '0' && setup.target !== '—' ? <span className="font-medium">{setup.target}</span> : '—', setup && setup.target && setup.target !== '0' && setup.target !== '—' ? 'Proposed' : '—'],
    ['Stop Loss', setup && setup.stop_loss > 0 ? <span className="text-red-500 font-medium">{fmt(setup.stop_loss)}</span> : '—', setup && setup.stop_loss > 0 ? 'Invalidation' : '—'],
    ['Backend Validation', validation ? (
      <Badge variant={validation.status === 'ACCEPT' || validation.status === 'PASS' ? 'success' : 'destructive'}>{validation.status}</Badge>
    ) : '—', validation?.rejection_reason || '—'],
    /* eslint-disable-next-line react/jsx-key */ // rendered via map; key assigned at map site
    ['Signal Status', <SignalBadge state={signalState} />, signalState ? `${signalState.age}s old · ${signalState.ttl_remaining}s left` : '—'],
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-2 pr-4 font-semibold text-muted-foreground">Factor</th>
            <th className="text-left py-2 pr-4 font-semibold text-muted-foreground">Current Finding</th>
            <th className="text-left py-2 font-semibold text-muted-foreground">Strength / Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([factor, finding, evidence]) => (
            <tr key={factor} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
              <td className="py-1.5 pr-4 text-muted-foreground font-medium">{factor}</td>
              <td className="py-1.5 pr-4">{finding}</td>
              <td className="py-1.5 text-muted-foreground">{evidence}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MULTI-TIMEFRAME VIEW — per §6
// ─────────────────────────────────────────────────────────────────────────────
function MultiTimeframeTable() {
  const { state } = useDeepInsight();
  const { multiTimeframe } = state;

  if (!multiTimeframe || multiTimeframe.length === 0) {
    return <div className="text-sm text-muted-foreground py-2">— Unavailable</div>;
  }

  const bullCount = multiTimeframe.filter(t => t.direction === 'BULLISH').length;
  const bearCount = multiTimeframe.filter(t => t.direction === 'BEARISH').length;
  const total = multiTimeframe.length;
  const alignment = bullCount === total ? 'STRONG BULLISH' : bearCount === total ? 'STRONG BEARISH' : bullCount === 0 && bearCount === 0 ? 'MIXED' : bullCount > bearCount ? 'BULLISH LEAD' : 'BEARISH LEAD';

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">MULTI-TF ALIGNMENT:</span>
        <Badge variant={bullCount > bearCount ? 'success' : bearCount > bullCount ? 'destructive' : 'secondary'}>{alignment}</Badge>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left py-1.5 pr-4 font-semibold text-muted-foreground">Timeframe</th>
            <th className="text-left py-1.5 pr-4 font-semibold text-muted-foreground">Direction</th>
            <th className="text-right py-1.5 pr-4 font-semibold text-muted-foreground">Strength</th>
            <th className="text-left py-1.5 font-semibold text-muted-foreground">Structure</th>
          </tr>
        </thead>
        <tbody>
          {multiTimeframe.map((tf) => (
            <tr key={tf.timeframe} className="border-b border-border/50">
              <td className="py-1.5 pr-4 font-medium">{tf.timeframe}</td>
              <td className="py-1.5 pr-4"><Badge variant={directionVariant(tf.direction)}>{tf.direction}</Badge></td>
              <td className="py-1.5 pr-4 text-right">
                <div className="flex items-center justify-end gap-2">
                  <div className="w-12 h-1 bg-muted rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${tf.direction === 'BULLISH' ? 'bg-emerald-500' : tf.direction === 'BEARISH' ? 'bg-red-500' : 'bg-muted'}`}
                      style={{ width: `${tf.strength}%` }} />
                  </div>
                  <span className="text-xs w-6 text-right">{tf.strength}</span>
                </div>
              </td>
              <td className="py-1.5 text-muted-foreground">{tf.structure}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// HISTORICAL INSIGHT — per §7
// ─────────────────────────────────────────────────────────────────────────────
function HistoricalTable() {
  const { state } = useDeepInsight();
  const { historicalEvidence } = state;

  if (!historicalEvidence) {
    return <div className="text-sm text-muted-foreground py-2">— Unavailable</div>;
  }

  const h = historicalEvidence;
  const qualityVariant = h.sample_quality === 'GOOD' ? 'success' : h.sample_quality === 'FAIR' ? 'secondary' : 'destructive';

  type HRow = [string, string | number | boolean | null | undefined, 'text' | 'badge'];
  const rows: HRow[] = [
    ['Similar States', h.similar_states > 0 ? h.similar_states : '—', 'text'],
    ['Continuation', h.continuation > 0 ? `${h.continuation.toFixed(0)}%` : '—', 'text'],
    ['Failure', h.failure > 0 ? `${h.failure.toFixed(0)}%` : '—', 'text'],
    ['Reversal', h.reversal > 0 ? `${h.reversal.toFixed(0)}%` : '—', 'text'],
    ['Median Move', h.median_move !== 0 ? `${h.median_move > 0 ? '+' : ''}${fmt(h.median_move, 0)} pts` : '—', 'text'],
    ['Median Duration', h.median_duration || '—', 'text'],
    ['Sample Quality', h.sample_quality || '—', 'badge'],
  ];

  return (
    <div>
      <div className="text-xs text-muted-foreground mb-2 italic">Historical evidence — not a prediction</div>
      <table className="w-full text-sm">
        <tbody>
          {rows.map(([label, value, style]) => (
            <tr key={label} className="border-b border-border/50">
              <td className="py-1.5 pr-4 text-muted-foreground">{label}</td>
              <td className="py-1.5 font-medium text-right">
                {style === 'badge' ? (
                  <Badge variant={qualityVariant}>{value}</Badge>
                ) : (
                  <span>{value}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// OPTIONS INSIGHT — per §8
// ─────────────────────────────────────────────────────────────────────────────
function OptionsTable() {
  const { state } = useDeepInsight();
  const { optionsEvidence } = state;

  if (!optionsEvidence) {
    return <div className="text-sm text-muted-foreground py-2">— Unavailable</div>;
  }

  const o = optionsEvidence;
  type ORow = [string, string | number | boolean | null | undefined, 'badge' | 'text' | 'span-badge'];
  const rows: ORow[] = [
    ['Overall Bias', o.bias, 'badge'],
    ['PCR (OI)', fmt(o.pcr), 'text'],
    ['Put Support', o.put_support > 0 ? fmt(o.put_support) : '—', 'text'],
    ['Call Resistance', o.call_resistance > 0 ? fmt(o.call_resistance) : '—', 'text'],
    ['OI Trend', o.oi_trend, 'badge'],
    ['IV Context', o.iv, 'text'],
    ['Interpretation', o.interpretation || '—', 'text'],
  ];

  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([label, value, style]) => (
          <tr key={label} className="border-b border-border/50">
            <td className="py-1.5 pr-4 text-muted-foreground">{label}</td>
            <td className="py-1.5 font-medium text-right">
              {style === 'badge' ? (
                <Badge variant={directionVariant(value as DeepInsightDirection)}>{value}</Badge>
              ) : (
                <span>{value}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AI VIEW / EVIDENCE / RISK — per §5
// ─────────────────────────────────────────────────────────────────────────────
function AiViewSection() {
  const { state } = useDeepInsight();
  const { aiView, technicalEvidence, risks, invalidation } = state;

  if (!aiView || Object.keys(aiView).length === 0) {
    return <div className="text-sm text-muted-foreground py-2">— Unavailable</div>;
  }

  return (
    <div className="space-y-3">
      <div className="p-3 bg-muted/30 rounded-lg">
        <div className="text-xs text-muted-foreground mb-1 font-semibold">AI SUMMARY</div>
        <div className="text-sm font-medium mb-2">{aiView.summary || '—'}</div>
        <div className="flex items-center gap-2">
          <Badge variant={aiView.bias === 'LONG' ? 'success' : aiView.bias === 'SHORT' ? 'destructive' : 'default'}>{aiView.bias}</Badge>
          <span className="text-xs text-muted-foreground">Confidence {aiView.confidence}/100</span>
          {Boolean(aiView.calibrated_confidence && aiView.calibrated_confidence !== aiView.confidence) && (
            <span className="text-xs text-muted-foreground">· Calibrated {aiView.calibrated_confidence}/100</span>
          )}
        </div>
      </div>

      {technicalEvidence && technicalEvidence.positive && technicalEvidence.positive.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground mb-1 font-semibold">WHY AI LIKES IT</div>
          <div className="space-y-1">
            {technicalEvidence.positive.map((item, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <span className="text-emerald-500 shrink-0 mt-0.5">✓</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {risks && risks.main_risks && risks.main_risks.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground mb-1 font-semibold">RISKS / INVALIDATION</div>
          <div className="space-y-1">
            {[...risks.main_risks, ...invalidation].slice(0, 5).map((item, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <span className="text-amber-500 shrink-0 mt-0.5">•</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// SETUP TABLE — per §9
// ─────────────────────────────────────────────────────────────────────────────
function SetupTable() {
  const { state } = useDeepInsight();
  const { setup, signalState } = state;

  if (!setup) {
    return <div className="text-sm text-muted-foreground py-2">— Unavailable</div>;
  }

  const isNoSetup = !setup.setup_type || setup.setup_type === 'NO_SETUP';
  type SRow = [string, string | number, 'text' | 'badge' | 'stop'];
  const rows: SRow[] = [
    ['Setup Type', isNoSetup ? 'No active setup' : setup.setup_type, 'badge'],
    ['Entry Zone', !isNoSetup && setup.entry_zone && setup.entry_zone !== '0' && setup.entry_zone !== '—' ? setup.entry_zone : '—', 'text'],
    ['Stop Loss', !isNoSetup && setup.stop_loss > 0 ? fmt(setup.stop_loss) : '—', 'stop'],
    ['Target', !isNoSetup && setup.target && setup.target !== '0' && setup.target !== '—' ? setup.target : '—', 'text'],
    ['Risk:Reward', !isNoSetup && setup.risk_reward > 0 ? `1:${fmt(setup.risk_reward)}` : '—', 'text'],
    ['Signal Age', signalState ? `${signalState.age}s` : '—', 'text'],
    ['Remaining TTL', signalState ? `${signalState.ttl_remaining}s` : '—', 'text'],
  ];

  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([label, value, style]) => (
          <tr key={label} className="border-b border-border/50">
            <td className="py-1.5 pr-4 text-muted-foreground">{label}</td>
            <td className="py-1.5 font-medium text-right">
              {style === 'badge' ? (
                <Badge variant={value === 'No active setup' ? 'secondary' : 'default'}>{value}</Badge>
              ) : style === 'stop' ? (
                <span className="text-red-500 font-medium">{value}</span>
              ) : (
                <span>{value}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// VALIDATION & SYSTEM — per §18
// ─────────────────────────────────────────────────────────────────────────────
function ValidationSection() {
  const { state } = useDeepInsight();
  const { validation, provider, dataQuality, payload } = state;

  return (
    <div className="space-y-3">
      {validation && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground font-semibold">VALIDATION:</span>
          <Badge variant={validation.status === 'ACCEPT' || validation.status === 'PASS' ? 'success' : 'destructive'}>{validation.status}</Badge>
          {validation.rejection_reason && (
            <span className="text-xs text-muted-foreground">{validation.rejection_reason}</span>
          )}
        </div>
      )}
      {provider && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <span className="text-muted-foreground">Provider</span>
          <span className="font-medium">{provider.name}</span>
          <span className="text-muted-foreground">Model</span>
          <span className="font-medium">{provider.model}</span>
          <span className="text-muted-foreground">Latency</span>
          <span className="font-medium">{provider.latency_ms}ms</span>
        </div>
      )}
      {dataQuality && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <span className="text-muted-foreground">Data Quality</span>
          <span className="font-medium">{fmt(dataQuality.completeness, 0)}%</span>
          <span className="text-muted-foreground">Status</span>
          <span className="font-medium">{dataQuality.status}</span>
        </div>
      )}
      {payload?.timestamp && (
        <div className="text-xs text-muted-foreground">
          Updated: {(() => {
            try {
              return new Date(payload.timestamp).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' });
            } catch {
              return String(payload.timestamp);
            }
          })()}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN EXPORT
// ─────────────────────────────────────────────────────────────────────────────
export function DeepInsightPanel() {
  const { state } = useDeepInsight();

  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'error') return <ErrorState msg={state.error || 'Failed to load deep insight'} />;
  if (state.status === 'unavailable') return <UnavailableState msg={state.error} />;
  if (state.status === 'idle') return <UnavailableState msg="Select a symbol to analyze" />;

  return (
    <div className="space-y-4">
      {/* Main Decision Table */}
      <Card>
        <CardContent className="pt-4">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">
            AI Deep Insight
          </div>
          <MainDecisionTable />
        </CardContent>
      </Card>

      {/* 2-column grid for secondary tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Multi-Timeframe</div>
            <MultiTimeframeTable />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Historical Insight</div>
            <HistoricalTable />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Options Evidence</div>
            <OptionsTable />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">Trade Setup</div>
            <SetupTable />
          </CardContent>
        </Card>
      </div>

      {/* AI View / Evidence / Risk */}
      <Card>
        <CardContent className="pt-4">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">AI View</div>
          <AiViewSection />
        </CardContent>
      </Card>

      {/* Validation & System */}
      <Card>
        <CardContent className="pt-4">
          <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-3">System</div>
          <ValidationSection />
        </CardContent>
      </Card>
    </div>
  );
}
