'use client';

import * as React from 'react';
import { X, ChevronLeft, ChevronRight, Trash2, AlertTriangle, ShieldCheck } from 'lucide-react';
import type { HpiDeletePreview, HpiDerivative } from '@/lib/types';
import { categoryLabel } from '@/lib/historical-intelligence/labels';
import { fmtMb, fmtNumber, fmtDate } from '@/lib/historical-intelligence/format';
import { cn } from '@/lib/utils';

interface Props {
  symbol: string;
  derivative: HpiDerivative | undefined;
  onClose: () => void;
  onPreview: (req: Record<string, unknown>) => Promise<{ preview?: HpiDeletePreview; error?: string }>;
  onConfirm: (token: string, reason: string) => Promise<{ error?: string }>;
}

const RANGES = [
  { value: 'last_30_days', label: 'Last 30 days' },
  { value: 'last_3_months', label: 'Last 3 months' },
  { value: 'older_than_6_months', label: 'Older than 6 months' },
  { value: 'custom', label: 'Custom date range' },
  { value: 'all_time', label: 'All stored data' },
];

type Step = 'scope' | 'impact' | 'confirm';

export function DeleteWizard({ symbol, derivative, onClose, onPreview, onConfirm }: Props) {
  const [step, setStep] = React.useState<Step>('scope');
  const [categories, setCategories] = React.useState<string[]>([]);
  const [rangeType, setRangeType] = React.useState('last_30_days');
  const [startDate, setStartDate] = React.useState('');
  const [endDate, setEndDate] = React.useState('');
  const [reason, setReason] = React.useState('');
  const [allowProtected, setAllowProtected] = React.useState(false);
  const [preview, setPreview] = React.useState<HpiDeletePreview | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose(); }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const buildReq = (): Record<string, unknown> => {
    const req: Record<string, unknown> = {
      symbol, categories, range_type: rangeType, reason: reason || undefined, allow_protected: allowProtected,
    };
    if (rangeType === 'custom') {
      if (startDate) req.start_date = new Date(startDate).toISOString();
      if (endDate) req.end_date = new Date(endDate).toISOString();
    }
    return req;
  };

  const next = async () => {
    setError(null);
    if (step === 'scope' && categories.length === 0) {
      setError('Pick at least one dataset.');
      return;
    }
    if (step === 'scope' && rangeType === 'custom' && (!startDate || !endDate)) {
      setError('Provide both start and end dates for a custom range.');
      return;
    }
    if (step === 'impact') {
      setBusy(true);
      const res = await onPreview(buildReq());
      setBusy(false);
      if (res.error) { setError(res.error); return; }
      setPreview(res.preview ?? null);
      setStep('confirm');
      return;
    }
    if (step === 'confirm') {
      if (!reason.trim()) { setError('A reason is required for the audit log.'); return; }
      if (!preview) return;
      setBusy(true);
      const res = await onConfirm(preview.confirmation_token, reason.trim());
      setBusy(false);
      if (res.error) { setError(res.error); return; }
      onClose();
      return;
    }
  };

  const back = () => {
    if (step === 'impact') setStep('scope');
    else if (step === 'confirm') { setStep('impact'); setPreview(null); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" role="dialog" aria-modal="true">
      <div className={cn('w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl border bg-card shadow-xl max-h-[92vh] flex flex-col', step === 'confirm' ? 'border-red-500/40' : 'border-border')}>
        <header className={cn('flex items-center justify-between px-5 py-4 border-b', step === 'confirm' ? 'border-red-500/30 bg-red-500/5' : 'border-border')}>
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Step {step === 'scope' ? '1' : step === 'impact' ? '2' : '3'} of 3</p>
            <h3 className={cn('font-bold text-base truncate', step === 'confirm' && 'text-red-500')}>
              Delete — {derivative?.display_name ?? symbol}
            </h3>
          </div>
          <button onClick={onClose} aria-label="Close delete wizard" className="p-1.5 rounded-md hover:bg-secondary">
            <X className="w-4 h-4" />
          </button>
        </header>

        <Stepper current={step} danger={step === 'confirm'} />

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 text-red-500 text-xs px-3 py-2 flex items-start gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {step === 'scope' && (
            <div className="space-y-4">
              <div>
                <p className="text-sm font-semibold">Which datasets?</p>
                <p className="text-xs text-muted-foreground">Only selected datasets will be considered for deletion.</p>
                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {(derivative?.data_categories ?? []).map((cat) => {
                    const checked = categories.includes(cat);
                    return (
                      <label key={cat} className={cn('flex items-center gap-2 rounded-md border p-3 cursor-pointer text-xs', checked ? 'border-red-500/60 bg-red-500/5' : 'border-border hover:bg-secondary/40')}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => setCategories(e.target.checked ? [...categories, cat] : categories.filter((c) => c !== cat))}
                          className="w-3.5 h-3.5"
                        />
                        <span className="font-medium">{categoryLabel(cat)}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-muted-foreground">Date range</label>
                <select value={rangeType} onChange={(e) => setRangeType(e.target.value)} className="mt-1 w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-sm">
                  {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                {rangeType === 'custom' && (
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-[10px] text-muted-foreground">Start</label>
                      <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs" />
                    </div>
                    <div>
                      <label className="text-[10px] text-muted-foreground">End</label>
                      <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs" />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {step === 'impact' && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Impact preview</p>
              <p className="text-xs text-muted-foreground">We will compute exactly how many records will be removed and what historical analysis will be affected.</p>
              <div className="rounded-md border border-border bg-muted/30 p-4 text-xs">
                <ul className="space-y-1.5">
                  <li><strong className="text-foreground">Range:</strong> {RANGES.find((r) => r.value === rangeType)?.label}</li>
                  <li><strong className="text-foreground">Datasets:</strong> {categories.length} selected</li>
                  <li><strong className="text-foreground">Allow protected:</strong> {allowProtected ? 'Yes' : 'No'}</li>
                </ul>
              </div>
              <label className="inline-flex items-center gap-2 text-xs cursor-pointer">
                <input type="checkbox" checked={allowProtected} onChange={(e) => setAllowProtected(e.target.checked)} className="w-3.5 h-3.5" />
                Include protected datasets (explicit override required)
              </label>
            </div>
          )}

          {step === 'confirm' && preview && (
            <div className="space-y-4">
              <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-xs">
                <p className="font-semibold text-red-500 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> This will permanently delete</p>
                <p className="mt-1 text-2xl font-bold text-red-500 tabular-nums">{fmtNumber(preview.total_records)} <span className="text-sm font-normal text-muted-foreground">records</span></p>
                <p className="text-xs text-muted-foreground">{fmtMb(preview.total_storage_mb)} released · {fmtDate(preview.range_start)} → {fmtDate(preview.range_end)}</p>
              </div>

              {preview.protected_categories.length > 0 && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs flex items-start gap-2">
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-600 mt-0.5 shrink-0" />
                  <div>
                    <p className="font-semibold text-amber-600">Protected datasets detected</p>
                    <p className="text-muted-foreground mt-0.5">
                      {preview.protected_categories.map((c) => categoryLabel(c)).join(', ')} will be skipped
                      {allowProtected ? ' unless "include protected" is checked.' : '.'}
                    </p>
                  </div>
                </div>
              )}

              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1">Per-dataset breakdown</p>
                <ul className="rounded-md border border-border overflow-hidden">
                  {preview.per_category.map((p) => (
                    <li key={p.category} className="flex items-center justify-between px-3 py-2 text-xs border-b border-border/60 last:border-b-0">
                      <span>{p.label}</span>
                      <span className="tabular-nums text-muted-foreground">{fmtNumber(p.records)} rec · {fmtMb(p.storage_mb)}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1">Historical-analysis impact</p>
                <ul className="list-disc list-inside text-xs text-muted-foreground space-y-0.5">
                  {preview.analytical_impact.map((i) => <li key={i}>{i}</li>)}
                </ul>
              </div>

              <div>
                <label className="text-xs font-semibold text-muted-foreground">Reason (required, recorded in audit log)</label>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. cleanup before re-import with 5m sampling"
                  className="mt-1 w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-sm"
                />
              </div>
            </div>
          )}
        </div>

        <footer className="flex items-center gap-2 px-5 py-3 border-t border-border bg-muted/30">
          {step !== 'scope' && (
            <button onClick={back} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary disabled:opacity-50">
              <ChevronLeft className="w-3.5 h-3.5" /> Back
            </button>
          )}
          <button onClick={onClose} disabled={busy} className="px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary ml-auto disabled:opacity-50">Cancel</button>
          <button
            onClick={next}
            disabled={busy}
            className={cn(
              'inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-semibold disabled:opacity-50',
              step === 'confirm' ? 'bg-red-500 text-white' : 'bg-primary text-primary-foreground'
            )}
          >
            {busy ? 'Working…' : step === 'scope' ? (<>Next <ChevronRight className="w-3.5 h-3.5" /></>) : step === 'impact' ? (<>Preview impact <ChevronRight className="w-3.5 h-3.5" /></>) : (<><Trash2 className="w-3.5 h-3.5" /> Confirm delete</>)}
          </button>
        </footer>
      </div>
    </div>
  );
}

function Stepper({ current, danger }: { current: Step; danger: boolean }) {
  const steps: Array<{ id: Step; label: string }> = [
    { id: 'scope', label: 'Scope' },
    { id: 'impact', label: 'Impact' },
    { id: 'confirm', label: 'Confirm' },
  ];
  const idx = steps.findIndex((s) => s.id === current);
  return (
    <ol className="flex items-center gap-1 px-5 pt-3" aria-label="Wizard progress">
      {steps.map((s, i) => {
        const done = i < idx;
        const active = i === idx;
        return (
          <li key={s.id} className="flex-1 flex items-center gap-2">
            <span className={cn(
              'h-5 w-5 rounded-full grid place-items-center text-[10px] font-bold border',
              done && (danger ? 'bg-red-500 text-white border-red-500' : 'bg-primary text-primary-foreground border-primary'),
              active && (danger ? 'border-red-500 text-red-500' : 'border-primary text-primary'),
              !done && !active && 'border-border text-muted-foreground'
            )}>
              {done ? '✓' : i + 1}
            </span>
            <span className={cn('text-xs', active && (danger ? 'text-red-500 font-semibold' : 'font-semibold'), !active && 'text-muted-foreground')}>{s.label}</span>
            {i < steps.length - 1 && <span className="flex-1 h-px bg-border ml-2" />}
          </li>
        );
      })}
    </ol>
  );
}