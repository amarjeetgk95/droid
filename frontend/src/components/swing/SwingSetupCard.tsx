'use client';

import { useState } from 'react';
import {
  Shield,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Play,
  Bot,
  Activity,
} from 'lucide-react';
import type { SwingSetupDTO } from '@/lib/api/swing';
import { SwingAIThesisModal } from './SwingAIThesisModal';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { fmtINR, fmtNum } from '@/components/ui/desk';

export type SwingSetupCardProps = {
  setup: SwingSetupDTO;
  onEnterTrade?: (setupId: string, fillPremium: number) => Promise<any>;
};

export function SwingSetupCard({ setup, onEnterTrade }: SwingSetupCardProps) {
  const toast = useToast();
  const [showThesis, setShowThesis] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [entering, setEntering] = useState(false);
  const [entered, setEntered] = useState(setup.signal_state === 'ENTERED');
  const [enterError, setEnterError] = useState<string | null>(null);

  const entryPremium = Number.isFinite(setup.entry_premium) ? setup.entry_premium : null;

  const handleConfirmEntry = async () => {
    if (!onEnterTrade || entryPremium === null) return;
    setEntering(true);
    setEnterError(null);
    try {
      await onEnterTrade(setup.setup_id, entryPremium);
      setEntered(true);
      toast.success(
        `Position entered — ${setup.underlying} ${setup.strike} ${setup.option_type}`,
        `${fmtINR(entryPremium)} · ${setup.strategy.replace(/_/g, ' ')}`,
      );
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Entry failed — no position was created.';
      setEnterError(message);
      // Re-throw so the confirmation dialog surfaces the failure and stays open.
      throw err instanceof Error ? err : new Error(message);
    } finally {
      setEntering(false);
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 75) return 'text-up bg-up/10 border-up/30';
    if (score >= 60) return 'text-accent bg-accent/10 border-accent/30';
    if (score >= 45) return 'text-warn bg-warn/10 border-warn/30';
    return 'text-muted-foreground bg-muted/40 border-border';
  };

  const scoreTotal = Number.isFinite(setup.score?.total) ? setup.score.total : null;
  const scoreLabel = scoreTotal === null ? '—' : String(Math.round(scoreTotal));
  const scoreClass =
    scoreTotal === null ? 'text-muted-foreground bg-muted/40 border-border' : getScoreColor(scoreTotal);

  const getStateBadge = (state: string) => {
    switch (state) {
      case 'TRIGGERED':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-up/20 text-up border border-up/30">TRIGGERED</span>;
      case 'READY':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-accent/20 text-accent border border-accent/30">READY</span>;
      case 'ENTERED':
        // Informational, like READY: an open position is neither bullish news
        // nor a block.
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-accent/20 text-accent border border-accent/30">ACTIVE</span>;
      case 'BLOCKED':
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-down/20 text-down border border-down/30">BLOCKED</span>;
      default:
        return <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-muted text-muted-foreground border border-border">RADAR</span>;
    }
  };

  const isCall = setup.option_type === 'CE';
  const delta = setup.greeks?.delta ?? 0;
  const thetaDay = setup.greeks?.theta_day ?? 0;
  const vega = setup.greeks?.vega ?? 0;
  const ivPct = Number.isFinite(setup.iv) ? fmtNum(setup.iv * 100, 1) : null;
  const ivRank = Number.isFinite(setup.iv_percentile) ? fmtNum(setup.iv_percentile, 0) : null;
  const thetaDrag = Number.isFinite(setup.theta_drag_ratio) ? fmtNum(setup.theta_drag_ratio, 1) : '—';
  const validity = setup.trade_validity;
  const entryAllowed = setup.signal_state !== 'BLOCKED' && setup.trade_validity?.overall_valid !== false;

  return (
    <>
      <div className="flex flex-col rounded-md border border-border bg-card text-card-foreground overflow-hidden">
        {/* Card Header */}
        <div className="p-3 border-b border-border/60 bg-muted/20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[15px] font-semibold tracking-normal text-foreground num">{setup.underlying}</span>
                {setup.horizon === 'INTRADAY' ? (
                  <span className="chip chip--warn">
                    Intraday · {setup.timeframe || '15m'}
                  </span>
                ) : (
                  <span className="chip chip--info">
                    Positional · 1D
                  </span>
                )}
                <span className={`chip ${isCall ? 'chip--up' : 'chip--down'} num`}>
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
                {Number.isFinite(setup.vwap) && (
                  <>
                    <span>•</span>
                    <span className="font-mono text-primary/80">VWAP: {fmtINR(setup.vwap)}</span>
                  </>
                )}
              </div>
            </div>

            {/* Quality Score */}
            <div className="flex flex-col items-end shrink-0">
              <div className={`px-2.5 py-0.5 rounded-lg border font-mono font-bold text-sm ${scoreClass}`}>
                {scoreLabel}
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
                <span className={`flex items-center gap-1 font-mono ${validity.underlying_valid ? 'text-up' : 'text-down'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.underlying_valid ? 'bg-up' : 'bg-down'}`} />
                  Underlying
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.option_valid ? 'text-up' : 'text-down'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.option_valid ? 'bg-up' : 'bg-down'}`} />
                  Option
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.portfolio_valid ? 'text-up' : 'text-down'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.portfolio_valid ? 'bg-up' : 'bg-down'}`} />
                  Portfolio
                </span>
                <span className={`flex items-center gap-1 font-mono ${validity.execution_valid ? 'text-up' : 'text-down'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${validity.execution_valid ? 'bg-up' : 'bg-down'}`} />
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
              <div className="font-semibold text-foreground text-sm font-mono">{fmtINR(setup.entry_premium)}</div>
              <div className="text-[10px] text-muted-foreground">Spot: {fmtINR(setup.spot_price)}</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[10px] uppercase font-semibold">Option Stop</div>
              <div className="font-semibold text-destructive text-sm font-mono">{fmtINR(setup.stop_premium)}</div>
              <div className="text-[10px] text-destructive/80 font-mono">Spot Inv: {fmtINR(setup.spot_stop)}</div>
            </div>

            <div>
              <div className="text-muted-foreground text-[10px] uppercase font-semibold">Targets (1.5R / 3R)</div>
              <div className="font-semibold text-up text-sm font-mono">{fmtINR(setup.target_premium_1)}</div>
              <div className="text-[10px] text-up/80 font-mono">T2: {fmtINR(setup.target_premium_2)}</div>
            </div>
          </div>

          {/* Greeks & IV Telemetry Bar */}
          <div className="grid grid-cols-4 gap-1 p-2 rounded-lg bg-background border border-border/60 text-[11px] text-center font-mono">
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Delta (Δ)</span>
              <span className="font-semibold text-foreground">{fmtNum(delta)}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Theta (Θ/d)</span>
              <span className="font-semibold text-down">-{fmtINR(Math.abs(thetaDay))}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">Vega (ν)</span>
              <span className="font-semibold text-foreground">{fmtINR(vega)}</span>
            </div>
            <div>
              <span className="text-muted-foreground text-[9px] block uppercase font-sans">IV (Rank)</span>
              <span className="font-semibold text-accent">
                {ivPct === null ? '—' : `${ivPct}%`} ({ivRank === null ? '—' : `${ivRank}%`})
              </span>
            </div>
          </div>

          {/* Sizing & Risk per Lot */}
          <div className="flex items-center justify-between text-[11px] text-muted-foreground px-1">
            <div className="flex items-center gap-1">
              <Shield className="w-3.5 h-3.5 text-primary" />
              <span>Risk/Lot: <strong className="text-foreground font-mono">{fmtINR(setup.premium_risk_per_lot)}</strong></span>
            </div>
            <div className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-muted-foreground" />
              <span>Hold: <strong className="text-foreground">{setup.horizon === 'INTRADAY' ? 'Intraday (15:15)' : `${setup.expected_holding_days}d`}</strong></span>
            </div>
            <div className="flex items-center gap-1">
              <Activity className="w-3.5 h-3.5 text-warn" />
              <span>Theta Drag: <strong className="text-foreground font-mono">{thetaDrag}%</strong></span>
            </div>
          </div>

          {/* Confirmations List */}
          <div className="space-y-1 pt-1 border-t border-border/40">
            <div className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
              Thesis & Volatility Check
            </div>
            <div className="space-y-1 text-[11px] text-foreground/90">
              {(setup.technical_reasons ?? []).slice(0, 1).map((r, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-up shrink-0 mt-0.5" />
                  <span className="line-clamp-1">{r}</span>
                </div>
              ))}
              {(setup.options_reasons ?? []).slice(0, 1).map((r, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-accent shrink-0 mt-0.5" />
                  <span className="line-clamp-1">{r}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="pt-2 border-t border-border/50 flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowThesis(true)}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg border border-border bg-background hover:bg-muted text-foreground text-xs font-medium transition-colors"
              >
                <Bot className="w-3.5 h-3.5 text-primary" />
                <span>AI Thesis</span>
              </button>

              {entryAllowed ? (
                <button
                  onClick={() => setConfirmOpen(true)}
                  disabled={entering || entered || entryPremium === null}
                  className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-medium transition-colors disabled:opacity-50"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>
                    {entered
                      ? 'In Portfolio'
                      : entering
                        ? 'Entering...'
                        : entryPremium === null
                          ? 'Premium Unavailable'
                          : 'Enter Position'}
                  </span>
                </button>
              ) : (
                <div className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 rounded-lg bg-down/10 text-down text-[11px] font-medium border border-down/20">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Blocked by Risk Gate</span>
                </div>
              )}
            </div>

            {enterError && (
              <p role="alert" className="text-[11px] text-down font-mono">
                Entry failed: {enterError}
              </p>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirmEntry}
        title={`Enter ${setup.underlying} ${setup.strike} ${setup.option_type}`}
        confirmLabel="Enter Position"
        destructive={false}
        message={
          <div className="space-y-2">
            <p>
              Submit this long options swing position? The server revalidates the 4-layer gate
              and the portfolio risk ceiling on submission.
            </p>
            <div className="rounded-md border border-border bg-secondary/40 px-3 py-2 font-mono text-[11px]">
              <div className="flex justify-between gap-3 py-0.5">
                <span className="text-muted-foreground">Contract</span>
                <span className="text-foreground">{setup.contract_symbol}</span>
              </div>
              <div className="flex justify-between gap-3 py-0.5">
                <span className="text-muted-foreground">Entry premium</span>
                <span className="text-foreground">{fmtINR(entryPremium)}</span>
              </div>
              <div className="flex justify-between gap-3 py-0.5">
                <span className="text-muted-foreground">Option stop</span>
                <span className="text-foreground">{fmtINR(setup.stop_premium)}</span>
              </div>
              <div className="flex justify-between gap-3 py-0.5">
                <span className="text-muted-foreground">Targets</span>
                <span className="text-foreground">
                  {fmtINR(setup.target_premium_1)} / {fmtINR(setup.target_premium_2)}
                </span>
              </div>
              <div className="flex justify-between gap-3 py-0.5">
                <span className="text-muted-foreground">Risk per lot</span>
                <span className="text-foreground">{fmtINR(setup.premium_risk_per_lot)}</span>
              </div>
            </div>
          </div>
        }
      />

      <SwingAIThesisModal
        setup={setup}
        isOpen={showThesis}
        onClose={() => setShowThesis(false)}
      />
    </>
  );
}
