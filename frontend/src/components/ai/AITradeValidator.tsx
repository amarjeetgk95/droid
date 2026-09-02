'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { AITradeValidationResponse } from '@/lib/types';
import { getStoredSettings } from '@/lib/settings';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  CheckCircle,
  XCircle,
  Clock,
  Sparkles,
  Zap,
  Target,
} from 'lucide-react';

interface AITradeValidatorProps {
  selectedSymbol: string;
}

export function AITradeValidator({ selectedSymbol }: AITradeValidatorProps) {
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [timeframe, setTimeframe] = useState<string>('15m');
  const [entryPrice, setEntryPrice] = useState<string>('24850');
  const [stopLoss, setStopLoss] = useState<string>('24780');
  const [targetPrice, setTargetPrice] = useState<string>('25050');
  const [thesisNotes, setThesisNotes] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AITradeValidationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Calculate live R:R
  const entry = parseFloat(entryPrice) || 0;
  const sl = parseFloat(stopLoss) || 0;
  const tgt = parseFloat(targetPrice) || 0;
  const risk = Math.abs(entry - sl);
  const reward = Math.abs(tgt - entry);
  const rrRatio = risk > 0 ? (reward / risk).toFixed(2) : '—';

  const handleValidate = async () => {
    if (!entry || !sl || !tgt) {
      setError('Please provide valid numbers for Entry, Stop Loss, and Target.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const settings = getStoredSettings();
      const res = await api.validateTradeSetup({
        symbol: selectedSymbol,
        direction,
        timeframe,
        entry_price: entry,
        stop_loss: sl,
        target_price: tgt,
        thesis_notes: thesisNotes || undefined,
        openrouter_api_key: settings.ai.openRouterApiKey || undefined,
        gemini_api_key: settings.ai.geminiApiKey || undefined,
      });
      setResult(res.data);
    } catch (err: any) {
      setError(err.message || 'Failed to validate trade setup.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Trade Parameters Form */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-foreground">Trade Thesis & Setup Auditor</h2>
              <p className="text-xs text-muted-foreground">
                Pre-flight risk validation checking setup against option walls, volume profile, and structural invalidations
              </p>
            </div>
          </div>
          <span className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-secondary text-primary border border-border">
            {selectedSymbol}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 pt-2">
          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Direction</label>
            <div className="flex rounded-lg border border-border p-0.5 bg-secondary/50">
              <button
                type="button"
                onClick={() => setDirection('BUY')}
                className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-all cursor-pointer flex items-center justify-center gap-1 ${
                  direction === 'BUY'
                    ? 'bg-emerald-600 text-white shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <TrendingUp className="w-3.5 h-3.5" />
                BUY
              </button>
              <button
                type="button"
                onClick={() => setDirection('SELL')}
                className={`flex-1 py-1.5 text-xs font-bold rounded-md transition-all cursor-pointer flex items-center justify-center gap-1 ${
                  direction === 'SELL'
                    ? 'bg-rose-600 text-white shadow-xs'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <TrendingDown className="w-3.5 h-3.5" />
                SELL
              </button>
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-medium cursor-pointer"
            >
              <option value="5m">5m (Intraday Scalp)</option>
              <option value="15m">15m (Primary Day Trade)</option>
              <option value="1h">1h (Hourly Swing)</option>
              <option value="1D">1D (Positional)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Entry Price (₹)</label>
            <input
              type="number"
              value={entryPrice}
              onChange={(e) => setEntryPrice(e.target.value)}
              placeholder="e.g. 24850"
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono font-medium focus:outline-hidden focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Stop Loss (₹)</label>
            <input
              type="number"
              value={stopLoss}
              onChange={(e) => setStopLoss(e.target.value)}
              placeholder="e.g. 24780"
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono font-medium text-rose-500 focus:outline-hidden focus:ring-1 focus:ring-rose-500"
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Target Price (₹)</label>
            <input
              type="number"
              value={targetPrice}
              onChange={(e) => setTargetPrice(e.target.value)}
              placeholder="e.g. 25050"
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono font-medium text-emerald-500 focus:outline-hidden focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-1">
          <div className="sm:col-span-3">
            <input
              type="text"
              value={thesisNotes}
              onChange={(e) => setThesisNotes(e.target.value)}
              placeholder="Optional: Enter reasoning (e.g. Breakout of 15m consolidation with put OI buildup)"
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-medium focus:outline-hidden focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60"
            />
          </div>

          <div className="flex items-center justify-between sm:justify-end gap-3">
            <div className="text-xs font-mono text-muted-foreground">
              R:R: <span className="font-bold text-foreground">1:{rrRatio}</span>
            </div>
            <button
              onClick={handleValidate}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 bg-primary text-primary-foreground font-semibold text-xs rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-all cursor-pointer shadow-xs"
            >
              {loading ? <Zap className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              Audit Trade Setup
            </button>
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-xl flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Validation Result Card */}
      {result && (
        <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-5 animate-in fade-in duration-300">
          {/* Header Verdict & Score */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border">
            <div className="flex items-center gap-3">
              <div
                className={`p-2.5 rounded-xl border text-white font-bold text-xs flex items-center gap-1.5 ${
                  result.decision === 'CONFIRM'
                    ? 'bg-emerald-600 border-emerald-500'
                    : result.decision === 'WATCH'
                    ? 'bg-amber-600 border-amber-500'
                    : 'bg-rose-600 border-rose-500'
                }`}
              >
                {result.decision === 'CONFIRM' ? (
                  <CheckCircle className="w-4 h-4" />
                ) : result.decision === 'WATCH' ? (
                  <Clock className="w-4 h-4" />
                ) : (
                  <XCircle className="w-4 h-4" />
                )}
                {result.decision}
              </div>

              <div>
                <h3 className="text-sm font-bold text-foreground">Quality Score: {result.score}/100</h3>
                <p className="text-xs text-muted-foreground">{result.executive_verdict}</p>
              </div>
            </div>

            <div className="flex items-center gap-3 text-xs">
              <div className="bg-secondary/40 px-3 py-1.5 rounded-lg border border-border">
                <span className="text-muted-foreground text-[11px] block">Calculated R:R</span>
                <span className="font-bold font-mono text-sm">1:{result.risk_reward_calculated}</span>
              </div>
            </div>
          </div>

          {/* 3 Alignment Breakdown Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="bg-secondary/30 p-3.5 rounded-xl border border-border space-y-1.5">
              <div className="font-bold text-foreground flex items-center gap-1.5">
                <Target className="w-3.5 h-3.5 text-primary" />
                Technical Alignment
              </div>
              <p className="text-muted-foreground leading-relaxed">{result.technical_alignment}</p>
            </div>

            <div className="bg-secondary/30 p-3.5 rounded-xl border border-border space-y-1.5">
              <div className="font-bold text-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                Derivatives & OI Walls
              </div>
              <p className="text-muted-foreground leading-relaxed">{result.derivatives_alignment}</p>
            </div>

            <div className="bg-secondary/30 p-3.5 rounded-xl border border-border space-y-1.5">
              <div className="font-bold text-foreground flex items-center gap-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-primary" />
                Volatility Regime Check
              </div>
              <p className="text-muted-foreground leading-relaxed">{result.volatility_regime_check}</p>
            </div>
          </div>

          {/* Invalidation Conditions */}
          {result.invalidation_conditions.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Invalidation Conditions (Strict Stop Triggers)</h4>
              <ul className="space-y-1 text-xs text-muted-foreground bg-secondary/20 p-3 rounded-lg border border-border list-disc list-inside">
                {result.invalidation_conditions.map((inv, idx) => (
                  <li key={idx}><span className="text-foreground font-medium">{inv}</span></li>
                ))}
              </ul>
            </div>
          )}

          {/* Warning Traps */}
          {result.warning_traps.length > 0 && (
            <div className="p-3.5 bg-rose-500/10 border border-rose-500/20 rounded-xl text-xs flex items-start gap-2.5 text-rose-700 dark:text-rose-400">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Detected Warning Traps:</span>
                <ul className="mt-1 list-disc list-inside space-y-0.5">
                  {result.warning_traps.map((trap, i) => (
                    <li key={i}>{trap}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
