'use client';

import React from 'react';
import { useDeepInsight } from '@/context/DeepInsightContext';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Activity,
  Layers,
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  Sliders,
  BarChart3,
  Clock,
  CheckCircle2,
} from 'lucide-react';
import type { DeepInsightDirection, DeepInsightRegime, DeepInsightSignalState } from '@/lib/deep-insight-types';

function fmt(n: number | undefined | null, digits = 2): string {
  if (n === undefined || n === null || isNaN(n)) return '—';
  return n.toFixed(digits);
}

function directionVariant(d: DeepInsightDirection | string | undefined | null): 'default' | 'success' | 'destructive' | 'secondary' {
  switch (d) {
    case 'BULLISH': return 'success';
    case 'BEARISH': return 'destructive';
    case 'NEUTRAL': return 'secondary';
    default: return 'default';
  }
}

function regimeVariant(r: DeepInsightRegime | string | undefined | null): 'default' | 'success' | 'destructive' | 'secondary' {
  switch (r) {
    case 'TREND': return 'success';
    case 'RANGE': return 'secondary';
    case 'BREAKOUT': return 'success';
    case 'REVERSAL': return 'destructive';
    default: return 'default';
  }
}

function formatTime(ts: string | number | undefined | null): string {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour12: true,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return String(ts);
  }
}

function LoadingState() {
  return (
    <div className="h-full flex items-center justify-center py-16">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <span className="text-sm font-medium text-muted-foreground">Synthesizing real-time market intelligence...</span>
      </div>
    </div>
  );
}

function ErrorState({ msg }: { msg: string }) {
  return (
    <div className="h-full flex items-center justify-center py-16">
      <div className="text-center max-w-md p-6 bg-card border border-border rounded-xl">
        <div className="text-red-500 font-bold mb-1">Intelligence Error</div>
        <div className="text-muted-foreground text-xs leading-relaxed">{msg || 'Failed to load deep insight'}</div>
      </div>
    </div>
  );
}

function UnavailableState({ msg }: { msg?: string | null }) {
  return (
    <div className="h-full flex items-center justify-center py-16">
      <div className="text-center max-w-md p-6 bg-card border border-border rounded-xl">
        <div className="text-muted-foreground font-semibold mb-1">AI Engine Unavailable</div>
        <div className="text-muted-foreground text-xs">{msg || 'Select an instrument to evaluate live conditions'}</div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 1: MARKET STRUCTURE & REGIME
// ─────────────────────────────────────────────────────────────────────────────
function MarketRegimeCard() {
  const { state } = useDeepInsight();
  const { market } = state;
  if (!market) return null;

  const spot = market.levels?.current_price;
  const vwap = market.levels?.vwap;
  const support = market.levels?.support;
  const resistance = market.levels?.resistance;
  const vwapRel = market.levels?.vwap_relation;
  const momentum = market.momentum;
  const volume = market.volume;

  return (
    <Card className="flex-1 min-h-0 flex flex-col border-border/70 shadow-xs bg-card/60">
      <CardContent className="p-3 flex flex-col h-full min-h-0 justify-between gap-2">
        {/* Header: Title + Volatility Tag */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Market Structure</span>
          </div>
          <Badge variant="outline" className="text-[10px] uppercase font-semibold px-1.5 py-0 h-4.5">
            Vol: {market.volatility}
          </Badge>
        </div>

        {/* Regime Banner */}
        <div className="bg-muted/40 border border-border/40 rounded-lg p-2">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <Badge variant={regimeVariant(market.regime)} className="font-bold text-xs h-5 px-2">
                {market.regime}
              </Badge>
              <Badge variant={directionVariant(market.direction)} className="text-[10px] h-4.5 px-1.5 font-semibold">
                {market.direction}
              </Badge>
            </div>
            <span className="text-xs font-mono font-bold text-foreground">
              {market.regime_strength}/100
            </span>
          </div>
          <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={`h-full transition-all rounded-full ${
                market.direction === 'BULLISH' ? 'bg-emerald-500' : market.direction === 'BEARISH' ? 'bg-red-500' : 'bg-primary'
              }`}
              style={{ width: `${Math.min(100, Math.max(0, market.regime_strength))}%` }}
            />
          </div>
        </div>

        {/* Indicators 3-col Mini Grid */}
        <div className="grid grid-cols-3 gap-2 text-xs">
          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">VWAP</span>
            <span className={`font-bold font-mono text-xs ${
              vwapRel === 'Above' ? 'text-emerald-500' : vwapRel === 'Below' ? 'text-red-500' : 'text-foreground'
            }`}>
              {vwap ? fmt(vwap, 1) : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">{vwapRel || 'At'} VWAP</span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Momentum</span>
            <span className="font-bold font-mono text-xs text-foreground">
              {momentum?.value !== undefined ? fmt(momentum.value, 1) : '—'}
            </span>
            <span className={`text-[10px] font-medium ${
              momentum?.status === 'Positive' ? 'text-emerald-500' : momentum?.status === 'Negative' ? 'text-red-500' : 'text-muted-foreground'
            }`}>
              {momentum?.status || 'Neutral'}
            </span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Volume</span>
            <span className="font-bold font-mono text-xs text-foreground">
              {volume?.relative_value !== undefined ? `${fmt(volume.relative_value, 2)}×` : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">{volume?.status || 'Normal'}</span>
          </div>
        </div>

        {/* Key Levels: Support & Resistance Bar */}
        <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex items-center justify-between text-xs">
          <div className="flex flex-col">
            <span className="text-[10px] text-emerald-500 font-semibold uppercase">Support</span>
            <span className="font-mono font-bold text-foreground">{support ? fmt(support, 1) : '—'}</span>
          </div>
          <div className="h-6 w-px bg-border/60" />
          <div className="flex flex-col items-center">
            <span className="text-[10px] text-muted-foreground font-medium uppercase">Current</span>
            <span className="font-mono font-bold text-primary">{spot ? fmt(spot, 1) : '—'}</span>
          </div>
          <div className="h-6 w-px bg-border/60" />
          <div className="flex flex-col items-end">
            <span className="text-[10px] text-red-500 font-semibold uppercase">Resistance</span>
            <span className="font-mono font-bold text-foreground">{resistance ? fmt(resistance, 1) : '—'}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 2: MULTI-TIMEFRAME ALIGNMENT
// ─────────────────────────────────────────────────────────────────────────────
function MultiTimeframeCard() {
  const { state } = useDeepInsight();
  const { multiTimeframe } = state;
  if (!multiTimeframe || multiTimeframe.length === 0) return null;

  const bullCount = multiTimeframe.filter(t => t.direction === 'BULLISH').length;
  const bearCount = multiTimeframe.filter(t => t.direction === 'BEARISH').length;
  const total = multiTimeframe.length;
  const alignment = bullCount === total ? 'STRONG BULLISH' : bearCount === total ? 'STRONG BEARISH' : bullCount === 0 && bearCount === 0 ? 'MIXED' : bullCount > bearCount ? 'BULLISH BIAS' : 'BEARISH BIAS';

  return (
    <Card className="flex-1 min-h-0 flex flex-col border-border/70 shadow-xs bg-card/60">
      <CardContent className="p-3 flex flex-col h-full min-h-0 justify-between gap-2">
        {/* Header with Alignment Badge */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Multi-Timeframe</span>
          </div>
          <Badge
            variant={bullCount > bearCount ? 'success' : bearCount > bullCount ? 'destructive' : 'secondary'}
            className="text-[10px] font-bold uppercase px-2 py-0 h-4.5"
          >
            {alignment}
          </Badge>
        </div>

        {/* 4 Timeframe Rows */}
        <div className="space-y-1.5 flex-1 min-h-0 flex flex-col justify-around">
          {multiTimeframe.map((tf) => (
            <div key={tf.timeframe} className="flex items-center justify-between text-xs bg-muted/20 hover:bg-muted/40 border border-border/30 rounded-lg px-2.5 py-1.5 transition-colors">
              <div className="flex items-center gap-2 min-w-[75px]">
                <span className="font-mono font-bold text-foreground text-xs">{tf.timeframe}</span>
                <Badge variant={directionVariant(tf.direction)} className="text-[10px] px-1.5 py-0 h-4 font-semibold">
                  {tf.direction}
                </Badge>
              </div>

              {/* Mini Strength Bar */}
              <div className="flex items-center gap-2 flex-1 max-w-[100px] mx-2">
                <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      tf.direction === 'BULLISH' ? 'bg-emerald-500' : tf.direction === 'BEARISH' ? 'bg-red-500' : 'bg-muted-foreground'
                    }`}
                    style={{ width: `${tf.strength}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-muted-foreground w-6 text-right">{tf.strength}</span>
              </div>

              <span className="text-[11px] text-muted-foreground truncate max-w-[85px] text-right font-medium">
                {tf.structure}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 3: HERO ACTIONABLE TRADE SETUP
// ─────────────────────────────────────────────────────────────────────────────
function HeroTradeSetupCard() {
  const { state } = useDeepInsight();
  const { setup, aiView, signalState } = state;

  const bias = aiView?.bias || 'NO_TRADE';
  const confidence = aiView?.confidence ?? 0;
  const calibrated = aiView?.calibrated_confidence;
  const isNoSetup = !setup?.setup_type || setup.setup_type === 'NO_SETUP' || setup.entry_zone === '—' || setup.entry_zone === '0';
  const setupType = isNoSetup ? 'No Active Setup' : setup?.setup_type;
  const ttl = signalState?.ttl_remaining ?? 0;

  return (
    <Card className="border-border/80 shadow-xs bg-card/80 shrink-0">
      <CardContent className="p-3 space-y-2.5">
        {/* Top row: Bias Banner + Setup Type + TTL */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <Badge
              variant={bias === 'LONG' ? 'success' : bias === 'SHORT' ? 'destructive' : 'default'}
              className="text-sm font-extrabold px-2.5 py-0.5 tracking-wide shadow-xs"
            >
              {bias}
            </Badge>
            <Badge variant={isNoSetup ? 'secondary' : 'outline'} className="text-xs font-semibold px-2 py-0.5">
              {setupType}
            </Badge>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {confidence > 0 && (
              <span className="font-mono font-bold text-foreground">
                Confidence {confidence}%
                {calibrated && calibrated !== confidence ? ` (Calibrated ${calibrated}%)` : ''}
              </span>
            )}
            {signalState && (
              <Badge variant="outline" className="text-[10px] font-mono text-muted-foreground px-1.5 py-0 h-5">
                {signalState.state} · {ttl}s left
              </Badge>
            )}
          </div>
        </div>

        {/* 4 Execution Metrics Grid */}
        <div className="grid grid-cols-4 gap-2 text-center">
          <div className="bg-muted/40 border border-border/40 rounded-xl p-2 flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-0.5">Entry Zone</span>
            <span className="text-base font-extrabold font-mono text-foreground">
              {!isNoSetup && setup?.entry_zone && setup.entry_zone !== '0' ? setup.entry_zone : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">Trigger</span>
          </div>

          <div className="bg-rose-500/5 border border-rose-500/20 rounded-xl p-2 flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-rose-500 mb-0.5">Stop Loss</span>
            <span className="text-base font-extrabold font-mono text-rose-500">
              {!isNoSetup && setup && setup.stop_loss > 0 ? fmt(setup.stop_loss, 1) : '—'}
            </span>
            <span className="text-[10px] text-rose-500/70">Invalidation</span>
          </div>

          <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-2 flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-500 mb-0.5">Target</span>
            <span className="text-base font-extrabold font-mono text-emerald-500">
              {!isNoSetup && setup?.target && setup.target !== '0' ? setup.target : '—'}
            </span>
            <span className="text-[10px] text-emerald-500/70">Proposed</span>
          </div>

          <div className="bg-muted/40 border border-border/40 rounded-xl p-2 flex flex-col justify-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-0.5">R : R</span>
            <span className="text-base font-extrabold font-mono text-foreground">
              {!isNoSetup && setup && setup.risk_reward > 0 ? `1 : ${fmt(setup.risk_reward, 1)}` : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">Ratio</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 4: AI THESIS, RISKS & TELEMETRY TABS
// ─────────────────────────────────────────────────────────────────────────────
function AiThesisTabsCard() {
  const { state } = useDeepInsight();
  const { aiView, technicalEvidence, risks, invalidation, validation, provider, dataQuality, payload } = state;

  return (
    <Card className="flex-1 min-h-0 flex flex-col border-border/70 shadow-xs bg-card/60">
      <CardContent className="p-3 flex flex-col h-full min-h-0">
        <Tabs defaultValue="thesis" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid grid-cols-3 h-8 p-0.5 bg-muted/60 mb-2 shrink-0">
            <TabsTrigger value="thesis" className="text-xs font-semibold py-1 gap-1">
              <Sparkles className="w-3 h-3 text-primary" />
              <span>Synthesis</span>
            </TabsTrigger>
            <TabsTrigger value="risks" className="text-xs font-semibold py-1 gap-1">
              <ShieldAlert className="w-3 h-3 text-amber-500" />
              <span>Risks</span>
            </TabsTrigger>
            <TabsTrigger value="system" className="text-xs font-semibold py-1 gap-1">
              <Sliders className="w-3 h-3 text-blue-500" />
              <span>System</span>
            </TabsTrigger>
          </TabsList>

          {/* Tab 1: Synthesis & Triggers */}
          <TabsContent value="thesis" className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            <div className="bg-muted/40 border border-border/40 rounded-lg p-2 text-xs">
              <div className="text-[10px] font-bold uppercase tracking-wider text-primary mb-1">AI Executive Summary</div>
              <p className="text-foreground leading-relaxed font-medium">
                {aiView?.summary || 'No trade signal active. Market conditions currently being evaluated.'}
              </p>
            </div>

            {technicalEvidence && technicalEvidence.positive && technicalEvidence.positive.length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Catalysts & Triggers</div>
                <div className="space-y-1">
                  {technicalEvidence.positive.map((item, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-xs text-foreground bg-muted/20 border border-border/20 rounded-md p-1.5">
                      <span className="text-emerald-500 font-bold shrink-0 mt-0.5">✓</span>
                      <span className="leading-snug">{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>

          {/* Tab 2: Risks & Invalidation */}
          <TabsContent value="risks" className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            {((risks?.main_risks && risks.main_risks.length > 0) || (invalidation && invalidation.length > 0)) ? (
              <div className="space-y-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-amber-500">Risk Factors & Invalidation</div>
                <div className="space-y-1">
                  {[...(risks?.main_risks || []), ...(invalidation || [])].slice(0, 5).map((item, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-xs text-foreground bg-amber-500/5 border border-amber-500/20 rounded-md p-1.5">
                      <span className="text-amber-500 font-bold shrink-0 mt-0.5">⚠</span>
                      <span className="leading-snug">{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-xs text-muted-foreground text-center py-6">No active risk flags recorded.</div>
            )}
          </TabsContent>

          {/* Tab 3: Model & System Telemetry */}
          <TabsContent value="system" className="flex-1 min-h-0 overflow-y-auto pr-1 space-y-2">
            {validation && (
              <div className="bg-muted/40 border border-border/40 rounded-lg p-2 space-y-1 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Validation:</span>
                  <Badge variant={validation.status === 'ACCEPT' || validation.status === 'PASS' ? 'success' : 'destructive'} className="text-[10px] h-4.5 px-1.5">
                    {validation.status}
                  </Badge>
                </div>
                {validation.rejection_reason && (
                  <p className="text-xs text-red-400 font-mono leading-snug bg-red-950/20 border border-red-900/30 p-2 rounded">
                    {validation.rejection_reason}
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="bg-muted/30 border border-border/30 rounded-lg p-2">
                <span className="text-[10px] text-muted-foreground block">AI Provider</span>
                <span className="font-semibold text-foreground">{provider?.name || 'AI Engine'}</span>
              </div>
              <div className="bg-muted/30 border border-border/30 rounded-lg p-2">
                <span className="text-[10px] text-muted-foreground block">Model</span>
                <span className="font-semibold text-foreground truncate block">{provider?.model || 'Configured'}</span>
              </div>
              <div className="bg-muted/30 border border-border/30 rounded-lg p-2">
                <span className="text-[10px] text-muted-foreground block">Latency</span>
                <span className="font-semibold font-mono text-foreground">{provider?.latency_ms ?? 0}ms</span>
              </div>
              <div className="bg-muted/30 border border-border/30 rounded-lg p-2">
                <span className="text-[10px] text-muted-foreground block">Data Completeness</span>
                <span className="font-semibold font-mono text-foreground">{dataQuality ? `${fmt(dataQuality.completeness, 0)}%` : '100%'}</span>
              </div>
            </div>

            {payload?.timestamp && (
              <div className="text-[10px] text-muted-foreground text-right pt-0.5">
                Synced: {formatTime(payload.timestamp)}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 5: OPTIONS FLOW & SENTIMENT
// ─────────────────────────────────────────────────────────────────────────────
function OptionsFlowCard() {
  const { state } = useDeepInsight();
  const { optionsEvidence } = state;
  if (!optionsEvidence) return null;

  const o = optionsEvidence;
  const pcrSentiment = o.pcr >= 1.2 ? 'BULLISH' : o.pcr <= 0.8 ? 'BEARISH' : 'NEUTRAL';

  return (
    <Card className="flex-1 min-h-0 flex flex-col border-border/70 shadow-xs bg-card/60">
      <CardContent className="p-3 flex flex-col h-full min-h-0 justify-between gap-2">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Options Flow</span>
          </div>
          <Badge variant={directionVariant(o.bias)} className="text-[10px] font-bold px-2 py-0 h-4.5 uppercase">
            {o.bias}
          </Badge>
        </div>

        {/* PCR & Strikes 2-Col Grid */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">PCR (OI)</span>
            <span className="font-bold font-mono text-sm text-foreground">{fmt(o.pcr, 2)}</span>
            <span className={`text-[10px] font-semibold ${
              pcrSentiment === 'BULLISH' ? 'text-emerald-500' : pcrSentiment === 'BEARISH' ? 'text-red-500' : 'text-muted-foreground'
            }`}>
              {pcrSentiment}
            </span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">OI Trend</span>
            <span className="font-bold font-mono text-xs text-foreground">{o.oi_trend}</span>
            <span className="text-[10px] text-muted-foreground">{o.iv} IV</span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-emerald-500 font-semibold uppercase">Put Support</span>
            <span className="font-bold font-mono text-xs text-foreground">
              {o.put_support > 0 ? fmt(o.put_support, 0) : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">Max Put OI</span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-red-500 font-semibold uppercase">Call Resist.</span>
            <span className="font-bold font-mono text-xs text-foreground">
              {o.call_resistance > 0 ? fmt(o.call_resistance, 0) : '—'}
            </span>
            <span className="text-[10px] text-muted-foreground">Max Call OI</span>
          </div>
        </div>

        {/* Flow Interpretation */}
        {o.interpretation && (
          <div className="bg-muted/20 border border-border/30 rounded-lg px-2.5 py-1.5 text-xs text-muted-foreground italic flex items-center gap-1.5">
            <span className="text-primary font-bold">ℹ</span>
            <span className="truncate">{o.interpretation}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CARD 6: STATISTICAL EDGE & HISTORICAL CONTEXT
// ─────────────────────────────────────────────────────────────────────────────
function HistoricalEdgeCard() {
  const { state } = useDeepInsight();
  const { historicalEvidence } = state;
  if (!historicalEvidence) return null;

  const h = historicalEvidence;
  const qualityVariant = h.sample_quality === 'GOOD' ? 'success' : h.sample_quality === 'FAIR' ? 'secondary' : 'destructive';

  return (
    <Card className="flex-1 min-h-0 flex flex-col border-border/70 shadow-xs bg-card/60">
      <CardContent className="p-3 flex flex-col h-full min-h-0 justify-between gap-2">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-primary" />
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Historical Edge</span>
          </div>
          <Badge variant={qualityVariant} className="text-[10px] font-bold px-1.5 py-0 h-4.5 uppercase">
            {h.sample_quality} Quality
          </Badge>
        </div>

        {/* 4-Stat Grid */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Continuation</span>
            <span className="font-bold font-mono text-sm text-foreground">
              {h.continuation > 0 ? `${fmt(h.continuation, 0)}%` : '—'}
            </span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Reversal</span>
            <span className="font-bold font-mono text-sm text-foreground">
              {h.reversal > 0 ? `${fmt(h.reversal, 0)}%` : '—'}
            </span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Failure</span>
            <span className="font-bold font-mono text-sm text-foreground">
              {h.failure > 0 ? `${fmt(h.failure, 0)}%` : '—'}
            </span>
          </div>

          <div className="bg-muted/30 border border-border/30 rounded-lg p-2 flex flex-col">
            <span className="text-[10px] text-muted-foreground font-semibold uppercase">Median Move</span>
            <span className="font-bold font-mono text-sm text-foreground">
              {h.median_move !== 0 ? `${h.median_move > 0 ? '+' : ''}${fmt(h.median_move, 0)} pts` : '—'}
            </span>
          </div>
        </div>

        {/* Footer Disclaimer */}
        <div className="text-[10px] text-muted-foreground italic text-center">
          Historical pattern edge · Not predictive
        </div>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN BENTO EXPORT
// ─────────────────────────────────────────────────────────────────────────────
export function DeepInsightPanel() {
  const { state } = useDeepInsight();

  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'error') return <ErrorState msg={state.error || 'Failed to load deep insight'} />;
  if (state.status === 'unavailable') return <UnavailableState msg={state.error} />;
  if (state.status === 'idle') return <UnavailableState msg="Select a symbol to analyze" />;

  return (
    <div className="h-full min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-2.5">
      {/* Left Column (33.3%): Market Structure & Multi-TF */}
      <div className="lg:col-span-4 flex flex-col gap-2.5 h-full min-h-0">
        <MarketRegimeCard />
        <MultiTimeframeCard />
      </div>

      {/* Center Column (41.7%): Hero Setup & AI Thesis Tabs */}
      <div className="lg:col-span-5 flex flex-col gap-2.5 h-full min-h-0">
        <HeroTradeSetupCard />
        <AiThesisTabsCard />
      </div>

      {/* Right Column (25%): Options Flow & Statistical Edge */}
      <div className="lg:col-span-3 flex flex-col gap-2.5 h-full min-h-0">
        <OptionsFlowCard />
        <HistoricalEdgeCard />
      </div>
    </div>
  );
}

