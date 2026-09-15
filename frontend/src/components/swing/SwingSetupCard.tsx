'use client';

import { useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Shield,
  Target,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Play,
  Bot,
  Info,
  Layers,
  Activity,
} from 'lucide-react';
import type { SwingSetupDTO } from '@/lib/api/swing';
import { SwingAIThesisModal } from './SwingAIThesisModal';

export type SwingSetupCardProps = {
  setup: SwingSetupDTO;
  onEnterTrade?: (setupId: string, fillPremium: number) => Promise<any>;
};

export function SwingSetupCard({ setup, onEnterTrade }: SwingSetupCardProps) {
  const [showThesis, setShowThesis] = useState(false);
  const [entering, setEntering] = useState(false);
  const [entered, setEntered] = useState(setup.signal_state === 'ENTERED');

  const handleEnter = async () => {
    if (!onEnterTrade || entered) return;
    setEntering(true);
    try {
      await onEnterTrade(setup.setup_id, setup.entry_premium);
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
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-emerald-500/20 text-emerald-500 border border-emerald-500/30 animate-pulse">TRIGGERED</span>;
      case 'READY':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-sky-500/20 text-sky-400 border border-sky-500/30">READY</span>;
      case 'ENTERED':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">ACTIVE</span>;
      case 'BLOCKED':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/30">BLOCKED</span>;
      default:
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-muted text-muted-foreground border border-border">RADAR</span>;
    }
  };

  const isCall = setup.option_type === 'CE';
  const delta = setup.greeks?.delta ?? 0;
  const thetaDay = setup.greeks?.theta_day ?? 0;
  const vega = setup.greeks?.vega ?? 0;
  const ivPct = (setup.iv * 100).toFixed(1);
  const validity = setup.trade_validity;

  return (
    <>
      <div className="flex flex-col rounded-xl border border-border bg-card text-card-foreground shadow-xs hover:border-border/80 transition-all overflow-hidden">
        {/* Card Header */}
        <div className="p-4 border-b border-border/60 bg-muted/20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-base font-bold tracking-tight text-foreground">{setup.underlying}</span>
                {setup.horizon === 'INTRADAY' ? (
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-md bg-amber-500/15 text-amber-500 dark:text-amber-400 border border-amber-500/30 flex items-center gap-1">
                    <span>⚡</span> INTRADAY ({setup.timeframe || '15M'})
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-[10px] font-bold rounded-md bg-sky-500/10 text-sky-500 dark:text-sky-400 border border-sky-500/30 flex items-center gap-1">
                    <span>📅</span> POSITIONAL (1D)
                  </span>
                )}
                <span className={`px-2 py-0.5 text-[11px] font-bold rounded-md border ${
                  isCall
                    ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30'
                    : 'bg-rose-500/10 text-rose-500 border-rose-500/30'
                }`}>
                  {setup.strike} {setup.option_type}
                </span>
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
                  DTE: {setup.dte}d ({setup.expiry_date})
                </span>
                {getStateBadge(setup.signal_state)}
              </div>
              <div className="text-[11px] text-muted-foreground mt-1 font-medium flex items-center gap-2 flex-wrap">
                <span>{setup.strategy.replace(/_/g, ' ')}</span>
                <span>•</span>
                <span className="font-mono">Lot: {setup.lot_size}</span>
                {setup.vwap && (
                  <>
                    <span>•</span>
                    <span className="font-mono text-primary/80">VWAP: ₹{setup.vwap.toFixed(1)}</span>
                  </>
                )}
              </div>
            </div>

            {/* Quality Score */}
            <div className="flex flex-col items-end shrink-0">
              <div className={`px-2.5 py-0.5 rounded-lg border font-mono font-bold text-sm ${getScoreColor(setup.score.total)}`}>
                {Math.round(setup.score.total)}
                <span className="text-[10px] font-normal opacity-70">/100</span>
              </div>
              <span className="text-[9px] text-muted-foreground mt-0.5">Setup Quality</span>
            </div>
          </div>

          {/* 4-Layer Validity Indicator (§6) */}
          {validity && (
            <div className="mt-2.5 pt-2 border-t border-border/40 flex items-center justify-between text-[10px]">
              <span className="text-muted-foreground font-medium">4-Layer Gate:</span>
              <div className="flex items-center gap-2">
                <span className={`flex items-center gap-1 font-mono ${validity.underlying_valid ? 'text-emerald-500' : 'text-rose-500'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.underlying_valid ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  Underlying
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.option_valid ? 'text-emerald-500' : 'text-rose-500'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.option_valid ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  Option
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.portfolio_valid ? 'text-emerald-500' : 'text-rose-500'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.portfolio_valid ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  Portfolio
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.execution_valid ? 'text-emerald-500' : 'text-rose-500'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.execution_valid ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  Execution
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Card Body: Option Premium Levels & Dual-Stop */}
        <div className="p-4 space-y-3 flex-1 flex flex-col justify-between text-xs">
          <div className="grid grid-cols-3 gap-2 p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div>
              <div className="text-muted-foreground text-[10px] uppercase font-semibold">Entry Premium</div>
              <div className="font-semibold text-foreground text-sm font-mono">₹{setup.entry_premium.toFixed(2)}</div>
              <div className="text-[10px] text-muted-foreground">Spot: ₹{setup.spot_price.toFixed(1)}</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[10px] uppercase font-semibold">Option Stop</div>
              <div className="font-semibold text-destructive text-sm font-mono">₹{setup.stop_premium.toFixed(2)}</div>
              <div className="text-[10px] text-destructive/80 font-mono">Spot Inv: ₹{setup.spot_stop.toFixed(1)}</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[10px] uppercase font-semibold">Targets (1.5R / 3R)</div>
              <div className="font-semibold text-emerald-500 text-sm font-mono">₹{setup.target_premium_1.toFixed(2)}</div>
              <div className="text-[10px] text-emerald-600/80 dark:text-emerald-400/80 font-mono">T2: ₹{setup.target_premium_2.toFixed(2)}</div>
            </div>
          </div>

          {/* Greeks & IV Telemetry Bar */}
          <div className="grid grid-cols-4 gap-1 p-2 rounded-lg bg-background border border-border/60 text-[11px] text-center font-mono">
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Delta (Δ)</span>
              <span className="font-semibold text-foreground">{delta.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Theta (Θ/d)</span>
              <span className="font-semibold text-rose-500">-₹{Math.abs(thetaDay).toFixed(1)}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Vega (ν)</span>
              <span className="font-semibold text-foreground">₹{vega.toFixed(1)}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">IV (Rank)</span>
              <span className="font-semibold text-sky-500">{ivPct}% ({setup.iv_percentile.toFixed(0)}%)</span>
            </div>
          </div>

          {/* Sizing & Risk per Lot */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <div className="flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-primary" />
              <span>Risk/Lot: <strong className="text-foreground font-mono">₹{Math.round(setup.premium_risk_per_lot)}</strong></span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Hold: <strong className="text-foreground">{setup.horizon === 'INTRADAY' ? 'Intraday (15:15)' : `${setup.expected_holding_days}d`}</strong></span>
            </div>
            <div className="flex items-center gap-1">
              <Activity className="w-3.5 h-3.5 text-amber-500" />
              <span>Theta Drag: <strong className="text-foreground font-mono">{setup.theta_drag_ratio.toFixed(1)}%</strong></span>
            </div>
          </div>

          {/* Confirmations List */}
          <div className="space-y-1 pt-1 border-t border-border/40">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              Thesis & Volatility Check
            </div>
            <div className="space-y-1 text-[11px] text-foreground/90">
              {setup.technical_reasons.slice(0, 1).map((r, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                  <span className="line-clamp-1">{r}</span>
                </div>
              ))}
              {setup.options_reasons.slice(0, 1).map((r, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-sky-500 shrink-0 mt-0.5" />
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

            {setup.signal_state !== 'BLOCKED' && setup.trade_validity?.overall_valid !== false ? (
              <button
                onClick={handleEnter}
                disabled={entering || entered}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-medium transition-colors disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>{entered ? 'In Portfolio' : entering ? 'Entering...' : 'Enter Position'}</span>
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
