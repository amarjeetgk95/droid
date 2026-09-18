'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { api } from '@/lib/api';
import { toNumber } from '@/lib/coerce';
import { errorMessage } from '@/lib/errors';
import type { AlgoCapitalConfig } from '@/lib/api/algo';
import { Card } from '@/components/ui/card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';

interface LimitsDraft {
  investment_limit: number | null;
  max_capital_per_trade: number | null;
  max_daily_loss: number | null;
  max_loss_per_trade: number | null;
  max_open_positions: number | null;
  max_trades_per_day: number | null;
}

type LimitKey = keyof LimitsDraft;
type LoadState = 'loading' | 'ready' | 'error';

const EMPTY_DRAFT: LimitsDraft = {
  investment_limit: null,
  max_capital_per_trade: null,
  max_daily_loss: null,
  max_loss_per_trade: null,
  max_open_positions: null,
  max_trades_per_day: null,
};

const LIMIT_LABELS: Record<LimitKey, string> = {
  investment_limit: 'INVESTMENT CEILING (₹)',
  max_capital_per_trade: 'MAX PER TRADE (₹)',
  max_daily_loss: 'MAX DAILY LOSS (₹)',
  max_loss_per_trade: 'MAX LOSS PER TRADE (₹)',
  max_open_positions: 'MAX OPEN POSITIONS',
  max_trades_per_day: 'MAX TRADES / DAY',
};

const LIMIT_KEYS = Object.keys(LIMIT_LABELS) as LimitKey[];

const money = (value: number | null): string => (value === null ? '—' : `₹${value.toLocaleString('en-IN')}`);

export const CapitalLimitsEditor: React.FC = () => {
  const [config, setConfig] = useState<LimitsDraft>(EMPTY_DRAFT);
  const [baseline, setBaseline] = useState<LimitsDraft | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const action = useAsyncAction({
    errorFallback: 'Unknown capital-config error',
    busyMessage: 'A capital update is already in progress. Wait for it to finish.',
  });

  const load = useCallback(async () => {
    setLoadState('loading');
    try {
      const res = await api.getAlgoCapital();
      const cfg = res?.data?.config;
      if (!cfg) throw new Error('Backend returned no capital config.');
      const draft: LimitsDraft = {
        investment_limit: toNumber(cfg.investment_limit),
        max_capital_per_trade: toNumber(cfg.max_capital_per_trade),
        max_daily_loss: toNumber(cfg.max_daily_loss),
        max_loss_per_trade: toNumber(cfg.max_loss_per_trade),
        max_open_positions: toNumber(cfg.max_open_positions),
        max_trades_per_day: toNumber(cfg.max_trades_per_day),
      };
      setConfig(draft);
      setBaseline(draft);
      setLoadState('ready');
      setLoadError(null);
    } catch (err) {
      setLoadState('error');
      setLoadError(errorMessage(err, 'Unknown capital-config error'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const isDirty =
    baseline !== null && LIMIT_KEYS.some((key) => config[key] !== baseline[key]);

  const changes =
    baseline === null
      ? []
      : LIMIT_KEYS.filter((key) => config[key] !== baseline[key]).map((key) => ({
          key,
          label: LIMIT_LABELS[key],
          from: baseline[key],
          to: config[key],
        }));

  const updateField = (key: LimitKey, raw: string) => {
    const parsed = raw === '' ? null : Number(raw);
    setConfig((prev) => ({
      ...prev,
      [key]: parsed !== null && Number.isFinite(parsed) ? parsed : null,
    }));
    setSuccess(null);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setResultError(null);
    setSuccess(null);

    if (loadState !== 'ready') {
      setResultError('Capital limits are not loaded — cannot save.');
      return;
    }
    if (!isDirty) {
      setResultError('No changes to save.');
      return;
    }

    const problems: string[] = [];
    LIMIT_KEYS.forEach((key) => {
      const value = config[key];
      if (value === null || value < 0) {
        problems.push(`${key} must be a non-negative number`);
      }
    });
    if ((config.max_open_positions ?? 0) < 1) problems.push('max_open_positions must be at least 1');
    if ((config.max_trades_per_day ?? 0) < 1) problems.push('max_trades_per_day must be at least 1');
    if (problems.length > 0) {
      setResultError(`Invalid limits: ${problems.join(' · ')}`);
      return;
    }

    setConfirmOpen(true);
  };

  const handleSaveConfirm = async () => {
    setResultError(null);
    setSuccess(null);

    const outcome = await action.run(async () => {
      const payload: AlgoCapitalConfig = {
        investment_limit: config.investment_limit as number,
        max_capital_per_trade: config.max_capital_per_trade as number,
        max_daily_loss: config.max_daily_loss as number,
        max_loss_per_trade: config.max_loss_per_trade as number,
        max_open_positions: config.max_open_positions as number,
        max_trades_per_day: config.max_trades_per_day as number,
        confirm: true,
      };
      const res = await api.updateAlgoCapital(payload);
      const data = res?.data;
      if (!data) throw new Error('Risk engine returned no result — update not confirmed.');
      if (data.updated === false) {
        throw new Error(data.reason ? `Risk engine refused the update: ${data.reason}` : 'Risk engine refused the update.');
      }
      if (typeof data.limit_exceeded === 'string' && data.limit_exceeded) {
        throw new Error(`Risk limit exceeded: ${data.limit_exceeded}`);
      }
      return { reason: typeof data.reason === 'string' && data.reason ? data.reason : null };
    });

    if (!outcome.ok) {
      setResultError(outcome.message);
      throw new Error(outcome.message);
    }

    setSuccess(
      outcome.value.reason
        ? `Risk mandate updated: ${outcome.value.reason}`
        : 'Risk mandate updated and verified by the risk engine.',
    );
    await load();
  };

  return (
    <>
      <Card
        title="RISK MANDATE & CAPITAL LIMITS EDITOR"
        subtitle="Hard server-side risk gate parameters (SEBI Algo Compliance §76)"
      >
        {loadState === 'error' && (
          <div
            role="alert"
            className="mb-3 rounded border border-down-line bg-down-wash px-2.5 py-1.5 font-mono text-[11px] text-down-strong"
          >
            Capital limits unavailable — {loadError}. Saving is disabled until the config loads.
            <button
              type="button"
              onClick={() => void load()}
              className="ml-2 underline font-semibold"
            >
              Retry
            </button>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3 font-mono text-xs">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {LIMIT_KEYS.map((key) => (
              <div key={key}>
                <label className="text-ink-2 block mb-1" htmlFor={`capital-${key}`}>
                  {LIMIT_LABELS[key]}
                </label>
                <input
                  id={`capital-${key}`}
                  type="number"
                  value={config[key] ?? ''}
                  disabled={loadState !== 'ready'}
                  onChange={(e) => updateField(key, e.target.value)}
                  className={`input w-full num ${
                    key === 'max_daily_loss' || key === 'max_loss_per_trade'
                      ? 'text-down-strong font-bold'
                      : ''
                  }`}
                />
              </div>
            ))}
          </div>

          {resultError && (
            <div
              role="alert"
              className="rounded border border-down-line bg-down-wash px-2.5 py-1.5 text-down-strong"
            >
              {resultError}
            </div>
          )}

          {success && (
            <div
              role="status"
              className="rounded border border-up-line bg-up-wash px-2.5 py-1.5 text-up-strong text-center"
            >
              {success}
            </div>
          )}

          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] text-ink-3">
              {loadState === 'loading'
                ? 'Loading current risk mandate…'
                : isDirty
                  ? `${changes.length} field(s) changed — confirmation required`
                  : 'No unsaved changes'}
            </span>
            <button
              type="submit"
              disabled={action.isPending || loadState !== 'ready' || !isDirty}
              className="btn btn-primary disabled:opacity-40"
            >
              {action.isPending ? 'Saving…' : 'Apply & Confirm Capital Limits'}
            </button>
          </div>
        </form>
      </Card>

      <ConfirmDialog
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleSaveConfirm}
        title="CONFIRM HARD RISK LIMITS UPDATE"
        message={
          <div className="space-y-3 font-mono text-xs">
            <p>
              Apply <span className="font-bold text-ink">{changes.length}</span> change(s) to the
              server-side hard risk gates? These limits are enforced by the risk engine on every order.
            </p>
            <dl className="rounded border border-border bg-surface-subtle p-2.5 space-y-1">
              {changes.map((change) => (
                <div key={change.key} className="flex justify-between gap-3">
                  <dt className="text-ink-3">{change.label}</dt>
                  <dd className="text-ink-2">
                    <span className="text-ink-3">{money(change.from)}</span>
                    <span className="mx-1">→</span>
                    <span className="font-semibold text-ink">{money(change.to)}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        }
        confirmLabel="CONFIRM & APPLY LIMITS"
        destructive={true}
      />
    </>
  );
};
