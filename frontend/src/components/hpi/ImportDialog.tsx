'use client';

import { useState } from 'react';
import { X, Download, AlertTriangle } from 'lucide-react';
import type { HpiDerivative, HpiImportPreview, HpiImportResult } from '@/lib/types';

interface Props {
  symbol: string;
  derivative: HpiDerivative | undefined;
  selectedCategories: string[];
  samplingIntervals: string[];
  onClose: () => void;
  onDone: () => void;
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
  { label: 'Custom date range', days: 0 },
];

export function ImportDialog({ symbol, derivative, selectedCategories, samplingIntervals, onClose, onDone, onImport }: Props) {
  const [categories, setCategories] = useState<string[]>(selectedCategories);
  const [period, setPeriod] = useState(PERIODS[2]);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [sampling, setSampling] = useState('5m');
  const [preview, setPreview] = useState<HpiImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildRequest = (estimateOnly: boolean): Record<string, unknown> => {
    const req: Record<string, unknown> = { symbol, categories, sampling_interval: sampling, estimate_only: estimateOnly };
    if (period.days === 0) {
      if (startDate) req.start_date = new Date(startDate).toISOString();
      if (endDate) req.end_date = new Date(endDate).toISOString();
    } else {
      req.retention_days = period.days;
    }
    return req;
  };

  const runEstimate = async () => {
    setBusy(true); setError(null); setPreview(null);
    const res = await onImport(buildRequest(true), true);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    setPreview(res.preview ?? null);
  };

  const runImport = async () => {
    setBusy(true); setError(null);
    const res = await onImport(buildRequest(false), false);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    onDone();
  };

  const blocked = preview?.blocked ?? false;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold">Import Historical Data — {derivative?.display_name ?? symbol}</h3>
          <button onClick={onClose} className="p-1 hover:bg-secondary rounded"><X className="w-4 h-4" /></button>
        </div>

        <label className="block text-xs font-semibold mb-1">Data categories</label>
        <div className="grid grid-cols-2 gap-1 mb-3">
          {(derivative?.data_categories ?? []).map((cat) => (
            <label key={cat} className="flex items-center gap-1.5 text-xs cursor-pointer">
              <input type="checkbox" className="w-3 h-3" checked={categories.includes(cat)}
                onChange={(e) => setCategories(e.target.checked ? [...categories, cat] : categories.filter((c) => c !== cat))} />
              {cat.replace(/_/g, ' ')}
            </label>
          ))}
        </div>

        <label className="block text-xs font-semibold mb-1">Historical period</label>
        <select value={period.label} onChange={(e) => setPeriod(PERIODS.find((p) => p.label === e.target.value)!)}
          className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1.5 text-xs mb-2">
          {PERIODS.map((p) => <option key={p.label} value={p.label}>{p.label}</option>)}
        </select>
        {period.days === 0 && (
          <div className="grid grid-cols-2 gap-2 mb-2">
            <div>
              <label className="block text-[10px] text-muted-foreground">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1 text-xs" />
            </div>
            <div>
              <label className="block text-[10px] text-muted-foreground">End date</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1 text-xs" />
            </div>
          </div>
        )}

        <label className="block text-xs font-semibold mb-1">Sampling interval</label>
        <select value={sampling} onChange={(e) => setSampling(e.target.value)} className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1.5 text-xs mb-3">
          {samplingIntervals.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        {preview && (
          <div className={`rounded-lg border p-3 mb-3 text-xs ${blocked ? 'border-red-500/50 bg-red-500/5' : 'border-border bg-muted/30'}`}>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mb-1">
              <div className="flex justify-between"><span className="text-muted-foreground">Current storage</span><span>{preview.current_storage_mb} MB</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Requested addition</span><span>{preview.requested_addition_mb} MB</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Projected storage</span><span className="font-semibold">{preview.projected_storage_mb} MB</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Status</span><span className="font-semibold">{preview.status.replace('_', ' ')}</span></div>
            </div>
            {preview.breakdown.map((b) => (
              <div key={b.category} className="flex justify-between text-[11px] text-muted-foreground">
                <span>{b.label} ({b.sampling_interval})</span><span>{b.estimated_records.toLocaleString()} rec · {b.estimated_mb} MB</span>
              </div>
            ))}
            {preview.warnings.map((w) => (
              <p key={w} className="text-amber-600 mt-1 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</p>
            ))}
            {blocked && (
              <div className="mt-2">
                <p className="font-semibold text-red-500">Blocked — projected storage exceeds the hard ceiling. Choose an alternative:</p>
                <ul className="list-disc list-inside text-muted-foreground mt-1">
                  {preview.alternatives.map((a) => <li key={a}>{a}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
        {error && <p className="text-xs text-red-500 mb-2">{error}</p>}

        <div className="flex justify-end gap-2">
          {!preview && (
            <button onClick={runEstimate} disabled={busy || categories.length === 0}
              className="border border-border px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-secondary disabled:opacity-50">
              {busy ? 'Estimating…' : 'Review Estimated Storage'}
            </button>
          )}
          {preview && !blocked && (
            <button onClick={runImport} disabled={busy}
              className="bg-primary text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 disabled:opacity-50">
              <Download className="w-3.5 h-3.5" />{busy ? 'Importing…' : 'Confirm & Import'}
            </button>
          )}
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-secondary">Cancel</button>
        </div>
      </div>
    </div>
  );
}
