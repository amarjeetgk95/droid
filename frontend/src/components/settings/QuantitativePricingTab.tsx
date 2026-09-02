'use client';

import React, { useMemo } from 'react';
import { Sliders, Calculator, Percent, Coins, Info, CheckCircle2 } from 'lucide-react';
import { QuantitativeSettings } from '@/lib/settings';

interface Props {
  settings: QuantitativeSettings;
  onChange: (updated: Partial<QuantitativeSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function QuantitativePricingTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `quantitative.${field}`)?.message;
  // Live Cost Simulator — NSE statutory rates are fixed (auto-applied, not user-editable)
  const simulatedCost = useMemo(() => {
    const lotSize = 75;
    const buyPrice = 120;
    const sellPrice = 160;
    const buyTurnover = buyPrice * lotSize;
    const sellTurnover = sellPrice * lotSize;
    const totalTurnover = buyTurnover + sellTurnover;
    // Hardcoded NSE rates (removed from settings as unnecessary)
    const stt = (sellTurnover * 0.0625) / 100;
    const exchangeCharge = (totalTurnover * 0.05) / 100;
    const sebiCharge = (totalTurnover / 10000000) * 10;
    const stampDuty = (buyTurnover * 0.003) / 100;
    const brokerage = settings.brokeragePerOrder * 2;
    const gst = ((brokerage + exchangeCharge + sebiCharge) * 18) / 100;
    const totalCharges = stt + exchangeCharge + sebiCharge + stampDuty + brokerage + gst;
    const grossPnl = (sellPrice - buyPrice) * lotSize;
    const netPnl = grossPnl - totalCharges;
    return { stt, exchangeCharge, sebiCharge, stampDuty, brokerage, gst, totalCharges, grossPnl, netPnl, breakEvenPts: totalCharges / lotSize };
  }, [settings.brokeragePerOrder]);

  return (
    <div className="space-y-4">
      {/* 1. Quantitative Pricing Engine Parameters */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Sliders className="w-4 h-4 text-primary" />
            Option Pricing & Greeks Valuation Framework
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Configure the quantitative parameters used across Option Chain, Greeks calculations, Payoff curves, and Max Pain.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-1">
          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">
              Risk-Free Rate ($r$)
            </label>
            <div className="relative">
              <input
                type="number"
                step="0.0025"
                min="0.01"
                max="0.20"
                value={settings.riskFreeRate}
                onChange={(e) => onChange({ riskFreeRate: parseFloat(e.target.value) || 0.0675 })}
                className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono"
              />
              <span className="absolute right-3 top-2 text-xs text-muted-foreground font-mono">
                ({(settings.riskFreeRate * 100).toFixed(2)}%)
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Indian 91-day T-Bill Benchmark rate.
            </span>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">
              Time-to-Expiry Convention
            </label>
            <select
              value={settings.timeConvention}
              onChange={(e) => onChange({ timeConvention: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary"
            >
              <option value="ACT365">ACT/365 (NSE Standard Calendar)</option>
              <option value="ACT360">ACT/360 (Money Market Standard)</option>
              <option value="TradingDays252">Trading Days 252 (Business Day)</option>
            </select>
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Fractional year precision model.
            </span>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">
              Default Pricing Model
            </label>
            <select
              value={settings.defaultPricingModel}
              onChange={(e) => onChange({ defaultPricingModel: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary"
            >
              <option value="FUTURES_BLACK76">Black-76 (European Index Futures)</option>
              <option value="SPOT_BLACK_SCHOLES">Black-Scholes (Spot-Based Standard)</option>
            </select>
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Preferred analytical pricing kernel.
            </span>
          </div>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">
              Implied Volatility (IV) Solver
            </label>
            <select
              value={settings.ivMethod}
              onChange={(e) => onChange({ ivMethod: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary"
            >
              <option value="BRENT">Brent&apos;s Method (Guaranteed Convergence)</option>
              <option value="NEWTON_RAPHSON">Newton-Raphson (High Speed)</option>
            </select>
            <span className="text-[11px] text-muted-foreground mt-1 block">
              Root-finding solver for IV Smile curves.
            </span>
          </div>
        </div>
      </div>

      {/* 2. Transaction Cost (only user-editable fields) */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Percent className="w-4 h-4 text-primary" />
            Transaction Cost
          </h3>
          <p className="text-xs text-muted-foreground mt-1">Brokerage & slippage — statutory NSE charges (STT, SEBI, Stamp, GST) are auto-applied.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          <div>
            <label className="font-semibold text-foreground block mb-1">Brokerage Flat (₹/Order)</label>
            <input type="number" step="5" value={settings.brokeragePerOrder} onChange={(e) => onChange({ brokeragePerOrder: parseFloat(e.target.value) || 20 })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono" />
            <span className="text-[10px] text-muted-foreground mt-0.5 block">Standard discount broker: ₹20</span>
          </div>
          <div>
            <label className="font-semibold text-foreground block mb-1">Slippage (%)</label>
            <input type="number" step="0.01" value={settings.slippagePct} onChange={(e) => onChange({ slippagePct: parseFloat(e.target.value) || 0.05 })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono" />
            <span className="text-[10px] text-muted-foreground mt-0.5 block">Execution slippage buffer</span>
          </div>
        </div>
      </div>

      {/* 3. Live Cost Breakdown Simulator Card */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Calculator className="w-4 h-4 text-emerald-400" />
              Live Trade Cost Simulator (1-Lot NIFTY Option Round-Trip)
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Simulated 75 qty trade: Buy @ ₹120 $\rightarrow$ Sell @ ₹160 (Gross ₹3,000 profit)
            </p>
          </div>
          <span className="text-xs bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2.5 py-1 rounded-full font-mono font-semibold">
            Break-Even: +{simulatedCost.breakEvenPts.toFixed(2)} pts
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-6 gap-3 text-xs">
          <div className="bg-secondary/30 border border-border/50 rounded-lg p-2.5">
            <span className="text-muted-foreground text-[10px] block">Brokerage (Buy+Sell)</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{simulatedCost.brokerage.toFixed(2)}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-2.5">
            <span className="text-muted-foreground text-[10px] block">STT (Sell Side)</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{simulatedCost.stt.toFixed(2)}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-2.5">
            <span className="text-muted-foreground text-[10px] block">Exchange Turnover</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{simulatedCost.exchangeCharge.toFixed(2)}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-2.5">
            <span className="text-muted-foreground text-[10px] block">GST (18%)</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{simulatedCost.gst.toFixed(2)}
            </span>
          </div>

          <div className="bg-secondary/30 border border-border/50 rounded-lg p-2.5">
            <span className="text-muted-foreground text-[10px] block">Stamp Duty & SEBI</span>
            <span className="font-mono font-semibold text-foreground mt-0.5 block">
              ₹{(simulatedCost.stampDuty + simulatedCost.sebiCharge).toFixed(2)}
            </span>
          </div>

          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2.5">
            <span className="text-emerald-400 text-[10px] font-semibold block">Net Realized P&L</span>
            <span className="font-mono font-bold text-emerald-400 mt-0.5 block">
              ₹{simulatedCost.netPnl.toFixed(2)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
