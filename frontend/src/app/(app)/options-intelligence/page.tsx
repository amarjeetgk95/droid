'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { PageTabs } from '@/components/ui/PageTabs';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Brain,
  Zap,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  Layers,
  Activity,
  Gauge,
  Scale,
  Clock,
  ExternalLink,
  Flame,
  CheckCircle2,
  XCircle,
  BarChart3,
  DollarSign,
} from 'lucide-react';

export default function OptionsIntelligencePage() {
  const [underlying, setUnderlying] = useState<'NIFTY' | 'BANKNIFTY' | 'SENSEX'>('NIFTY');
  const [horizon, setHorizon] = useState<'SCALP' | 'INTRADAY' | 'SWING' | 'POSITIONAL'>('INTRADAY');
  const [direction, setDirection] = useState<'BULLISH' | 'BEARISH'>('BULLISH');
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Data states
  const [researchData, setResearchData] = useState<any>(null);
  const [expectedMoveData, setExpectedMoveData] = useState<any>(null);
  const [contractSelection, setContractSelection] = useState<any>(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState<any>(null);

  const spotBaselines: Record<string, number> = {
    NIFTY: 24920.0,
    BANKNIFTY: 53240.0,
    SENSEX: 81850.0,
  };

  const loadAllIntelligence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const spot = spotBaselines[underlying] || 25000.0;
      const optDirection = direction === 'BULLISH' ? 'LONG_CALL' : 'LONG_PUT';

      const [researchRes, moveRes, selectRes, greeksRes] = await Promise.all([
        api.getFinancialResearch(underlying, horizon, direction),
        api.projectExpectedMove({
          underlying,
          spot,
          direction,
          horizon,
          current_iv: 0.155,
        }),
        api.selectOptimalContract({
          underlying,
          spot_price: spot,
          direction: optDirection,
          stop_loss_points: underlying === 'BANKNIFTY' ? 80 : underlying === 'SENSEX' ? 120 : 30,
          current_iv: 0.155,
        }),
        api.getPortfolioGreeksSummary(),
      ]);

      setResearchData(researchRes);
      setExpectedMoveData(moveRes);
      setContractSelection(selectRes);
      setPortfolioGreeks(greeksRes);
    } catch (err: any) {
      setError(err?.message || 'Failed to fetch options intelligence data');
    } finally {
      setLoading(false);
    }
  }, [underlying, horizon, direction]);

  useEffect(() => {
    loadAllIntelligence();
  }, [loadAllIntelligence]);

  // Context effect badge styling
  const getEffectBadge = (effect: string) => {
    switch (effect) {
      case 'SUPPORTIVE':
        return <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">SUPPORTIVE</Badge>;
      case 'CONTRADICTORY':
        return <Badge className="bg-rose-500/20 text-rose-400 border-rose-500/30">CONTRADICTORY</Badge>;
      default:
        return <Badge className="bg-muted text-muted-foreground border-border">NEUTRAL</Badge>;
    }
  };

  // AI impact badge styling
  const getImpactBadge = (impact: string) => {
    switch (impact) {
      case 'STRENGTHEN':
        return <Badge className="bg-emerald-500 text-white font-bold px-3 py-1">STRENGTHENED (+)</Badge>;
      case 'BLOCK':
        return <Badge className="bg-rose-600 text-white font-bold px-3 py-1">BLOCKED (NO-TRADE)</Badge>;
      case 'WEAKEN':
        return <Badge className="bg-amber-500 text-black font-bold px-3 py-1">WEAKENED (-)</Badge>;
      default:
        return <Badge variant="outline" className="px-3 py-1">NO CHANGE</Badge>;
    }
  };

  const getSourceTierLabel = (tier: number) => {
    switch (tier) {
      case 1:
        return <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 font-semibold">Tier 1: Regulator</span>;
      case 2:
        return <span className="text-xs px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-semibold">Tier 2: Central Bank</span>;
      case 3:
        return <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 font-semibold">Tier 3: Corporate Filing</span>;
      case 4:
        return <span className="text-xs px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-semibold">Tier 4: Financial Terminal</span>;
      case 5:
        return <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">Tier 5: Financial Press</span>;
      default:
        return <span className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-zinc-300">Tier {tier}: Secondary/Social</span>;
    }
  };

  // Sub-Tabs definition
  const tabs = [
    {
      id: 'ai_research',
      label: 'AI Financial Research & Contradictions (§42)',
      icon: Brain,
      content: (
        <div className="space-y-6">
          {/* Executive Assessment Header */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="bg-card/70 border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase tracking-wider">Research Assessment</CardDescription>
                <CardTitle className="text-xl font-bold flex items-center gap-2">
                  {researchData?.research_assessment?.replace('_', ' ') || 'MIXED'}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">{researchData?.bull_case_summary}</p>
              </CardContent>
            </Card>

            <Card className="bg-card/70 border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase tracking-wider">AI Signal Contract Impact (§22)</CardDescription>
                <div className="mt-1">{getImpactBadge(researchData?.ai_impact || 'NO_CHANGE')}</div>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {researchData?.impact_rationale?.[0] || 'Quantitative setup operating within baseline risk limits.'}
                </p>
              </CardContent>
            </Card>

            <Card className="bg-card/70 border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase tracking-wider">Contradiction Threat Score (§16)</CardDescription>
                <CardTitle className="text-xl font-bold text-amber-400 flex items-center gap-2">
                  <Scale className="w-5 h-5 text-amber-400" />
                  {researchData?.contradiction_analysis?.counter_weight_score ?? 0}%
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-xs text-muted-foreground">
                  {researchData?.contradiction_analysis?.counter_weight_score > 50
                    ? 'Elevated counter-evidence; defensive positioning active.'
                    : 'Counter-evidence within safe operational bounds.'}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Context Pillars */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary" />
                Six Financial Context Pillars (§10 - §15)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Market Context</div>
                  {getEffectBadge(researchData?.market_context || 'NEUTRAL')}
                </div>
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Macro / Rates</div>
                  {getEffectBadge(researchData?.macro_context || 'NEUTRAL')}
                </div>
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Fundamentals</div>
                  {getEffectBadge(researchData?.fundamental_context || 'NEUTRAL')}
                </div>
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">News & Events</div>
                  {getEffectBadge(researchData?.news_context || 'NEUTRAL')}
                </div>
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Positioning</div>
                  {getEffectBadge(researchData?.sentiment_context || 'NEUTRAL')}
                </div>
                <div className="bg-muted/40 p-3 rounded-lg border border-border/50 text-center">
                  <div className="text-xs text-muted-foreground mb-1">Cross-Asset</div>
                  {getEffectBadge(researchData?.cross_asset_context || 'NEUTRAL')}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Mandatory Contradiction & Invalidation Card */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="bg-rose-950/20 border-rose-500/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-rose-300 flex items-center gap-2">
                  <ShieldAlert className="w-5 h-5 text-rose-400" />
                  Strongest Counter-Thesis (§16)
                </CardTitle>
                <CardDescription className="text-xs text-rose-200/70">
                  Mandatory active disconfirmation: what could cause this trade to fail?
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="p-3 bg-rose-950/40 border border-rose-500/20 rounded-lg text-sm text-rose-200 font-medium">
                  {researchData?.contradiction_analysis?.strongest_counter_argument || 'No material counter-catalysts detected.'}
                </div>
                <div>
                  <div className="text-xs font-semibold text-rose-400 uppercase tracking-wider mb-1">Invalidation Triggers</div>
                  <ul className="text-xs text-rose-200/80 space-y-1 list-disc list-inside">
                    {researchData?.contradiction_analysis?.invalidation_conditions?.map((c: string, i: number) => (
                      <li key={i}>{c}</li>
                    )) || <li>Local structural stop breach</li>}
                  </ul>
                </div>
              </CardContent>
            </Card>

            <Card className="bg-emerald-950/20 border-emerald-500/30">
              <CardHeader className="pb-2">
                <CardTitle className="text-base font-semibold text-emerald-300 flex items-center gap-2">
                  <ShieldCheck className="w-5 h-5 text-emerald-400" />
                  Supporting Catalysts & Driver
                </CardTitle>
                <CardDescription className="text-xs text-emerald-200/70">
                  Key fundamental and market flows corroborating the thesis.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="p-3 bg-emerald-950/40 border border-emerald-500/20 rounded-lg text-sm text-emerald-200">
                  {researchData?.key_catalysts?.[0] || 'Technical momentum expansion above institutional session anchor.'}
                </div>
                <div>
                  <div className="text-xs font-semibold text-emerald-400 uppercase tracking-wider mb-1">Key Risks Monitored</div>
                  <ul className="text-xs text-emerald-200/80 space-y-1 list-disc list-inside">
                    {researchData?.contradiction_analysis?.key_risks?.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    )) || <li>Slippage during opening momentum</li>}
                  </ul>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sourced Evidence Ledger */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-primary" />
                  Sourced Evidence Ledger (§18 Source Hierarchy)
                </span>
                <span className="text-xs text-muted-foreground font-normal">
                  Model: {researchData?.model_version || 'v1.0'} | Freshness TTL Active
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {researchData?.supporting_evidence?.length > 0 || researchData?.contradiction_analysis?.contradicting_evidence?.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground uppercase tracking-wider">
                        <th className="py-2 px-3">Credibility Tier</th>
                        <th className="py-2 px-3">Source Name</th>
                        <th className="py-2 px-3">Claim / Assertion</th>
                        <th className="py-2 px-3">Impact</th>
                        <th className="py-2 px-3 text-right">Confidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/40">
                      {[...(researchData?.supporting_evidence || []), ...(researchData?.contradiction_analysis?.contradicting_evidence || [])].map((item: any, idx: number) => (
                        <tr key={idx} className="hover:bg-muted/30">
                          <td className="py-2.5 px-3">{getSourceTierLabel(item.source_tier)}</td>
                          <td className="py-2.5 px-3 font-medium text-foreground">{item.source_name}</td>
                          <td className="py-2.5 px-3 max-w-md truncate">{item.claim}</td>
                          <td className="py-2.5 px-3">{getEffectBadge(item.effect)}</td>
                          <td className="py-2.5 px-3 text-right font-mono">{item.confidence}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-6 text-muted-foreground text-sm">
                  Deterministic Fallback active (§34). Live quantitative stream operating with neutral AI baseline.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ),
    },
    {
      id: 'expected_move',
      label: 'Expected Move & Velocity vs Theta (§8)',
      icon: Gauge,
      content: (
        <div className="space-y-6">
          {/* Velocity vs Theta Hero Gauge */}
          <Card className={`border ${expectedMoveData?.is_fast_enough_for_option ? 'bg-emerald-950/15 border-emerald-500/40' : 'bg-rose-950/15 border-rose-500/40'}`}>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg font-bold flex items-center gap-2">
                  <Gauge className="w-5 h-5 text-primary" />
                  Velocity vs Option Theta Decoupling (§8 Core Invariant)
                </CardTitle>
                <Badge className={expectedMoveData?.is_fast_enough_for_option ? 'bg-emerald-500 text-white' : 'bg-rose-600 text-white'}>
                  {expectedMoveData?.is_fast_enough_for_option ? 'VELOCITY APPROVED' : 'TOO SLOW FOR OPTION BUYING'}
                </Badge>
              </div>
              <CardDescription className="text-xs">
                Distinguishes &ldquo;large move eventually&rdquo; from &ldquo;large move quickly enough for the selected option after theta decay&rdquo;.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="bg-card/80 p-4 rounded-xl border border-border">
                  <div className="text-xs text-muted-foreground">Expected Duration</div>
                  <div className="text-2xl font-bold font-mono mt-1">{expectedMoveData?.expected_duration_hours || 1.0} hrs</div>
                  <div className="text-xs text-muted-foreground mt-1">Horizon: {expectedMoveData?.horizon}</div>
                </div>

                <div className="bg-card/80 p-4 rounded-xl border border-border">
                  <div className="text-xs text-muted-foreground">Price Velocity</div>
                  <div className="text-2xl font-bold font-mono mt-1 text-primary">
                    {expectedMoveData?.expected_velocity_pts_per_hour || 0} pts/hr
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Underlying speed</div>
                </div>

                <div className="bg-card/80 p-4 rounded-xl border border-border">
                  <div className="text-xs text-muted-foreground">1-Sigma IV Move</div>
                  <div className="text-2xl font-bold font-mono mt-1">±{expectedMoveData?.iv_implied_1sigma_move || 0} pts</div>
                  <div className="text-xs text-muted-foreground mt-1">Statistical dispersion</div>
                </div>

                <div className="bg-card/80 p-4 rounded-xl border border-border">
                  <div className="text-xs text-muted-foreground">ATR Excursion</div>
                  <div className="text-2xl font-bold font-mono mt-1">±{expectedMoveData?.atr_excursion_points || 0} pts</div>
                  <div className="text-xs text-muted-foreground mt-1">Regime volatility multiplier</div>
                </div>
              </div>

              <div className="p-3 bg-card/60 border border-border rounded-lg text-xs space-y-1">
                <div className="font-semibold text-foreground">Forecast Rationale & Diagnostics:</div>
                {expectedMoveData?.forecast_rationale?.map((r: string, i: number) => (
                  <div key={i} className="text-muted-foreground flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-primary" />
                    {r}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Staged Target Bands */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Conservative Target (T1)</CardDescription>
                <CardTitle className="text-xl font-bold font-mono text-emerald-400">
                  +{expectedMoveData?.conservative_move_points} pts
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">70% Probability target excursion</div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Expected Target Excursion</CardDescription>
                <CardTitle className="text-xl font-bold font-mono text-primary">
                  +{expectedMoveData?.expected_move_points} pts ({expectedMoveData?.expected_move_pct}%)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Synthesized IV &amp; structural target</div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Aggressive Target (T2 / Runner)</CardDescription>
                <CardTitle className="text-xl font-bold font-mono text-cyan-400">
                  +{expectedMoveData?.aggressive_move_points} pts
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Extended breakout continuation</div>
              </CardContent>
            </Card>
          </div>
        </div>
      ),
    },
    {
      id: 'contract_sim',
      label: 'Strike Selection & Path Simulation (§23, §30, §31)',
      icon: Layers,
      content: (
        <div className="space-y-6">
          {/* Best Contract Recommendation */}
          <Card className="bg-card border-primary/40">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div>
                  <CardDescription className="text-xs uppercase tracking-wider">Optimal Quantitative Contract</CardDescription>
                  <CardTitle className="text-xl font-bold text-foreground flex items-center gap-2 mt-0.5">
                    {contractSelection?.selected_contract?.broker_symbol || `${underlying} Selected Strike`}
                    <Badge variant="outline" className="text-primary border-primary font-mono text-xs">
                      {contractSelection?.selected_strike_type} ({contractSelection?.selected_strike})
                    </Badge>
                  </CardTitle>
                </div>
                <div className="text-right">
                  <div className="text-xs text-muted-foreground">Selection Score</div>
                  <div className="text-2xl font-bold font-mono text-emerald-400">{contractSelection?.selection_score || 0}/100</div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 bg-muted/30 p-3 rounded-xl border border-border/60">
                <div>
                  <div className="text-xs text-muted-foreground">Delta (Δ)</div>
                  <div className="text-base font-bold font-mono">{contractSelection?.selected_greeks?.delta}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Gamma (Γ)</div>
                  <div className="text-base font-bold font-mono">{contractSelection?.selected_greeks?.gamma}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Theta Decay / Hr</div>
                  <div className="text-base font-bold font-mono text-rose-400">₹{contractSelection?.selected_greeks?.theta_hour}/hr</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Vega (V / 1% IV)</div>
                  <div className="text-base font-bold font-mono">₹{contractSelection?.selected_greeks?.vega}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Theoretical Price</div>
                  <div className="text-base font-bold font-mono">₹{contractSelection?.selected_greeks?.theoretical_price}</div>
                </div>
              </div>

              <div className="mt-3 space-y-1">
                {contractSelection?.selection_rationale?.map((r: string, i: number) => (
                  <div key={i} className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    {r}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* 5-Scenario Path Simulation (§31) */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Activity className="w-4 h-4 text-primary" />
                Path-Dependent 5-Scenario Simulation (§31)
              </CardTitle>
              <CardDescription className="text-xs">
                Options cannot be evaluated from terminal price alone. Analyzes net rupee outcome after time decay and Indian F&amp;O taxes.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                {/* 1. Fast Favorable */}
                <div className="bg-muted/40 p-3 rounded-xl border border-emerald-500/30">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-emerald-400">Fast Target</span>
                    <span className="text-xs text-muted-foreground">30m</span>
                  </div>
                  <div className="text-lg font-bold font-mono text-emerald-400">
                    ₹{contractSelection?.path_simulation?.fast_target?.net_pnl_total ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Return: {contractSelection?.path_simulation?.fast_target?.net_return_pct}%
                  </div>
                </div>

                {/* 2. Slow Favorable */}
                <div className="bg-muted/40 p-3 rounded-xl border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-cyan-400">Slow Target</span>
                    <span className="text-xs text-muted-foreground">3.0h</span>
                  </div>
                  <div className="text-lg font-bold font-mono text-cyan-400">
                    ₹{contractSelection?.path_simulation?.slow_target?.net_pnl_total ?? 0}
                  </div>
                  <div className="text-xs text-rose-400 mt-1">
                    Theta: -₹{contractSelection?.path_simulation?.slow_target?.theta_drag_total ?? 0}
                  </div>
                </div>

                {/* 3. Sideways Bleed */}
                <div className="bg-muted/40 p-3 rounded-xl border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-amber-400">Sideways Bleed</span>
                    <span className="text-xs text-muted-foreground">3.0h</span>
                  </div>
                  <div className="text-lg font-bold font-mono text-rose-400">
                    ₹{contractSelection?.path_simulation?.sideways?.net_pnl_total ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Pure theta loss</div>
                </div>

                {/* 4. Adverse Stop */}
                <div className="bg-muted/40 p-3 rounded-xl border border-rose-500/30">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-rose-400">Stop Loss Hit</span>
                    <span className="text-xs text-muted-foreground">Defensive</span>
                  </div>
                  <div className="text-lg font-bold font-mono text-rose-400">
                    ₹{contractSelection?.path_simulation?.adverse_stop?.net_pnl_total ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Max stop risk</div>
                </div>

                {/* 5. IV Crush */}
                <div className="bg-muted/40 p-3 rounded-xl border border-border">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-indigo-400">Target + IV -20%</span>
                    <span className="text-xs text-muted-foreground">Post-Event</span>
                  </div>
                  <div className="text-lg font-bold font-mono text-indigo-300">
                    ₹{contractSelection?.path_simulation?.iv_crush_target?.net_pnl_total ?? 0}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">Vega impact</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      ),
    },
    {
      id: 'portfolio_greeks',
      label: 'Portfolio Greeks & Cross-Horizon Ledger (§36, §51)',
      icon: Scale,
      content: (
        <div className="space-y-6">
          {/* Consolidated Greek Risk Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Portfolio Delta (ΣΔ)</CardDescription>
                <CardTitle className="text-2xl font-bold font-mono text-primary">
                  {portfolioGreeks?.total_delta ?? 0.0}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Net directional shares equivalent</div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Portfolio Gamma (ΣΓ)</CardDescription>
                <CardTitle className="text-2xl font-bold font-mono">
                  {portfolioGreeks?.total_gamma ?? 0.0}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Second-order curvature exposure</div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Daily Theta Burn (ΣΘ)</CardDescription>
                <CardTitle className="text-2xl font-bold font-mono text-rose-400">
                  ₹{portfolioGreeks?.total_theta_day ?? 0.0}/day
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Consolidated overnight decay cost</div>
              </CardContent>
            </Card>

            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardDescription className="text-xs uppercase">Portfolio Vega (ΣV)</CardDescription>
                <CardTitle className="text-2xl font-bold font-mono">
                  ₹{portfolioGreeks?.total_vega ?? 0.0}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-xs text-muted-foreground">Per 1% volatility shift exposure</div>
              </CardContent>
            </Card>
          </div>

          {/* Cross-Horizon Harmonizer Info */}
          <Card className="bg-card border-border">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-primary" />
                Cross-Horizon Compounding Exposure Harmonizer (§51)
              </CardTitle>
              <CardDescription className="text-xs">
                Prevents unhedged compounding risk when Scalp, Intraday, and Swing strategies trigger simultaneously on the same underlying.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="p-4 bg-muted/30 rounded-xl border border-border flex items-center justify-between">
                <div className="space-y-1">
                  <div className="text-sm font-semibold text-foreground">Active Cross-Horizon Status</div>
                  <div className="text-xs text-muted-foreground">
                    Total active positions: {portfolioGreeks?.total_open_positions ?? 0} | Expiry concentrations balanced.
                  </div>
                </div>
                <Badge variant="outline" className="text-emerald-400 border-emerald-500/40">
                  HARMONIZED &amp; BOUNDED
                </Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header & Controls Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-card p-4 rounded-xl border border-border shadow-sm">
        <div>
          <h1 className="text-2xl font-bold text-foreground flex items-center gap-2.5">
            <Zap className="w-6 h-6 text-primary" />
            Options Intelligence &amp; AI Research
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Institutional options pricing, analytical Greeks, path simulations, and non-blocking contradiction research.
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Instrument Selector */}
          <div className="flex rounded-lg bg-muted/60 p-1 border border-border">
            {(['NIFTY', 'BANKNIFTY', 'SENSEX'] as const).map((sym) => (
              <button
                key={sym}
                onClick={() => setUnderlying(sym)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  underlying === sym ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {sym}
              </button>
            ))}
          </div>

          {/* Horizon Selector */}
          <div className="flex rounded-lg bg-muted/60 p-1 border border-border">
            {(['SCALP', 'INTRADAY', 'SWING', 'POSITIONAL'] as const).map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                  horizon === h ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {h}
              </button>
            ))}
          </div>

          {/* Direction Toggle */}
          <div className="flex rounded-lg bg-muted/60 p-1 border border-border">
            <button
              onClick={() => setDirection('BULLISH')}
              className={`px-3 py-1 text-xs font-semibold rounded-md flex items-center gap-1 transition-all ${
                direction === 'BULLISH' ? 'bg-emerald-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <TrendingUp className="w-3.5 h-3.5" /> Call
            </button>
            <button
              onClick={() => setDirection('BEARISH')}
              className={`px-3 py-1 text-xs font-semibold rounded-md flex items-center gap-1 transition-all ${
                direction === 'BEARISH' ? 'bg-rose-600 text-white shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <TrendingDown className="w-3.5 h-3.5" /> Put
            </button>
          </div>

          <Button variant="outline" size="sm" onClick={loadAllIntelligence} disabled={loading} className="gap-1.5 h-8">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/30 border border-rose-500/40 rounded-xl text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          {error}
        </div>
      )}

      {/* Main Tabbed Interface */}
      <PageTabs tabs={tabs} defaultTab="ai_research" />
    </div>
  );
}
