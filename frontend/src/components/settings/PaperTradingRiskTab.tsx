'use client';

import React, { useState, useEffect } from 'react';
import { FileText, Coins, ShieldCheck, AlertTriangle, RefreshCw, CheckCircle2, AlertCircle, Clock, PieChart } from 'lucide-react';
import { PaperTradingSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { PortfolioSummary } from '@/lib/types';

interface Props {
  settings: PaperTradingSettings;
  onChange: (updated: Partial<PaperTradingSettings>) => void;
}

export function PaperTradingRiskTab({ settings, onChange }: Props) {
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchPortfolio = async () => {
    setLoading(true);
    try {
      const res = await api.getPaperPortfolio();
      setPortfolio(res.data);
    } catch {
      // Fallback
      setPortfolio({
        virtual_capital: settings.initialCapital,
        available_margin: settings.initialCapital,
        used_margin: 0,
        margin_utilization_pct: 0,
        total_realized_pnl: 0,
        total_unrealized_pnl: 0,
        total_portfolio_pnl: 0,
        open_positions_count: 0,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPortfolio();
  }, []);

  const handleResetAccount = async () => {
    if (!confirm('Are you sure you want to reset your virtual paper trading account? This will square off all active positions and restore starting capital.')) {
      return;
    }

    setResetting(true);
    setMsg(null);
    try {
      const res = await api.resetPaperAccount();
      setPortfolio(res.data);
      setMsg({
        type: 'success',
        text: 'Paper trading account successfully reset to default initial capital.',
      });
    } catch (err: any) {
      setMsg({
        type: 'error',
        text: err?.message || 'Failed to reset paper account',
      });
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-6">
      {msg && (
        <div
          className={`p-3.5 rounded-xl text-xs flex items-center gap-2 ${
            msg.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{msg.text}</span>
        </div>
      )}

      {/* 1. Live Virtual Account Telemetry Card */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Coins className="w-4 h-4 text-emerald-400" />
              Live Virtual Portfolio & Capital Status
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Simulated capital allocation and real-time margin utilization.
            </p>
          </div>
          <button
            type="button"
            onClick={handleResetAccount}
            disabled={resetting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/20 rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
            <span>Reset Virtual Capital</span>
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Virtual Capital</span>
            <span className="font-mono font-bold text-foreground text-base mt-0.5 block">
              ₹{(portfolio?.virtual_capital ?? settings.initialCapital).toLocaleString('en-IN')}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Available Margin</span>
            <span className="font-mono font-semibold text-emerald-400 mt-0.5 block">
              ₹{(portfolio?.available_margin ?? settings.initialCapital).toLocaleString('en-IN')}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Margin Used</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{(portfolio?.used_margin ?? 0).toLocaleString('en-IN')} ({portfolio?.margin_utilization_pct ?? 0}%)
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3">
            <span className="text-muted-foreground text-[11px] block">Total Realized P&L</span>
            <span
              className={`font-mono font-bold mt-0.5 block ${
                (portfolio?.total_realized_pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-destructive'
              }`}
            >
              {(portfolio?.total_realized_pnl ?? 0) >= 0 ? '+' : ''}₹{(portfolio?.total_realized_pnl ?? 0).toLocaleString('en-IN')}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Capital & Risk Allocation Parameters */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-primary" />
            Virtual Execution & Risk Safeguard Parameters
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Enforce trading guardrails, position size limits, and intraday square-off rules for virtual orders.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs pt-1">
          <div>
            <label className="font-semibold text-foreground block mb-1">
              Default Initial Capital (₹)
            </label>
            <select
              value={settings.initialCapital}
              onChange={(e) => onChange({ initialCapital: Number(e.target.value) })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden"
            >
              <option value={500000}>₹5,00,000 (5 Lakhs)</option>
              <option value={1000000}>₹10,00,000 (10 Lakhs - Standard)</option>
              <option value={2500000}>₹25,00,000 (25 Lakhs)</option>
              <option value={5000000}>₹50,00,000 (50 Lakhs - HNI)</option>
              <option value={10000000}>₹1,00,00,000 (1 Crore - Institutional)</option>
            </select>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Intraday Auto Square-off Time
            </label>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={settings.autoSquareOffTime}
                onChange={(e) => onChange({ autoSquareOffTime: e.target.value })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono"
              />
              <span className="text-muted-foreground shrink-0 font-mono text-[11px]">IST</span>
            </div>
            <span className="text-[10px] text-muted-foreground mt-1 block">
              Default NSE intraday MIS cutoff (15:20)
            </span>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Max Capital Per Trade (%)
            </label>
            <div className="relative">
              <input
                type="number"
                min="5"
                max="100"
                value={settings.maxCapitalPerTradePct}
                onChange={(e) => onChange({ maxCapitalPerTradePct: Number(e.target.value) || 20 })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono"
              />
              <span className="absolute right-3 top-2 text-muted-foreground">%</span>
            </div>
            <span className="text-[10px] text-muted-foreground mt-1 block">
              Single trade exposure cap
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 text-xs">
          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3 flex items-center justify-between">
            <div>
              <span className="font-semibold text-foreground block">Order Execution Confirmation</span>
              <span className="text-[11px] text-muted-foreground">Show preview modal before placing virtual orders</span>
            </div>
            <input
              type="checkbox"
              checked={settings.requireOrderConfirm}
              onChange={(e) => onChange({ requireOrderConfirm: e.target.checked })}
              className="w-4 h-4 rounded text-primary accent-primary cursor-pointer"
            />
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-3 flex items-center justify-between">
            <div>
              <span className="font-semibold text-foreground block">Allow Overnight / NRML Positions</span>
              <span className="text-[11px] text-muted-foreground">Enable carryforward options & futures contracts</span>
            </div>
            <input
              type="checkbox"
              checked={settings.allowOvernightPositions}
              onChange={(e) => onChange({ allowOvernightPositions: e.target.checked })}
              className="w-4 h-4 rounded text-primary accent-primary cursor-pointer"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
