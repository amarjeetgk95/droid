'use client';

import * as React from 'react';
import { X, ChevronLeft, ChevronRight, Download, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { HpiDerivative, HpiImportPreview, HpiImportResult } from '@/lib/types';
import { categoryLabel } from '@/lib/historical-intelligence/labels';
import { fmtMb, fmtNumber } from '@/lib/historical-intelligence/format';
import { StorageBar } from '../StorageBar';
import { cn } from '@/lib/utils';

interface Props {
  symbol: string;
  derivative: HpiDerivative | undefined;
  initialCategories: string[];
  initialSampling: string;
  samplingIntervals: string[];
  storageBudget: { target_mb: number; warning_mb: number; hard_ceiling_mb: number; current_mb?: number };
  onClose: () => void;
  onImport: (req: Record<string, unknown>, estimateOnly: boolean) => Promise<{ preview?: HpiImportPreview; result?: HpiImportResult; error?: string }>;
}

const PERIODS = [
  { label: '1 month', days: 30 },
  { label: '3 months', days: 90 },
  { label: '6 months', days: 180 },
  { label: '1 year', days: 365 },
  { label: '2 years', days: 730 },
  { label: '3 years', days: 1095 },
  { label: '5 years', days: 1825 },
  { label: 'Custom range', days: 0 },
];

type Step = 'scope' | 'period' | 'review';

export function ImportWizard({ symbol, derivative, initialCategories, initialSampling, samplingIntervals, storageBudget, onClose, onImport }: Props) {
  const [step, setStep] = React.useState<Step>('scope');
  const [categories, setCategories] = React.useState<string[]>(initialCategories);
  const [period, setPeriod] = React.useState(PERIODS[2]);
  const [startDate, setStartDate] = React.useState('');
  const [endDate, setEndDate] = React.useState('');
  const [sampling, setSampling] = React.useState(initialSampling);
  const [preview, setPreview] = React.useState<HpiImportPreview | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const buildRequest = (estimateOnly: boolean): Record<string, unknown> => {
    const req: Record<string, unknown> = {
      symbol, categories, sampling_interval: sampling, estimate_only: estimateOnly,
    };
    if (period.days === 0) {
      if (startDate) req.start_date = new Date(startDate).toISOString();
      if (endDate) req.end_date = new Date(endDate).toISOString();
    } else {
      req.retention_days = period.days;
    }
    return req;
  };

  const next = async () => {
    setError(null);
    if (step === 'scope') {
      if (categories.length === 0) {
        setError('Pick at least one data category.');
        return;
      }
      setStep('period');
      return;
    }
    if (step === 'period') {
      if (period.days === 0 && (!startDate || !endDate)) {
        setError('Provide both start and end dates for a custom range.');
        return;
      }
      setBusy(true);
      const res = await onImport(buildRequest(true), true);
      setBusy(false);
      if (res.error) { setError(res.error); return; }
      setPreview(res.preview ?? null);
      setStep('review');
      return;
    }
    if (step === 'review' && preview && !preview.blocked) {
      setBusy(true);
      setError(null);
      const res = await onImport(buildRequest(false), false);
      setBusy(false);
      if (res.error) { setError(res.error); return; }
      onClose();
      return;
    }
  };

  const back = () => {
    if (step === 'period') setStep('scope');
    else if (step === 'review') { setStep('period'); setPreview(null); }
  };

  const blocked = preview?.blocked ?? false;
  const projected = preview?.projected_storage_mb ?? storageBudget.current_mb;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/60 p-0 sm:p-4" role="dialog" aria-modal="true">
      <div className="w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl border border-border bg-card shadow-xl max-h-[92vh] flex flex-col">
        <header className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Step {step === 'scope' ? '1' : step === 'period' ? '2' : '3'} of 3</p>
            <h3 className="font-bold text-base truncate">Import — {derivative?.display_name ?? symbol}</h3>
          </div>
          <button onClick={onClose} aria-label="Close import wizard" className="p-1.5 rounded-md hover:bg-secondary">
            <X className="w-4 h-4" />
          </button>
        </header>

        <Stepper current={step} />

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && (
            <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 text-red-500 text-xs px-3 py-2 flex items-start gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {step === 'scope' && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Which data categories?</p>
              <p className="text-xs text-muted-foreground">Pick one or more. Categories you don&apos;t enable won&apos;t be imported.</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(derivative?.data_categories ?? []).map((cat) => {
                  const checked = categories.includes(cat);
                  return (
                    <label
                      key={cat}
                      className={cn(
                        'flex items-center gap-2 rounded-md border p-3 cursor-pointer transition-colors',
                        checked ? 'border-primary/60 bg-primary/5' : 'border-border hover:bg-secondary/40'
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => setCategories(e.target.checked ? [...categories, cat] : categories.filter((c) => c !== cat))}
                        className="w-3.5 h-3.5"
                      />
                      <span className="text-xs font-medium">{categoryLabel(cat)}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {step === 'period' && (
            <div className="space-y-3">
              <p className="text-sm font-semibold">Period and sampling</p>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Historical period</label>
                <select
                  value={period.label}
                  onChange={(e) => setPeriod(PERIODS.find((p) => p.label === e.target.value)!)}
                  className="mt-1 w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-sm"
                >
                  {PERIODS.map((p) => (
                    <option key={p.label} value={p.label}>{p.label}</option>
                  ))}
                </select>
              </div>
              {period.days === 0 && (
                <div className="grid grid-cols-2 gap-2">
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
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Sampling interval</label>
                <select value={sampling} onChange={(e) => setSampling(e.target.value)} className="mt-1 w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-sm">
                  {samplingIntervals.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {step === 'review' && preview && (
            <div className="space-y-4">
              <div>
                <p className="text-xs text-muted-foreground">Projected total</p>
                <p className="text-2xl font-bold tabular-nums">{preview.projected_storage_mb} MB</p>
                <p className="text-[10px] text-muted-foreground">
                  Current {preview.current_storage_mb} MB + addition {preview.requested_addition_mb} MB
                </p>
              </div>

              <StorageBar
                currentMb={preview.current_storage_mb}
                targetMb={storageBudget.target_mb}
                warningMb={storageBudget.warning_mb}
                hardCeilingMb={storageBudget.hard_ceiling_mb}
                status={blocked ? 'EXCEEDS_HARD' : projected && projected > storageBudget.warning_mb ? 'WARNING' : 'WITHIN_TARGET'}
                projectedMb={preview.projected_storage_mb}
              />

              <div className="rounded-md border border-border overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left p-2 font-medium">Category</th>
                      <th className="text-right p-2 font-medium">Sampling</th>
                      <th className="text-right p-2 font-medium">Records</th>
                      <th className="text-right p-2 font-medium">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.breakdown.map((b) => (
                      <tr key={b.category} className="border-t border-border/60">
                        <td className="p-2">{categoryLabel(b.category)}</td>
                        <td className="p-2 text-right tabular-nums">{b.sampling_interval}</td>
                        <td className="p-2 text-right tabular-nums">{fmtNumber(b.estimated_records)}</td>
                        <td className="p-2 text-right tabular-nums">{fmtMb(b.estimated_mb)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {preview.warnings.length > 0 && (
                <ul className="space-y-1">
                  {preview.warnings.map((w) => (
                    <li key={w} className="text-xs text-amber-600 flex items-start gap-1.5">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {w}
                    </li>
                  ))}
                </ul>
              )}

              {blocked ? (
                <div className="rounded-md border border-red-500/40 bg-red-500/5 p-3 text-xs">
                  <p className="font-semibold text-red-500 flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> Storage ceiling exceeded</p>
                  <p className="text-muted-foreground mt-1">Reduce the scope to fit under the ceiling:</p>
                  <ul className="mt-2 space-y-1 list-disc list-inside">
                    {preview.alternatives.map((a) => <li key={a}>{a}</li>)}
                  </ul>
                </div>
              ) : (
                <div className="rounded-md border border-green-500/30 bg-green-500/5 p-3 text-xs flex items-start gap-2">
                  <CheckCircle2 className="w-3.5 h-3.5 text-green-600 mt-0.5 shrink-0" />
                  <span>Within budget. Ready to import.</span>
                </div>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center gap-2 px-5 py-3 border-t border-border bg-muted/30">
          {step !== 'scope' && (
            <button onClick={back} disabled={busy} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary disabled:opacity-50">
              <ChevronLeft className="w-3.5 h-3.5" /> Back
            </button>
          )}
          <button onClick={onClose} disabled={busy} className="px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary ml-auto disabled:opacity-50">
            Cancel
          </button>
          <button
            onClick={next}
            disabled={busy || (step === 'review' && blocked)}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold disabled:opacity-50"
          >
            {busy ? (step === 'period' ? 'Calculating estimate…' : 'Importing dataset…') : step === 'review' ? (<><Download className="w-3.5 h-3.5" /> Confirm import</>) : (<>Next <ChevronRight className="w-3.5 h-3.5" /></>)}
          </button>
        </footer>
      </div>
    </div>
  );
}

function Stepper({ current }: { current: Step }) {
  const steps: Array<{ id: Step; label: string }> = [
    { id: 'scope', label: 'Scope' },
    { id: 'period', label: 'Period' },
    { id: 'review', label: 'Review' },
  ];
  const currentIdx = steps.findIndex((s) => s.id === current);
  return (
    <ol className="flex items-center gap-1 px-5 pt-3" aria-label="Wizard progress">
      {steps.map((s, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        return (
          <li key={s.id} className="flex-1 flex items-center gap-2">
            <span className={cn(
              'h-5 w-5 rounded-full grid place-items-center text-[10px] font-bold border',
              done && 'bg-primary text-primary-foreground border-primary',
              active && 'border-primary text-primary',
              !done && !active && 'border-border text-muted-foreground'
            )}>
              {done ? '✓' : i + 1}
            </span>
            <span className={cn('text-xs', active ? 'font-semibold' : 'text-muted-foreground')}>{s.label}</span>
            {i < steps.length - 1 && <span className="flex-1 h-px bg-border ml-2" />}
          </li>
        );
      })}
    </ol>
  );
}