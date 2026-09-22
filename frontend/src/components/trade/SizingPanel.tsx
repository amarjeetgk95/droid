'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useToast } from '@/components/ui/toast';
import {
  buildSizingPayload,
  type SizingFormState,
  type SizingPreview,
} from '@/lib/tradeOps';
import type { SizingPreviewResult } from '@/hooks/useTradeOps';
import { safeNum } from '@/lib/utils';

// No prefilled wallet numbers: risk budget / lot size / multiplier are
// examples only, and available capital is prefilled solely from a connected
// account snapshot (synced below when that snapshot arrives).
const EMPTY_FORM: SizingFormState = {
  entryPrice: '',
  stopPrice: '',
  riskBudget: '',
  lotSize: '',
  contractMultiplier: '',
  maxCapitalPerTrade: '',
  maxPositionSize: '',
  availableCapital: '',
};

function Field({
  label,
  value,
  onChange,
  placeholder,
  required,
}: {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  return (
    <label className="field">
      <span className="field-l">
        {label}
        {required ? ' *' : ''}
      </span>
      <input
        type="number"
        min="0"
        step="any"
        className="input num"
        value={value}
        placeholder={placeholder}
        required={required}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

/** On-demand sizing preview. Pure compute — places no orders. */
export function SizingPanel({
  defaultAvailable,
  previewSizing,
}: {
  defaultAvailable: number | null;
  previewSizing: (payload: Record<string, number>) => Promise<SizingPreviewResult>;
}) {
  const { push } = useToast();
  const [form, setForm] = useState<SizingFormState>({
    ...EMPTY_FORM,
    availableCapital: defaultAvailable !== null ? String(defaultAvailable) : '',
  });
  const [lastDefault, setLastDefault] = useState<number | null>(defaultAvailable);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<SizingPreview | null>(null);

  // Track the connected account snapshot: re-prefill available capital when it
  // changes (e.g. stream arrives after mount), but never clobber a user edit.
  useEffect(() => {
    if (defaultAvailable === lastDefault) return;
    const previousDefault = lastDefault !== null ? String(lastDefault) : '';
    setLastDefault(defaultAvailable);
    setForm((prev) =>
      prev.availableCapital === previousDefault
        ? { ...prev, availableCapital: defaultAvailable !== null ? String(defaultAvailable) : '' }
        : prev,
    );
  }, [defaultAvailable, lastDefault]);

  const hasAccountSource = defaultAvailable !== null;

  const set = (key: keyof SizingFormState) => (next: string) =>
    setForm((prev) => ({ ...prev, [key]: next }));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const built = buildSizingPayload(form);
    if (!built.ok) {
      push('error', built.error);
      return;
    }
    setBusy(true);
    try {
      const result = await previewSizing(built.payload);
      push(result.ok ? 'success' : 'error', result.message);
      setPreview(result.preview);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">Sizing Preview</h3>
        <span className="card-meta">on-demand · places no orders</span>
      </header>
      <p className="sg-note">
        Computes the risk-based quantity for an entry price and stop. Nothing is submitted —
        the result is advisory only.
      </p>
      <p className="sg-note">
        {hasAccountSource
          ? 'Available capital is prefilled from the connected account snapshot. Risk budget, lot size and multiplier placeholders are examples — confirm each value before use.'
          : 'No connected account snapshot is available — all capital inputs are manual and advisory. Risk budget / lot size placeholders are examples, not live wallet values.'}
      </p>
      <form onSubmit={(e) => void handleSubmit(e)}>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Entry price" value={form.entryPrice} onChange={set('entryPrice')} placeholder="e.g. 120.5" required />
          <Field label="Stop price" value={form.stopPrice} onChange={set('stopPrice')} placeholder="e.g. 110" />
          <Field label="Risk budget (example)" value={form.riskBudget} onChange={set('riskBudget')} placeholder="e.g. 500" />
          <Field label="Lot size (example)" value={form.lotSize} onChange={set('lotSize')} placeholder="e.g. 1" />
          <Field label="Contract mult (example)" value={form.contractMultiplier} onChange={set('contractMultiplier')} placeholder="e.g. 1" />
          <Field label="Max capital/trade" value={form.maxCapitalPerTrade} onChange={set('maxCapitalPerTrade')} placeholder="e.g. 1000" />
          <Field label="Max position size" value={form.maxPositionSize} onChange={set('maxPositionSize')} placeholder="e.g. 500" />
          <Field
            label={hasAccountSource ? 'Available capital (account)' : 'Available capital (manual)'}
            value={form.availableCapital}
            onChange={set('availableCapital')}
            placeholder="e.g. 3000"
          />
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? 'Computing…' : 'Preview sizing'}
          </button>
        </div>
      </form>
      {preview ? (
        <div className="sg-kvlist">
          <div className="sg-kv">
            <span className="l">Quantity</span>
            <span className="v">{preview.quantity ?? '—'}</span>
          </div>
          <div className="sg-kv">
            <span className="l">Notional</span>
            <span className="v">{safeNum(preview.notional)}</span>
          </div>
          <div className="sg-kv">
            <span className="l">Risk per unit</span>
            <span className="v">{safeNum(preview.riskPerUnit)}</span>
          </div>
          <div className="sg-kv">
            <span className="l">Capped by</span>
            <span className="v">{preview.cappedBy ?? '—'}</span>
          </div>
          <div className="sg-kv">
            <span className="l">Reason</span>
            <span className="v">{preview.reason ?? '—'}</span>
          </div>
        </div>
      ) : (
        <p className="sg-empty">No preview yet — enter an entry price and run the calculator.</p>
      )}
    </section>
  );
}
