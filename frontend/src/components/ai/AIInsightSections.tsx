'use client';

import { AIInsightResponse } from '@/lib/types';
import { Activity, TrendingUp, Compass, Target } from 'lucide-react';

export function AIInsightSections({
  insight,
}: {
  insight: AIInsightResponse | null;
}) {
  if (!insight) return null;

  const sections = [
    {
      title: 'Options Microstructure & Volatility Interpretation',
      icon: <Activity className="w-4 h-4 text-primary" />,
      content: insight.options_interpretation,
      accent: 'border-primary/30',
    },
    {
      title: 'Futures Flow, Basis & Rollover Momentum',
      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
      content: insight.futures_flow_analysis,
      accent: 'border-emerald-500/30',
    },
    {
      title: 'Market Regime, S/R Pivots & Volume Profile',
      icon: <Compass className="w-4 h-4 text-warning" />,
      content: insight.regime_and_levels,
      accent: 'border-warning/30',
    },
    {
      title: 'Recommended Strategy Framework & Risk Setup',
      icon: <Target className="w-4 h-4 text-purple-400" />,
      content: insight.recommended_strategy_framework,
      accent: 'border-purple-500/30',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {sections.map((sec, idx) => (
        <div
          key={idx}
          className={`bg-card border ${sec.accent} rounded-xl p-4 space-y-2 shadow-xs hover:border-foreground/20 transition-all`}
        >
          <div className="flex items-center gap-2">
            {sec.icon}
            <h3 className="font-bold text-xs text-foreground uppercase tracking-wider">
              {sec.title}
            </h3>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {sec.content}
          </p>
        </div>
      ))}
    </div>
  );
}
