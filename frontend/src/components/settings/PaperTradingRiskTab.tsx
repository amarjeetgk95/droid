'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, RefreshCw, Wallet, AlertCircle } from 'lucide-react';
import { PaperTradingSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { PortfolioSummary } from '@/lib/types';
import {
  SettingSection,
  SettingRow,
  SettingInput,
  SettingSelect,
  SettingSwitch,
  StatTile,
  FeedbackBanner,
} from './ui/SettingPrimitives';

interface Props {
  settings: PaperTradingSettings;
  onChange: (updated: Partial<PaperTradingSettings>) => void;
  errors?: { path: string; message: string }[];
}

function formatRupees(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `₹${value.toLocaleString('en-IN')}`;
}

export function PaperTradingRiskTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `paper.${field}`)?.message;
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Raw input drafts so an invalid entry stays visible (and blocks save via
  // NaN) instead of being silently snapped to a fallback number.
  const [tradeCapDraft, setTradeCapDraft] = useState(() => String(settings.maxCapitalPerTradePct));
  const [drawdownDraft, setDrawdownDraft] = useState(() => String(settings.maxDailyDrawdownHaltPct));
  const [squareOffDraft, setSquareOffDraft] = useState(() => settings.autoSquareOffTime);

  useEffect(() => {
    if (Number.isFinite(settings.maxCapitalPerTradePct)) {
      setTradeCapDraft(String(settings.maxCapitalPerTradePct));
    }
  }, [settings.maxCapitalPerTradePct]);
  useEffect(() => {
    if (Number.isFinite(settings.maxDailyDrawdownHaltPct)) {
      setDrawdownDraft(String(settings.maxDailyDrawdownHaltPct));
    }
  }, [settings.maxDailyDrawdownHaltPct]);
  useEffect(() => {
    setSquareOffDraft(settings.autoSquareOffTime);
  }, [settings.autoSquareOffTime]);

  const fetchPortfolio = useCallback(async () => {
    setLoading(true);
    setPortfolioError(null);
    try {
      const res = await api.getPaperPortfolio();
      setPortfolio(res.data ?? null);
      if (!res.data) setPortfolioError('Portfolio endpoint returned no data.');
    } catch (err: unknown) {
      setPortfolio(null);
      setPortfolioError(err instanceof Error ? err.message : 'Failed to load paper portfolio');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchPortfolio();
  }, [fetchPortfolio]);

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
      if (res.data) {
        setPortfolio(res.data);
        setPortfolioError(null);
      } else {
        setPortfolioError('Reset completed but the backend returned no portfolio summary.');
      }
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

  const handleTradeCapChange = (raw: string) => {
    setTradeCapDraft(raw);
    const parsed = raw.trim() === '' ? NaN : Number(raw);
    onChange({ maxCapitalPerTradePct: parsed });
  };

  const handleDrawdownChange = (raw: string) => {
    setDrawdownDraft(raw);
    const parsed = raw.trim() === '' ? NaN : Number(raw);
    onChange({ maxDailyDrawdownHaltPct: parsed });
  };

  const handleSquareOffChange = (raw: string) => {
    setSquareOffDraft(raw);
    onChange({ autoSquareOffTime: raw });
  };

  const marginUtilization =
    portfolio?.margin_utilization_pct != null ? `${portfolio.margin_utilization_pct}%` : undefined;

  return (
    <div className="space-y-4">
      <FeedbackBanner message={msg} onDismiss={() => setMsg(null)} />

      {/* 1. Account Summary & Status */}
      <SettingSection
        title="Virtual Portfolio & Capital Allocation"
        description="Simulated capital allocation, available intraday margin, and cumulative P&L."
        icon={Wallet}
        action={
          <button
            type="button"
            onClick={handleResetAccount}
            disabled={resetting}
            className="btn btn-sm flex items-center gap-1.5 text-[var(--ds-bear)] hover:border-[var(--ds-bear)] disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
            <span>{resetting ? 'Resetting…' : 'Reset Account'}</span>
          </button>
        }
      >
        <div className="card-pad space-y-3">
          {portfolioError && (
            <div className="flex items-center gap-2 text-xs text-[var(--ds-bear-strong)] bg-[var(--ds-bear-wash)] border border-[var(--ds-bear-line)] rounded p-2.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>Portfolio telemetry unavailable — {portfolioError}</span>
            </div>
          )}
          <div className="stat-grid grid-cols-2 sm:grid-cols-4">
            <StatTile
              label="Virtual capital"
              value={loading ? '…' : formatRupees(portfolio?.virtual_capital)}
            />
            <StatTile
              label="Available margin"
              value={loading ? '…' : formatRupees(portfolio?.available_margin)}
              tone="positive"
            />
            <StatTile
              label="Margin utilized"
              value={loading ? '…' : formatRupees(portfolio?.used_margin)}
              sub={loading ? undefined : marginUtilization}
            />
            <StatTile
              label="Realized P&L"
              value={loading ? '…' : formatRupees(portfolio?.total_realized_pnl)}
              tone={
                portfolio?.total_realized_pnl != null && portfolio.total_realized_pnl >= 0
                  ? 'positive'
                  : 'negative'
              }
            />
          </div>
        </div>
      </SettingSection>

      {/* 2. Risk Boundaries & Constraints */}
      <SettingSection
        title="Execution limits & risk guardrails"
        description="Exposure ceilings, automatic intraday square-off, and circuit breakers."
        icon={ShieldCheck}
      >
        <SettingRow
          label="Default Starting Capital"
          description="Baseline balance restored when provisioning or resetting paper accounts."
          error={getError('initialCapital')}
          htmlFor="paper-initial-capital"
        >
          <SettingSelect
            id="paper-initial-capital"
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
          htmlFor="paper-square-off"
        >
          <div className="flex items-center gap-2">
            <SettingInput
              id="paper-square-off"
              type="text"
              mono
              value={squareOffDraft}
              onChange={(e) => handleSquareOffChange(e.target.value)}
              className="w-28"
            />
            <span className="text-xs text-muted-foreground font-mono">IST</span>
          </div>
        </SettingRow>

        <SettingRow
          label="Single-Trade Allocation Cap"
          description="Maximum portfolio percentage allowed on any single executed option structure."
          error={getError('maxCapitalPerTradePct')}
          htmlFor="paper-trade-cap"
        >
          <div className="flex items-center gap-2">
            <SettingInput
              id="paper-trade-cap"
              type="number"
              min="1"
              max="100"
              mono
              value={tradeCapDraft}
              onChange={(e) => handleTradeCapChange(e.target.value)}
              className="w-28"
            />
            <span className="text-xs text-muted-foreground font-mono">%</span>
          </div>
        </SettingRow>

        <SettingRow
          label="Daily Drawdown Circuit Breaker"
          description="Automatically halt all execution algorithms if daily losses exceed this threshold."
          error={getError('maxDailyDrawdownHaltPct')}
          htmlFor="paper-drawdown"
        >
          <div className="flex items-center gap-2">
            <SettingInput
              id="paper-drawdown"
              type="number"
              min="1"
              max="100"
              mono
              value={drawdownDraft}
              onChange={(e) => handleDrawdownChange(e.target.value)}
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
