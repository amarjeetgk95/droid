'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { AIOptionsStrategyRecommendation } from '@/lib/types';
import { getStoredSettings } from '@/lib/settings';
import {
  Layers,
  TrendingUp,
  ShieldAlert,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Play,
  Copy,
  Check,
  Zap,
  Sparkles,
  BarChart2,
} from 'lucide-react';

interface AIOptionsArchitectProps {
  selectedSymbol: string;
}

export function AIOptionsArchitect({ selectedSymbol }: AIOptionsArchitectProps) {
  const [outlook, setOutlook] = useState<'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'DIRECTIONAL_RANGE'>('BULLISH');
  const [riskTolerance, setRiskTolerance] = useState<'LOW' | 'MODERATE' | 'AGGRESSIVE'>('MODERATE');
  const [customPrompt, setCustomPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [recommendation, setRecommendation] = useState<AIOptionsStrategyRecommendation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const settings = getStoredSettings();
      const res = await api.recommendOptionsStrategy({
        symbol: selectedSymbol,
        outlook,
        max_risk_tolerance: riskTolerance,
        custom_query: customPrompt || undefined,
        openrouter_api_key: settings.ai.openRouterApiKey || undefined,
        gemini_api_key: settings.ai.geminiApiKey || undefined,
      });
      setRecommendation(res.data);
    } catch (err: any) {
      setError(err.message || 'Failed to structure options strategy.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!recommendation) return;
    const text = `${recommendation.strategy_name} (${recommendation.symbol})\n` +
      `Outlook: ${recommendation.market_outlook}\n` +
      `Legs:\n` +
      recommendation.legs.map(l => `  - ${l.action} ${selectedSymbol} ₹${l.strike} ${l.option_type} @ ~₹${l.estimated_premium}`).join('\n') +
      `\nMax Profit: ${recommendation.max_profit_pts} | Max Loss: ${recommendation.max_loss_pts} | R:R: ${recommendation.risk_reward_ratio}\n` +
      `Breakevens: ${recommendation.breakevens.join(', ')}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4">
      {/* Configuration Controls Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-primary/10 rounded-lg text-primary">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-foreground">Options Strategy Architect</h2>
              <p className="text-xs text-muted-foreground">
                AI derivatives engine structuring risk-defined option spreads aligned with current IV & S/R walls
              </p>
            </div>
          </div>
          <span className="text-xs font-mono font-bold px-2.5 py-1 rounded bg-secondary text-primary border border-border">
            {selectedSymbol}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
          <div>
            <label className="text-xs font-semibold text-foreground block mb-1.5">Market Outlook</label>
            <select
              value={outlook}
              onChange={(e) => setOutlook(e.target.value as any)}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-medium cursor-pointer focus:outline-hidden focus:ring-1 focus:ring-primary"
            >
              <option value="BULLISH">Bullish (Expect upward move)</option>
              <option value="BEARISH">Bearish (Expect downward move)</option>
              <option value="NEUTRAL">Neutral / Range-Bound (Theta decay)</option>
              <option value="HIGH_VOLATILITY">High Volatility (Long Gamma breakout)</option>
              <option value="LOW_VOLATILITY">Low Volatility (IV crush premium selling)</option>
              <option value="DIRECTIONAL_RANGE">Directional Range (Bullish / Bearish Put/Call spread)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1.5">Risk Tolerance</label>
            <select
              value={riskTolerance}
              onChange={(e) => setRiskTolerance(e.target.value as any)}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-medium cursor-pointer focus:outline-hidden focus:ring-1 focus:ring-primary"
            >
              <option value="LOW">Low (Strictly Defined Spreads / Low Margin)</option>
              <option value="MODERATE">Moderate (Standard 1:2 R:R Spreads & Condors)</option>
              <option value="AGGRESSIVE">Aggressive (Ratio Spreads / Asymmetric Skew)</option>
            </select>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1.5">Custom Thesis / Constraints</label>
            <input
              type="text"
              value={customPrompt}
              onChange={(e) => setCustomPrompt(e.target.value)}
              placeholder="e.g. Protect against RBI policy gap down"
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-medium focus:outline-hidden focus:ring-1 focus:ring-primary placeholder:text-muted-foreground/60"
            />
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground font-semibold text-xs rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-all cursor-pointer shadow-xs"
          >
            {loading ? (
              <>
                <Zap className="w-4 h-4 animate-spin" />
                Structuring Optimal Legs...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Structure Options Strategy
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 text-destructive text-xs rounded-xl flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Strategy Recommendation Card */}
      {recommendation && (
        <div className="bg-card border border-border rounded-xl p-5 shadow-xs space-y-5 animate-in fade-in duration-300">
          {/* Header & Metrics Overview */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-border">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-foreground">{recommendation.strategy_name}</h3>
                <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 font-semibold border border-emerald-500/20">
                  {recommendation.risk_reward_ratio} R:R
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">{recommendation.market_outlook}</p>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-foreground text-xs font-medium rounded-lg hover:bg-secondary/80 border border-border cursor-pointer transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied!' : 'Copy Structure'}
              </button>
            </div>
          </div>

          {/* Quick Metrics Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="bg-secondary/40 p-3 rounded-lg border border-border">
              <div className="text-muted-foreground text-[11px]">Max Profit</div>
              <div className="font-bold text-sm text-emerald-600 dark:text-emerald-400">{recommendation.max_profit_pts}</div>
            </div>
            <div className="bg-secondary/40 p-3 rounded-lg border border-border">
              <div className="text-muted-foreground text-[11px]">Max Loss</div>
              <div className="font-bold text-sm text-rose-600 dark:text-rose-400">{recommendation.max_loss_pts}</div>
            </div>
            <div className="bg-secondary/40 p-3 rounded-lg border border-border">
              <div className="text-muted-foreground text-[11px]">Net Premium Points</div>
              <div className="font-bold text-sm font-mono">
                {recommendation.net_debit_credit_pts > 0 ? `+${recommendation.net_debit_credit_pts} (Credit)` : `${recommendation.net_debit_credit_pts} (Debit)`}
              </div>
            </div>
            <div className="bg-secondary/40 p-3 rounded-lg border border-border">
              <div className="text-muted-foreground text-[11px]">Net Greeks Exposure</div>
              <div className="font-mono text-xs font-semibold">
                Δ {recommendation.net_delta > 0 ? `+${recommendation.net_delta}` : recommendation.net_delta} • θ +{recommendation.net_theta}/day
              </div>
            </div>
          </div>

          {/* Breakeven Banner */}
          {recommendation.breakevens.length > 0 && (
            <div className="px-3.5 py-2 bg-secondary/30 rounded-lg border border-border text-xs flex items-center justify-between">
              <span className="text-muted-foreground">Estimated Expiry Breakeven Points:</span>
              <span className="font-mono font-bold text-foreground">
                {recommendation.breakevens.map(b => `₹${b}`).join(' | ')}
              </span>
            </div>
          )}

          {/* Strategy Legs Ladder Table */}
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Strategy Legs Structure</h4>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-xs text-left">
                <thead className="bg-secondary/60 text-muted-foreground font-semibold border-b border-border">
                  <tr>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-3 py-2">Strike</th>
                    <th className="px-3 py-2">Option Type</th>
                    <th className="px-3 py-2">Est. Premium</th>
                    <th className="px-3 py-2">Delta</th>
                    <th className="px-3 py-2">Theta</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {recommendation.legs.map((leg, i) => (
                    <tr key={i} className="hover:bg-secondary/20 transition-colors">
                      <td className="px-3 py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            leg.action === 'BUY'
                              ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-600 border border-rose-500/20'
                          }`}
                        >
                          {leg.action}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-bold font-mono">₹{leg.strike}</td>
                      <td className="px-3 py-2.5 font-semibold">
                        <span className={leg.option_type === 'CE' ? 'text-blue-500' : 'text-amber-500'}>
                          {leg.option_type}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono">~₹{leg.estimated_premium}</td>
                      <td className="px-3 py-2.5 font-mono text-muted-foreground">{leg.delta ?? '—'}</td>
                      <td className="px-3 py-2.5 font-mono text-muted-foreground">{leg.theta ? `${leg.theta}/day` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Rationale & Rules */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-1">
            <div className="bg-secondary/20 p-4 rounded-xl border border-border/80 space-y-2">
              <h5 className="font-bold text-foreground flex items-center gap-1.5">
                <BarChart2 className="w-4 h-4 text-primary" />
                Institutional Rationale
              </h5>
              <p className="text-muted-foreground leading-relaxed">{recommendation.rationale}</p>
            </div>

            <div className="bg-secondary/20 p-4 rounded-xl border border-border/80 space-y-2">
              <h5 className="font-bold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                Execution & Exit Playbook
              </h5>
              <ul className="space-y-1 text-muted-foreground list-disc list-inside">
                {recommendation.entry_rules.map((r, i) => (
                  <li key={`entry-${i}`}><span className="font-semibold text-foreground">Entry:</span> {r}</li>
                ))}
                {recommendation.exit_rules.map((r, i) => (
                  <li key={`exit-${i}`}><span className="font-semibold text-foreground">Exit:</span> {r}</li>
                ))}
              </ul>
            </div>
          </div>

          {/* Risk Management Banner */}
          {recommendation.risk_management && (
            <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs flex items-start gap-2.5 text-amber-700 dark:text-amber-400">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold">Risk Management Directive:</span> {recommendation.risk_management}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
