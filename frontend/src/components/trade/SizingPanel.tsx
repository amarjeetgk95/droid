'use client';

import { useState, type FormEvent } from 'react';
import { useToast } from '@/components/ui/toast';
import {
  buildSizingPayload,
  type SizingFormState,
  type SizingPreview,
} from '@/lib/tradeOps';
import type { SizingPreviewResult } from '@/hooks/useTradeOps';
import { safeNum } from '@/lib/utils';

const EMPTY_FORM: SizingFormState = {
  entryPrice: '',
  stopPrice: '',
  riskBudget: '500',
  lotSize: '1',
  contractMultiplier: '1',
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
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<SizingPreview | null>(null);

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
      <form onSubmit={(e) => void handleSubmit(e)}>
        <div className="flex flex-wrap items-end gap-2">
          <Field label="Entry price" value={form.entryPrice} onChange={set('entryPrice')} placeholder="120.5" required />
          <Field label="Stop price" value={form.stopPrice} onChange={set('stopPrice')} placeholder="110" />
          <Field label="Risk budget" value={form.riskBudget} onChange={set('riskBudget')} placeholder="500" />
          <Field label="Lot size" value={form.lotSize} onChange={set('lotSize')} placeholder="1" />
          <Field label="Contract mult" value={form.contractMultiplier} onChange={set('contractMultiplier')} placeholder="1" />
          <Field label="Max capital/trade" value={form.maxCapitalPerTrade} onChange={set('maxCapitalPerTrade')} placeholder="1000" />
          <Field label="Max position size" value={form.maxPositionSize} onChange={set('maxPositionSize')} placeholder="500" />
          <Field label="Available capital" value={form.availableCapital} onChange={set('availableCapital')} placeholder="3000" />
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
