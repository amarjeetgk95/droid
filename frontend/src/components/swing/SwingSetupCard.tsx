'use client';

import { useState } from 'react';
import {
  TrendingUp,
  Shield,
  Target,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Play,
  Bot,
  Info,
} from 'lucide-react';
import type { SwingSetupDTO } from '@/lib/api/swing';
import { SwingAIThesisModal } from './SwingAIThesisModal';

export type SwingSetupCardProps = {
  setup: SwingSetupDTO;
  onEnterTrade?: (setupId: string, fillPrice: number) => Promise<any>;
};

export function SwingSetupCard({ setup, onEnterTrade }: SwingSetupCardProps) {
  const [showThesis, setShowThesis] = useState(false);
  const [entering, setEntering] = useState(false);
  const [entered, setEntered] = useState(setup.signal_state === 'ENTERED');

  const handleEnter = async () => {
    if (!onEnterTrade || entered) return;
    setEntering(true);
    try {
      await onEnterTrade(setup.setup_id, setup.trigger_price);
      setEntered(true);
    } catch {
      // Error handled by parent hook
    } finally {
      setEntering(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/30';
    if (score >= 60) return 'text-sky-500 bg-sky-500/10 border-sky-500/30';
    if (score >= 45) return 'text-amber-500 bg-amber-500/10 border-amber-500/30';
    return 'text-muted-foreground bg-muted/40 border-border';
  };

  const getStateBadge = (state: string) => {
    switch (state) {
      case 'TRIGGERED':
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-emerald-500/20 text-emerald-500 border border-emerald-500/30 animate-pulse">TRIGGERED</span>;
      case 'READY':
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-sky-500/20 text-sky-400 border border-sky-500/30">READY TO TRIGGER</span>;
      case 'ENTERED':
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">POSITION ACTIVE</span>;
      case 'BLOCKED':
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30">RISK BLOCKED</span>;
      default:
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded-full bg-muted text-muted-foreground border border-border">ON RADAR</span>;
    }
  };

  return (
    <>
      <div className="flex flex-col rounded-xl border border-border bg-card text-card-foreground shadow-sm hover:border-border/80 transition-all overflow-hidden">
        {/* Card Header */}
        <div className="p-4 border-b border-border/60 bg-muted/20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold tracking-tight text-foreground">{setup.symbol}</span>
                <span className="text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground font-medium">
                  {setup.sector}
                </span>
                {getStateBadge(setup.signal_state)}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5 font-medium">
                {setup.strategy.replace(/_/g, ' ')}
              </div>
            </div>

            {/* Quality Score */}
            <div className="flex flex-col items-end">
              <div className={`px-2.5 py-1 rounded-lg border font-mono font-bold text-sm ${getScoreColor(setup.score.total)}`}>
                {setup.score.total}
                <span className="text-[10px] font-normal opacity-70">/100</span>
              </div>
              <span className="text-[10px] text-muted-foreground mt-0.5">Setup Quality</span>
            </div>
          </div>
        </div>

        {/* Card Body: Execution Levels Grid */}
        <div className="p-4 space-y-3.5 flex-1 flex flex-col justify-between text-xs">
          <div className="grid grid-cols-3 gap-2 p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div>
              <div className="text-muted-foreground text-[11px]">Trigger Entry</div>
              <div className="font-semibold text-foreground text-sm">₹{setup.trigger_price.toFixed(2)}</div>
              <div className="text-[10px] text-muted-foreground">Zone: ₹{setup.entry_zone_min} - ₹{setup.entry_zone_max}</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[11px]">Stop Loss</div>
              <div className="font-semibold text-destructive text-sm">₹{setup.stop_price.toFixed(2)}</div>
              <div className="text-[10px] text-destructive/80 font-mono">-{setup.risk_pct.toFixed(1)}% (₹{setup.risk_per_share})</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[11px]">Target 1 & 2</div>
              <div className="font-semibold text-emerald-500 text-sm">₹{setup.target_1.toFixed(2)}</div>
              <div className="text-[10px] text-emerald-600/80 dark:text-emerald-400/80">T2: ₹{setup.target_2.toFixed(2)} (3.0R)</div>
            </div>
          </div>

          {/* Key Metrics Row */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <div className="flex items-center gap-1.5">
              <Target className="w-3.5 h-3.5 text-primary" />
              <span>R:R (T1): <strong className="text-foreground">{setup.risk_reward_t1.toFixed(1)}x</strong></span>
            </div>
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Expected Hold: <strong className="text-foreground">{setup.expected_holding_days} Days</strong></span>
            </div>
            <div className="flex items-center gap-1.5">
              <Shield className="w-3.5 h-3.5 text-emerald-500" />
              <span>Daily ATR: <strong className="text-foreground">₹{setup.daily_atr.toFixed(1)}</strong></span>
            </div>
          </div>

          {/* Confirmations List */}
          <div className="space-y-1 pt-1 border-t border-border/40">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              Confirmations
            </div>
            <div className="space-y-1 text-[11px] text-foreground/90">
              {setup.technical_reasons.slice(0, 2).map((r, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                  <span className="line-clamp-1">{r}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="pt-2 border-t border-border/50 flex items-center gap-2">
            <button
              onClick={() => setShowThesis(true)}
              className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-medium transition-colors"
            >
              <Bot className="w-3.5 h-3.5 text-primary" />
              <span>AI Thesis</span>
            </button>

            {setup.signal_state !== 'BLOCKED' ? (
              <button
                onClick={handleEnter}
                disabled={entering || entered}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-medium transition-colors disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{entered ? 'In Portfolio' : entering ? 'Entering...' : 'Paper Enter'}</span>
              </button>
            ) : (
              <div className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-rose-500/10 text-rose-500 text-[11px] font-medium border border-rose-500/20">
                <AlertTriangle className="w-3.5 h-3.5" />
                <span>Blocked by Risk Gate</span>
              </div>
            )}
          </div>
        </div>
      </div>

      <SwingAIThesisModal
        setup={setup}
        isOpen={showThesis}
        onClose={() => setShowThesis(false)}
      />
    </>
  );
}
