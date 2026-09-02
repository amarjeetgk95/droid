'use client';

import React from 'react';
import { AIInsightResponse } from '@/lib/types';
import {
  Compass,
  Layers,
  Building2,
  CheckCircle2,
  ChevronRight,
} from 'lucide-react';

interface AIQuantPillarsProps {
  insight: AIInsightResponse;
}

export function AIQuantPillars({ insight }: AIQuantPillarsProps) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Pillar 1: Key Levels & Price Action */}
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between space-y-3">
        <div className="space-y-2.5">
          <div className="flex items-center gap-2 pb-2 border-b border-border/60">
            <div className="p-1.5 bg-blue-500/10 text-blue-500 rounded-lg">
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                1. Key Levels & S/R Pivots
              </h3>
              <p className="text-[10.5px] text-muted-foreground">Volume profile & pivot boundaries</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            {insight.regime_and_levels || 'Price is trading within the defined daily pivot range.'}
          </p>
        </div>

        <div className="pt-2 border-t border-border/40 text-[11px] font-medium text-blue-500 flex items-center justify-between">
          <span>Boundary Analysis</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
      </div>

      {/* Pillar 2: Option Chain Walls & Greeks */}
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between space-y-3">
        <div className="space-y-2.5">
          <div className="flex items-center gap-2 pb-2 border-b border-border/60">
            <div className="p-1.5 bg-purple-500/10 text-purple-500 rounded-lg">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                2. Option Walls & Max Pain
              </h3>
              <p className="text-[10.5px] text-muted-foreground">Call & Put writer concentrations</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            {insight.options_interpretation || 'Option chain shows balanced Put-Call OI distribution.'}
          </p>
        </div>

        <div className="pt-2 border-t border-border/40 text-[11px] font-medium text-purple-500 flex items-center justify-between">
          <span>Derivatives Structure</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
      </div>

      {/* Pillar 3: Futures & Institutional Flow */}
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs flex flex-col justify-between space-y-3">
        <div className="space-y-2.5">
          <div className="flex items-center gap-2 pb-2 border-b border-border/60">
            <div className="p-1.5 bg-emerald-500/10 text-emerald-500 rounded-lg">
              <Building2 className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                3. Institutional (FII/DII) Flow
              </h3>
              <p className="text-[10.5px] text-muted-foreground">Futures buildup & cash market flow</p>
            </div>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            {insight.futures_flow_analysis || 'Futures basis and institutional flow show neutral rollover.'}
          </p>
        </div>

        <div className="pt-2 border-t border-border/40 text-[11px] font-medium text-emerald-500 flex items-center justify-between">
          <span>Smart Money Positioning</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </div>
      </div>
    </div>
  );
}
