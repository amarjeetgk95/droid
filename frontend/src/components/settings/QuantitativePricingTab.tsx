'use client';

import React, { useMemo } from 'react';
import { Sliders, Calculator, Percent } from 'lucide-react';
import { QuantitativeSettings } from '@/lib/settings';
import {
  SettingSection,
  SettingRow,
  SettingInput,
  SettingSelect,
} from './ui/SettingPrimitives';

interface Props {
  settings: QuantitativeSettings;
  onChange: (updated: Partial<QuantitativeSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function QuantitativePricingTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `quantitative.${field}`)?.message;

  // Live Cost Simulator — NSE statutory rates are fixed (auto-applied)
  const simulatedCost = useMemo(() => {
    const lotSize = 75;
    const buyPrice = 120;
    const sellPrice = 160;
    const buyTurnover = buyPrice * lotSize;
    const sellTurnover = sellPrice * lotSize;
    const totalTurnover = buyTurnover + sellTurnover;

    const stt = (sellTurnover * 0.0625) / 100;
    const exchangeCharge = (totalTurnover * 0.05) / 100;
    const sebiCharge = (totalTurnover / 10000000) * 10;
    const stampDuty = (buyTurnover * 0.003) / 100;
    const brokerage = (settings.brokeragePerOrder || 20) * 2;
    const gst = ((brokerage + exchangeCharge + sebiCharge) * 18) / 100;
    const totalCharges = stt + exchangeCharge + sebiCharge + stampDuty + brokerage + gst;
    const grossPnl = (sellPrice - buyPrice) * lotSize;
    const netPnl = grossPnl - totalCharges;

    return {
      stt,
      exchangeCharge,
      sebiCharge,
      stampDuty,
      brokerage,
      gst,
      totalCharges,
      grossPnl,
      netPnl,
      breakEvenPts: totalCharges / lotSize,
    };
  }, [settings.brokeragePerOrder]);

  return (
    <div className="space-y-6">
      {/* 1. Quantitative Pricing Engine Parameters */}
      <SettingSection
        title="Option Pricing & Greeks Kernel"
        description="Configure analytical pricing kernels, volatility root-finding solvers, and baseline risk-free rates."
        icon={Sliders}
      >
        <SettingRow
          label="Risk-Free Rate (r)"
          description="Baseline risk-free yield curve based on Indian 91-day T-Bills."
          error={getError('riskFreeRate')}
        >
          <div className="flex items-center gap-2">
            <SettingInput
              type="number"
              step="0.0025"
              min="0.01"
              max="0.20"
              mono
              value={settings.riskFreeRate}
              onChange={(e) => onChange({ riskFreeRate: parseFloat(e.target.value) || 0.0675 })}
            />
            <span className="text-xs font-mono text-muted-foreground w-14">
              ({((settings.riskFreeRate || 0) * 100).toFixed(2)}%)
            </span>
          </div>
        </SettingRow>

        <SettingRow
          label="Time-to-Expiry Convention"
          description="Day-count convention used to calculate fractional calendar years to expiration."
          error={getError('timeConvention')}
        >
          <SettingSelect
            value={settings.timeConvention}
            onChange={(e) => onChange({ timeConvention: e.target.value as any })}
          >
            <option value="ACT365">ACT/365 (NSE Standard Calendar)</option>
            <option value="ACT360">ACT/360 (Money Market Standard)</option>
            <option value="TradingDays252">Trading Days 252 (Business Day Basis)</option>
          </SettingSelect>
        </SettingRow>

        <SettingRow
          label="Analytical Pricing Model"
          description="Mathematical framework for option greeks, theoretical value, and payoff curves."
          error={getError('defaultPricingModel')}
        >
          <SettingSelect
            value={settings.defaultPricingModel}
            onChange={(e) => onChange({ defaultPricingModel: e.target.value as any })}
          >
            <option value="FUTURES_BLACK76">Black-76 (European Index Futures)</option>
            <option value="SPOT_BLACK_SCHOLES">Black-Scholes (Spot-Based Standard)</option>
          </SettingSelect>
        </SettingRow>

        <SettingRow
          label="Implied Volatility (IV) Solver"
          description="Numerical root-finding algorithm to compute strike implied volatility."
          error={getError('ivMethod')}
        >
          <SettingSelect
            value={settings.ivMethod}
            onChange={(e) => onChange({ ivMethod: e.target.value as any })}
          >
            <option value="BRENT">Brent&apos;s Method (Robust &amp; Guaranteed)</option>
            <option value="NEWTON_RAPHSON">Newton-Raphson (High Speed)</option>
          </SettingSelect>
        </SettingRow>
      </SettingSection>

      {/* 2. Execution Friction & Charges */}
      <SettingSection
        title="Transaction Friction & Commission"
        description="Brokerage rates and estimated market slippage. Statutory NSE taxes are calculated automatically."
        icon={Percent}
      >
        <SettingRow
          label="Flat Brokerage (₹ / Order)"
          description="Commission charged by your execution broker per executed leg."
          error={getError('brokeragePerOrder')}
        >
          <SettingInput
            type="number"
            step="5"
            min="0"
            mono
            value={settings.brokeragePerOrder}
            onChange={(e) => onChange({ brokeragePerOrder: parseFloat(e.target.value) || 0 })}
          />
        </SettingRow>

        <SettingRow
          label="Estimated Slippage Buffer (%)"
          description="Assumed execution slippage applied to backtests and paper orders."
          error={getError('slippagePct')}
        >
          <SettingInput
            type="number"
            step="0.01"
            min="0"
            max="5"
            mono
            value={settings.slippagePct}
            onChange={(e) => onChange({ slippagePct: parseFloat(e.target.value) || 0 })}
          />
        </SettingRow>
      </SettingSection>

      {/* 3. Live Cost Breakdown Simulator */}
      <SettingSection
        title="Live Round-Trip Cost Estimator"
        description="Simulated 1-lot NIFTY option trade (75 qty @ ₹120 buy, ₹160 sell, ₹3,000 gross P&L)."
        icon={Calculator}
        action={
          <span className="text-xs px-2.5 py-1 rounded-md bg-secondary/80 border border-border/60 font-mono text-muted-foreground">
            Break-even: <strong className="text-foreground">+{simulatedCost.breakEvenPts.toFixed(2)} pts</strong>
          </span>
        }
      >
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Brokerage
              </span>
              <span className="font-mono font-semibold text-sm text-foreground mt-1 block">
                ₹{simulatedCost.brokerage.toFixed(2)}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                STT (Sell)
              </span>
              <span className="font-mono font-semibold text-sm text-foreground mt-1 block">
                ₹{simulatedCost.stt.toFixed(2)}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Exchange Turn.
              </span>
              <span className="font-mono font-semibold text-sm text-foreground mt-1 block">
                ₹{simulatedCost.exchangeCharge.toFixed(2)}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                GST (18%)
              </span>
              <span className="font-mono font-semibold text-sm text-foreground mt-1 block">
                ₹{simulatedCost.gst.toFixed(2)}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                SEBI &amp; Stamp
              </span>
              <span className="font-mono font-semibold text-sm text-foreground mt-1 block">
                ₹{(simulatedCost.stampDuty + simulatedCost.sebiCharge).toFixed(2)}
              </span>
            </div>

            <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-3">
              <span className="text-emerald-700 text-[10px] uppercase font-medium tracking-wide block">
                Net Realized
              </span>
              <span className="font-mono font-bold text-sm text-emerald-600 mt-1 block">
                ₹{simulatedCost.netPnl.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      </SettingSection>
    </div>
  );
}
