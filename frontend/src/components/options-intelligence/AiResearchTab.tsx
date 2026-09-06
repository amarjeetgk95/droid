'use client';

import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Brain,
  Scale,
  ShieldAlert,
  ShieldCheck,
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Globe,
  TrendingUp,
  FileText,
  Activity,
  Layers,
  Sparkles,
} from 'lucide-react';
import { FinancialResearchReport, SourcedEvidence } from './options-types';

interface AiResearchTabProps {
  researchData: FinancialResearchReport | null;
  onSynthesizeAI: () => void;
  synthesizing: boolean;
}

export const AiResearchTab: React.FC<AiResearchTabProps> = ({
  researchData,
  onSynthesizeAI,
  synthesizing,
}) => {
  const [evidenceFilter, setEvidenceFilter] = useState<'ALL' | 'SUPPORTIVE' | 'CONTRADICTORY' | 'REGULATORY'>('ALL');

  const isComplete = researchData?.research_status === 'COMPLETE';
  const counterScore = researchData?.contradiction_analysis?.counter_weight_score ?? 0;

  // Impact badge
  const renderImpactBadge = (impact?: string) => {
    switch (impact) {
      case 'STRENGTHEN':
        return <Badge className="bg-emerald-500 hover:bg-emerald-600 text-white font-bold px-3 py-1 text-xs">STRENGTHENED (+)</Badge>;
      case 'BLOCK':
        return <Badge className="bg-rose-600 hover:bg-rose-700 text-white font-bold px-3 py-1 text-xs">BLOCKED (NO-TRADE)</Badge>;
      case 'WEAKEN':
        return <Badge className="bg-amber-500 hover:bg-amber-600 text-black font-bold px-3 py-1 text-xs">WEAKENED (-)</Badge>;
      default:
        return <Badge variant="outline" className="px-3 py-1 text-xs font-semibold text-muted-foreground border-border">NO CHANGE</Badge>;
    }
  };

  // Effect badge
  const renderEffectBadge = (effect: string) => {
    switch (effect) {
      case 'SUPPORTIVE':
        return <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-400 bg-emerald-500/10 border border-emerald-500/25 px-2 py-0.5 rounded-md">Supportive</span>;
      case 'CONTRADICTORY':
        return <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-400 bg-rose-500/10 border border-rose-500/25 px-2 py-0.5 rounded-md">Contradictory</span>;
      default:
        return <span className="inline-flex items-center gap-1 text-[11px] font-medium text-muted-foreground bg-muted/40 border border-border/40 px-2 py-0.5 rounded-md">Neutral</span>;
    }
  };

  // Credibility tier label
  const renderSourceTierBadge = (tier: number) => {
    switch (tier) {
      case 1:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/30 font-semibold font-mono">Tier 1: Regulator</span>;
      case 2:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-semibold font-mono">Tier 2: Central Bank</span>;
      case 3:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30 font-semibold font-mono">Tier 3: Exchange Filing</span>;
      case 4:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-semibold font-mono">Tier 4: Market Terminal</span>;
      case 5:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-semibold font-mono">Tier 5: Financial Press</span>;
      default:
        return <span className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 font-mono">Tier {tier}: Secondary</span>;
    }
  };

  // Evidence list compilation
  const allEvidence: SourcedEvidence[] = [
    ...(researchData?.supporting_evidence || []),
    ...(researchData?.contradiction_analysis?.contradicting_evidence || []),
  ];

  const filteredEvidence = allEvidence.filter((ev) => {
    if (evidenceFilter === 'SUPPORTIVE') return ev.effect === 'SUPPORTIVE';
    if (evidenceFilter === 'CONTRADICTORY') return ev.effect === 'CONTRADICTORY';
    if (evidenceFilter === 'REGULATORY') return ev.source_tier <= 2;
    return true;
  });

  return (
    <div className="space-y-5">
      {/* 1. Sleek Engine Health & Verification Ribbon */}
      <div
        className={`p-3.5 rounded-xl border flex flex-col md:flex-row items-start md:items-center justify-between gap-3 ${
          isComplete
            ? 'bg-card/70 border-emerald-500/30'
            : 'bg-card/70 border-amber-500/30'
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${
              isComplete
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
            }`}
          >
            <Brain className="w-4 h-4" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-foreground">
                {isComplete ? 'AI Financial Research Engine: Active & Verified' : 'Deterministic Fallback Active (§34)'}
              </span>
              <Badge
                className={`text-[10px] font-mono font-semibold ${
                  isComplete
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                    : 'bg-amber-500/20 text-amber-400 border-amber-500/40'
                }`}
              >
                {researchData?.research_status || 'IDLE'}
              </Badge>
              <span className="text-[10px] font-mono text-muted-foreground">
                Model: {researchData?.model_version || 'v1.0'}
              </span>
              <span className="text-[10px] font-mono text-muted-foreground">
                • 7-Tier Adversarial Protection
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              {isComplete
                ? `Validated ${researchData?.supporting_evidence?.length || 0} supportive and ${
                    researchData?.contradiction_analysis?.contradicting_evidence?.length || 0
                  } contradicting institutional sources.`
                : 'Cache cold or stale. Per §34, missing AI never fabricates approval; quantitative options math proceeds safely at neutral baseline.'}
            </p>
          </div>
        </div>

        <Button
          onClick={onSynthesizeAI}
          disabled={synthesizing}
          size="sm"
          variant="outline"
          className="gap-2 text-xs h-8 border-border/70 hover:bg-muted/70 shrink-0 self-end md:self-auto"
        >
          <Sparkles className={`w-3.5 h-3.5 ${synthesizing ? 'animate-spin text-primary' : 'text-primary'}`} />
          {synthesizing ? 'Synthesizing...' : 'Re-Run Synthesis'}
        </Button>
      </div>

      {/* 2. Executive Verdict HUD (3 Clean Cockpit Cards) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {/* Assessment Card */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Research Assessment
            </CardDescription>
            <CardTitle className="text-lg font-bold text-foreground flex items-center gap-2">
              {researchData?.research_assessment?.replace(/_/g, ' ') || 'MIXED'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2">
              {researchData?.bull_case_summary || 'No active AI research assessment available.'}
            </p>
            <div className="flex items-center gap-2 text-[10px] font-mono">
              <span className="text-muted-foreground">Uncertainty:</span>
              <span
                className={`font-semibold px-1.5 py-0.5 rounded ${
                  researchData?.uncertainty_level === 'LOW'
                    ? 'bg-emerald-500/15 text-emerald-400'
                    : researchData?.uncertainty_level === 'HIGH'
                    ? 'bg-rose-500/15 text-rose-400'
                    : 'bg-amber-500/15 text-amber-400'
                }`}
              >
                {researchData?.uncertainty_level || 'MODERATE'}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* AI Signal Impact Card */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              AI Signal Contract Impact (§22)
            </CardDescription>
            <div className="mt-1">{renderImpactBadge(researchData?.ai_impact)}</div>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {researchData?.impact_rationale?.[0] || 'Quantitative setup operating within baseline risk limits.'}
            </p>
          </CardContent>
        </Card>

        {/* Contradiction Threat Meter Card */}
        <Card className="bg-card/80 border-border/60 shadow-xs">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardDescription className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Contradiction Threat Score (§16)
              </CardDescription>
              <span className="text-[10px] font-mono text-muted-foreground">Ceiling: 65%</span>
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-2xl font-bold font-mono text-amber-400">{counterScore}%</span>
              <span className="text-[11px] text-muted-foreground">counter-weight</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {/* Visual Threat Bar */}
            <div className="w-full bg-muted/60 h-2 rounded-full overflow-hidden relative">
              <div
                className={`h-full transition-all ${
                  counterScore >= 65
                    ? 'bg-rose-500'
                    : counterScore >= 45
                    ? 'bg-amber-500'
                    : 'bg-emerald-500'
                }`}
                style={{ width: `${Math.min(100, counterScore)}%` }}
              />
              {/* 65% Block Ceiling Indicator */}
              <div className="absolute top-0 bottom-0 left-[65%] w-0.5 bg-rose-500/80" title="65% Safety Block Ceiling" />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {counterScore >= 65
                ? 'Counter-evidence exceeds 65% ceiling; trade vetoed.'
                : counterScore >= 45
                ? 'Elevated counter-evidence; defensive position sizing.'
                : 'Counter-evidence safely bounded below threat threshold.'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 3. Streamlined Six Financial Context Pillars Ribbon (§10-§15) */}
      <Card className="bg-card/70 border-border/60 shadow-xs">
        <CardHeader className="py-2.5 px-4 border-b border-border/40 flex flex-row items-center justify-between">
          <CardTitle className="text-xs font-semibold flex items-center gap-2 text-foreground">
            <Activity className="w-3.5 h-3.5 text-primary" />
            Six Financial Context Pillars
          </CardTitle>
          <span className="text-[10px] text-muted-foreground font-mono">Tiers 1–5 Macro Corroboration</span>
        </CardHeader>
        <CardContent className="p-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {[
              { label: 'Market Context', effect: researchData?.market_context || 'NEUTRAL' },
              { label: 'Macro / Rates', effect: researchData?.macro_context || 'NEUTRAL' },
              { label: 'Fundamentals', effect: researchData?.fundamental_context || 'NEUTRAL' },
              { label: 'News & Events', effect: researchData?.news_context || 'NEUTRAL' },
              { label: 'Positioning', effect: researchData?.sentiment_context || 'NEUTRAL' },
              { label: 'Cross-Asset', effect: researchData?.cross_asset_context || 'NEUTRAL' },
            ].map((pillar, idx) => (
              <div key={idx} className="bg-muted/40 p-2.5 rounded-lg border border-border/50 text-center">
                <div className="text-[11px] font-medium text-muted-foreground mb-1">{pillar.label}</div>
                <div>{renderEffectBadge(pillar.effect)}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 4. Institutional Thesis vs Counter-Thesis Dossier (§16, §17) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {/* Supporting Dossier */}
        <Card className="bg-card/70 border-border/60 shadow-xs">
          <CardHeader className="pb-2.5 border-b border-border/40">
            <div className="flex items-center justify-between">
              <CardTitle className="text-xs font-bold text-foreground flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-500" />
                Supporting Catalysts &amp; Market Drivers
              </CardTitle>
              <Badge variant="outline" className="text-[10px] font-mono text-emerald-400 border-emerald-500/30">
                Corroborating
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-3.5 space-y-3">
            <div className="p-2.5 bg-muted/40 border border-border/50 rounded-lg text-xs text-foreground font-medium">
              {researchData?.key_catalysts?.[0] || 'Technical momentum expansion above institutional session anchor.'}
            </div>
            <div>
              <div className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5">
                Key Flow Drivers
              </div>
              <ul className="text-xs text-muted-foreground space-y-1">
                {researchData?.supporting_evidence?.slice(0, 3).map((ev, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                    <span>
                      <strong className="text-foreground">{ev.source_name}:</strong> {ev.claim}
                    </span>
                  </li>
                )) || <li className="text-xs text-muted-foreground">Baseline institutional liquidity flow.</li>}
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* Counter-Thesis Dossier */}
        <Card className="bg-card/70 border-border/60 shadow-xs">
          <CardHeader className="pb-2.5 border-b border-border/40">
            <div className="flex items-center justify-between">
              <CardTitle className="text-xs font-bold text-foreground flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-rose-500" />
                Strongest Counter-Thesis &amp; Invalidation (§16)
              </CardTitle>
              <Badge variant="outline" className="text-[10px] font-mono text-rose-400 border-rose-500/30">
                Disconfirmation
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="p-3.5 space-y-3">
            <div className="p-2.5 bg-muted/40 border border-border/50 rounded-lg text-xs text-foreground font-medium">
              {researchData?.contradiction_analysis?.strongest_counter_argument || 'No material counter-catalysts detected.'}
            </div>
            <div>
              <div className="text-[11px] font-semibold text-rose-400 uppercase tracking-wider mb-1.5">
                Invalidation Triggers
              </div>
              <ul className="text-xs text-muted-foreground space-y-1">
                {researchData?.contradiction_analysis?.invalidation_conditions?.map((c, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500 mt-1.5 shrink-0" />
                    <span>{c}</span>
                  </li>
                )) || <li>Local structural stop breach.</li>}
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 5. Sourced Evidence Ledger (§18 Source Hierarchy) */}
      <Card className="bg-card/70 border-border/60 shadow-xs">
        <CardHeader className="py-3 px-4 border-b border-border/40 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <CardTitle className="text-xs font-bold flex items-center gap-2 text-foreground">
              <BarChart3 className="w-4 h-4 text-primary" />
              Sourced Evidence Ledger (§18 Institutional Hierarchy)
            </CardTitle>
            <CardDescription className="text-[11px]">
              Credibility-weighted claims evaluated through adversarial prompt protection.
            </CardDescription>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center rounded-lg bg-muted/60 p-0.5 border border-border/50 text-[11px]">
            {(['ALL', 'SUPPORTIVE', 'CONTRADICTORY', 'REGULATORY'] as const).map((filterKey) => (
              <button
                key={filterKey}
                onClick={() => setEvidenceFilter(filterKey)}
                className={`px-2 py-1 rounded-md font-semibold transition-all ${
                  evidenceFilter === filterKey
                    ? 'bg-card text-foreground shadow-xs font-bold'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {filterKey}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {filteredEvidence.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-border/40 bg-muted/20 text-muted-foreground uppercase text-[10px] tracking-wider font-mono">
                    <th className="py-2.5 px-3.5">Credibility Tier</th>
                    <th className="py-2.5 px-3">Source Name</th>
                    <th className="py-2.5 px-3">Verified Claim</th>
                    <th className="py-2.5 px-3">Impact</th>
                    <th className="py-2.5 px-3.5 text-right">Confidence</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {filteredEvidence.map((item, idx) => (
                    <tr key={idx} className="hover:bg-muted/20 transition-colors">
                      <td className="py-2 px-3.5 whitespace-nowrap">{renderSourceTierBadge(item.source_tier)}</td>
                      <td className="py-2 px-3 font-medium text-foreground whitespace-nowrap">{item.source_name}</td>
                      <td className="py-2 px-3 text-muted-foreground leading-relaxed max-w-md">{item.claim}</td>
                      <td className="py-2 px-3 whitespace-nowrap">{renderEffectBadge(item.effect)}</td>
                      <td className="py-2 px-3.5 text-right whitespace-nowrap font-mono text-[11px]">
                        <div className="flex items-center justify-end gap-1.5">
                          <span className="w-10 text-right">{item.confidence}%</span>
                          <div className="w-8 bg-muted/60 h-1.5 rounded-full overflow-hidden">
                            <div className="bg-primary h-full rounded-full" style={{ width: `${item.confidence}%` }} />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground text-xs">
              {isComplete
                ? 'No evidence matches the selected filter.'
                : 'Deterministic Fallback active (§34). Background context cold; live quantitative stream operating at neutral baseline.'}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
