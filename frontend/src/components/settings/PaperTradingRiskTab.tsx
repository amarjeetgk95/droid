'use client';

import React, { useState, useEffect } from 'react';
import { ShieldCheck, RefreshCw, CheckCircle2, AlertCircle, Wallet } from 'lucide-react';
import { PaperTradingSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { PortfolioSummary } from '@/lib/types';
import {
  SettingSection,
  SettingRow,
  SettingInput,
  SettingSelect,
  SettingSwitch,
} from './ui/SettingPrimitives';

interface Props {
  settings: PaperTradingSettings;
  onChange: (updated: Partial<PaperTradingSettings>) => void;
  errors?: { path: string; message: string }[];
}

export function PaperTradingRiskTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `paper.${field}`)?.message;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleResetAccount = async () => {
    if (
      !confirm(
        'Are you sure you want to reset your virtual paper trading account? This will square off all active positions and restore starting capital.'
      )
    ) {
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

  const virtualCapital = portfolio?.virtual_capital ?? settings.initialCapital;
  const availableMargin = portfolio?.available_margin ?? settings.initialCapital;
  const usedMargin = portfolio?.used_margin ?? 0;
  const realizedPnl = portfolio?.total_realized_pnl ?? 0;

  return (
    <div className="space-y-6">
      {msg && (
        <div
          className={`px-4 py-3 rounded-lg text-xs flex items-center gap-2.5 transition-all ${
            msg.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{msg.text}</span>
          <button
            type="button"
            onClick={() => setMsg(null)}
            className="ml-auto text-muted-foreground hover:text-foreground text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Account Summary & Status */}
      <SettingSection
        title="Virtual Portfolio & Capital"
        description="Real-time simulated capital allocation, available intraday margin, and net cumulative P&L."
        icon={Wallet}
        action={
          <button
            type="button"
            onClick={handleResetAccount}
            disabled={resetting}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 rounded-md text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-muted-foreground ${resetting ? 'animate-spin' : ''}`} />
            <span>Reset Account</span>
          </button>
        }
      >
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Virtual Capital
              </span>
              <span className="font-mono font-bold text-base text-foreground mt-1 block">
                ₹{virtualCapital.toLocaleString('en-IN')}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Available Margin
              </span>
              <span className="font-mono font-semibold text-base text-emerald-600 mt-1 block">
                ₹{availableMargin.toLocaleString('en-IN')}
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Margin Utilized
              </span>
              <span className="font-mono font-semibold text-base text-foreground mt-1 block">
                ₹{usedMargin.toLocaleString('en-IN')}{' '}
                <span className="text-xs font-normal text-muted-foreground">
                  ({portfolio?.margin_utilization_pct ?? 0}%)
                </span>
              </span>
            </div>

            <div className="bg-secondary/30 border border-border/40 rounded-lg p-3">
              <span className="text-muted-foreground text-[10px] uppercase font-medium tracking-wide block">
                Realized P&amp;L
              </span>
              <span
                className={`font-mono font-bold text-base mt-1 block ${
                  realizedPnl >= 0 ? 'text-emerald-600' : 'text-destructive'
                }`}
              >
                {realizedPnl >= 0 ? '+' : ''}₹{realizedPnl.toLocaleString('en-IN')}
              </span>
            </div>
          </div>
        </div>
      </SettingSection>

      {/* 2. Risk Boundaries & Constraints */}
      <SettingSection
        title="Execution Limits & Risk Guardrails"
        description="Enforce exposure ceilings, automatic intraday square-off, and circuit breakers."
        icon={ShieldCheck}
      >
        <SettingRow
          label="Default Starting Capital"
          description="Baseline balance restored when provisioning or resetting paper accounts."
          error={getError('initialCapital')}
        >
          <SettingSelect
            value={settings.initialCapital}
            onChange={(e) => onChange({ initialCapital: Number(e.target.value) })}
          >
            <option value={500000}>₹5,00,000 (5 Lakhs)</option>
            <option value={1000000}>₹10,00,000 (10 Lakhs - Standard)</option>
            <option value={2500000}>₹25,00,000 (25 Lakhs)</option>
            <option value={5000000}>₹50,00,000 (50 Lakhs - HNI)</option>
            <option value={10000000}>₹1,00,00,000 (1 Crore - Institutional)</option>
          </SettingSelect>
        </SettingRow>

        <SettingRow
          label="Intraday Auto Square-Off Time"
          description="Mandatory cutoff time (IST) to close open intraday MIS option & futures positions."
          error={getError('autoSquareOffTime')}
        >
          <div className="flex items-center gap-2">
            <SettingInput
              type="text"
              mono
              value={settings.autoSquareOffTime}
              onChange={(e) => onChange({ autoSquareOffTime: e.target.value })}
              className="w-28"
            />
            <span className="text-xs text-muted-foreground font-mono">IST</span>
          </div>
        </SettingRow>

        <SettingRow
          label="Single-Trade Allocation Cap"
          description="Maximum portfolio percentage allowed on any single executed option structure."
          error={getError('maxCapitalPerTradePct')}
        >
          <div className="flex items-center gap-2">
            <SettingInput
              type="number"
              min="5"
              max="100"
              mono
              value={settings.maxCapitalPerTradePct}
              onChange={(e) => onChange({ maxCapitalPerTradePct: Number(e.target.value) || 20 })}
              className="w-28"
            />
            <span className="text-xs text-muted-foreground font-mono">%</span>
          </div>
        </SettingRow>

        <SettingRow
          label="Daily Drawdown Circuit Breaker"
          description="Automatically halt all execution algorithms if daily losses exceed this threshold."
          error={getError('maxDailyDrawdownHaltPct')}
        >
          <div className="flex items-center gap-2">
            <SettingInput
              type="number"
              min="1"
              max="100"
              mono
              value={settings.maxDailyDrawdownHaltPct}
              onChange={(e) => onChange({ maxDailyDrawdownHaltPct: Number(e.target.value) || 10 })}
              className="w-28"
            />
            <span className="text-xs text-muted-foreground font-mono">%</span>
          </div>
        </SettingRow>

        <SettingRow
          label="Order Confirmation Modal"
          description="Display an explicit verification modal before routing simulated orders."
        >
          <SettingSwitch
            checked={settings.requireOrderConfirm}
            onChange={(checked) => onChange({ requireOrderConfirm: checked })}
            aria-label="Order confirmation modal"
          />
        </SettingRow>

        <SettingRow
          label="Allow Overnight (NRML) Positions"
          description="Permit multi-day swing and hedging structures to carry past market close."
        >
          <SettingSwitch
            checked={settings.allowOvernightPositions}
            onChange={(checked) => onChange({ allowOvernightPositions: checked })}
            aria-label="Allow overnight positions"
          />
        </SettingRow>
      </SettingSection>
    </div>
  );
}
