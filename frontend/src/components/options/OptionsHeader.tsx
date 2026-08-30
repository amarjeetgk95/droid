'use client';

import { OptionsAnalytics } from '@/lib/types';
import { Target, Calendar, ShieldCheck } from 'lucide-react';

export function OptionsHeader({
  analytics,
  selectedSymbol,
  onSelectSymbol,
  selectedExpiry,
  expiries,
  onSelectExpiry,
  viewMode,
  onToggleViewMode,
}: {
  analytics: OptionsAnalytics | null;
  selectedSymbol: string;
  onSelectSymbol: (sym: string) => void;
  selectedExpiry: string;
  expiries: string[];
  onSelectExpiry: (exp: string) => void;
  viewMode: 'standard' | 'greeks';
  onToggleViewMode: (mode: 'standard' | 'greeks') => void;
}) {
  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-4 shadow-sm">
      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Symbol Selector */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => onSelectSymbol(sym)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                selectedSymbol === sym
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        {/* Expiry & View Controls */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs bg-secondary px-2.5 py-1 rounded-lg border border-border">
            <Calendar className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Expiry:</span>
            <select
              value={selectedExpiry}
              onChange={(e) => onSelectExpiry(e.target.value)}
              className="bg-transparent text-foreground font-semibold focus:outline-hidden cursor-pointer"
            >
              {expiries.map((exp) => (
                <option key={exp} value={exp} className="bg-card text-foreground">
                  {exp}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center bg-secondary p-0.5 rounded-lg border border-border text-xs">
            <button
              onClick={() => onToggleViewMode('standard')}
              className={`px-3 py-1 rounded-md font-medium transition-all cursor-pointer ${
                viewMode === 'standard' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground'
              }`}
            >
              Standard
            </button>
            <button
              onClick={() => onToggleViewMode('greeks')}
              className={`px-3 py-1 rounded-md font-medium transition-all cursor-pointer ${
                viewMode === 'greeks' ? 'bg-card text-foreground shadow-xs' : 'text-muted-foreground'
              }`}
            >
              Greeks (Δ, Γ, Θ, V)
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Spot LTP</span>
          <span className="text-base font-bold text-foreground font-mono">
            {analytics?.spot_price ? `₹${analytics.spot_price.toLocaleString('en-IN')}` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            Fut: ₹{analytics?.futures_price ? analytics.futures_price.toLocaleString('en-IN') : '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">ATM Strike</span>
          <span className="text-base font-bold text-primary font-mono">
            {analytics?.atm_strike ? analytics.atm_strike.toLocaleString('en-IN') : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            IV: {analytics?.atm_iv ? `${analytics.atm_iv}%` : '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">PCR (OI)</span>
          <span className={`text-base font-bold font-mono ${
            (analytics?.pcr_oi ?? 1) >= 1.2 ? 'text-success' : (analytics?.pcr_oi ?? 1) <= 0.8 ? 'text-destructive' : 'text-foreground'
          }`}>
            {analytics?.pcr_oi ?? '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">
            Vol PCR: {analytics?.pcr_volume ?? '---'}
          </span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Target className="w-3 h-3 text-warning" /> Max Pain
          </span>
          <span className="text-base font-bold text-warning font-mono">
            {analytics?.max_pain_strike ? analytics.max_pain_strike.toLocaleString('en-IN') : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">Least Option Payout</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground block">Days To Expiry</span>
          <span className="text-base font-bold text-foreground font-mono">
            {analytics?.time_to_expiry_days !== undefined ? `${analytics.time_to_expiry_days}d` : '---'}
          </span>
          <span className="text-[10px] text-muted-foreground block">ACT/365 Precision</span>
        </div>

        <div className="bg-secondary/60 p-3 rounded-lg border border-border">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldCheck className="w-3 h-3 text-primary" /> Risk-Free Rate
          </span>
          <span className="text-base font-bold text-foreground font-mono">
            {analytics?.risk_free_rate ? `${(analytics.risk_free_rate * 100).toFixed(2)}%` : '6.75%'}
          </span>
          <span className="text-[10px] text-muted-foreground block truncate" title={analytics?.rate_source}>
            IN Benchmark
          </span>
        </div>
      </div>
    </div>
  );
}
