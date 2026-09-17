'use client';

import React, { useMemo, useState, useEffect } from 'react';
import { Sliders, Calculator, Percent } from 'lucide-react';
import { QuantitativeSettings } from '@/lib/settings';
import {
  SettingSection,
  SettingRow,
  SettingInput,
  SettingSelect,
  StatTile,
} from './ui/SettingPrimitives';

interface Props {
  settings: QuantitativeSettings;
  onChange: (updated: Partial<QuantitativeSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function QuantitativePricingTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `quantitative.${field}`)?.message;

  // Raw drafts — invalid text stays visible and propagates NaN so zod blocks
  // the save instead of silently snapping to a default.
  const [riskDraft, setRiskDraft] = useState(() => String(settings.riskFreeRate));
  const [brokerageDraft, setBrokerageDraft] = useState(() => String(settings.brokeragePerOrder));
  const [slippageDraft, setSlippageDraft] = useState(() => String(settings.slippagePct));

  useEffect(() => {
    if (Number.isFinite(settings.riskFreeRate)) setRiskDraft(String(settings.riskFreeRate));
  }, [settings.riskFreeRate]);
  useEffect(() => {
    if (Number.isFinite(settings.brokeragePerOrder)) setBrokerageDraft(String(settings.brokeragePerOrder));
  }, [settings.brokeragePerOrder]);
  useEffect(() => {
    if (Number.isFinite(settings.slippagePct)) setSlippageDraft(String(settings.slippagePct));
  }, [settings.slippagePct]);

  const handleRiskChange = (raw: string) => {
    setRiskDraft(raw);
    onChange({ riskFreeRate: raw.trim() === '' ? NaN : Number(raw) });
  };
  const handleBrokerageChange = (raw: string) => {
    setBrokerageDraft(raw);
    onChange({ brokeragePerOrder: raw.trim() === '' ? NaN : Number(raw) });
  };
  const handleSlippageChange = (raw: string) => {
    setSlippageDraft(raw);
    onChange({ slippagePct: raw.trim() === '' ? NaN : Number(raw) });
  };

  const riskPercentDisplay = Number.isFinite(settings.riskFreeRate)
    ? `(${(settings.riskFreeRate * 100).toFixed(2)}%)`
    : '(invalid — fix to save)';

  // Live Cost Simulator — NSE statutory rates are fixed (auto-applied).
  // Returns null when brokerage is invalid so nothing is fabricated.
  const simulatedCost = useMemo(() => {
    if (!Number.isFinite(settings.brokeragePerOrder) || settings.brokeragePerOrder < 0) return null;

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
    const brokerage = settings.brokeragePerOrder * 2;
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
    <div className="space-y-4">
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
          htmlFor="quant-risk-free"
        >
          <div className="flex items-center gap-2">
            <SettingInput
              id="quant-risk-free"
              type="number"
              step="0.0025"
              min="0"
              max="1"
              mono
              value={riskDraft}
              onChange={(e) => handleRiskChange(e.target.value)}
            />
            <span className="text-xs font-mono text-muted-foreground w-28">
              {riskPercentDisplay}
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
          htmlFor="quant-brokerage"
        >
          <SettingInput
            id="quant-brokerage"
            type="number"
            step="5"
            min="0"
            mono
            value={brokerageDraft}
            onChange={(e) => handleBrokerageChange(e.target.value)}
          />
        </SettingRow>

        <SettingRow
          label="Estimated Slippage Buffer (%)"
          description="Assumed execution slippage applied to backtests and paper orders."
          error={getError('slippagePct')}
          htmlFor="quant-slippage"
        >
          <SettingInput
            id="quant-slippage"
            type="number"
            step="0.01"
            min="0"
            max="10"
            mono
            value={slippageDraft}
            onChange={(e) => handleSlippageChange(e.target.value)}
          />
        </SettingRow>
      </SettingSection>

      {/* 3. Live Cost Breakdown Simulator */}
      <SettingSection
        title="Round-Trip Cost Breakdown"
        description="Simulated 1-lot NIFTY option trade (75 qty @ ₹120 buy, ₹160 sell, ₹3,000 gross P&L)."
        icon={Calculator}
        action={
          simulatedCost ? (
            <span className="badge b-info font-mono" style={{ fontSize: '11px' }}>
              Break-even: +{simulatedCost.breakEvenPts.toFixed(2)} pts
            </span>
          ) : (
            <span className="badge b-warn" style={{ fontSize: '11px' }}>
              Brokerage invalid — fix to simulate
            </span>
          )
        }
      >
        <div className="card-pad">
          {simulatedCost ? (
            <div className="stat-grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
              <StatTile label="Brokerage" value={`₹${simulatedCost.brokerage.toFixed(2)}`} />
              <StatTile label="STT (Sell)" value={`₹${simulatedCost.stt.toFixed(2)}`} />
              <StatTile label="Exchange" value={`₹${simulatedCost.exchangeCharge.toFixed(2)}`} />
              <StatTile label="GST (18%)" value={`₹${simulatedCost.gst.toFixed(2)}`} />
              <StatTile label="SEBI & Stamp" value={`₹${(simulatedCost.stampDuty + simulatedCost.sebiCharge).toFixed(2)}`} />
              <StatTile
                label="Net realized"
                value={`₹${simulatedCost.netPnl.toFixed(2)}`}
                tone={simulatedCost.netPnl >= 0 ? 'positive' : 'negative'}
              />
            </div>
          ) : (
            <p className="text-xs text-[var(--ds-warn-strong)]">
              Enter a valid non-negative brokerage to compute the round-trip cost breakdown.
            </p>
          )}
        </div>
      </SettingSection>
    </div>
  );
}
