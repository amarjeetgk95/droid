'use client';

import React from 'react';
import { AIInsightResponse } from '@/lib/types';
import {
  Target,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
} from 'lucide-react';

interface AITradePlaybookProps {
  insight: AIInsightResponse;
}

export function AITradePlaybook({ insight }: AITradePlaybookProps) {
  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-4">
      <div className="flex items-center gap-2 pb-3 border-b border-border">
        <div className="p-2 bg-primary/10 rounded-lg text-primary">
          <Target className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-foreground">What should I do?</h3>
          <p className="text-xs text-muted-foreground">
            A safe, step-by-step plan based on what the market is doing
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Recommended Framework */}
        <div className="bg-secondary/30 rounded-xl p-4 border border-border space-y-2">
          <div className="flex items-center gap-2 font-bold text-foreground">
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            <span>Suggested game plan</span>
          </div>
          <p className="text-muted-foreground leading-relaxed font-sans whitespace-pre-line">
            {insight.recommended_strategy_framework || 'Maintain defined-risk option spreads with positive theta decay.'}
          </p>
        </div>

        {/* Risk Management & Invalidation */}
        <div className="bg-secondary/30 rounded-xl p-4 border border-border space-y-2">
          <div className="flex items-center gap-2 font-bold text-foreground">
            <ShieldAlert className="w-4 h-4 text-amber-500" />
            <span>When to exit if it goes wrong</span>
          </div>
          <p className="text-muted-foreground leading-relaxed font-sans whitespace-pre-line">
            {insight.risk_management_notes || 'Always enforce maximum 1-2% account risk per trade and exit upon breach of key S/R pivots.'}
          </p>
        </div>
      </div>

      {/* Compliance / Disclaimer */}
      <div className="pt-2 text-[11px] text-muted-foreground flex items-center gap-2 border-t border-border/50">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        <span>
          <strong>Please note:</strong> {insight.disclaimer || 'This is computer analysis for learning, not financial advice. You can still lose money.'}
        </span>
      </div>
    </div>
  );
}
