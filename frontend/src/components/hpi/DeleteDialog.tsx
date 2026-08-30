'use client';

import { useState } from 'react';
import { X, Trash2, AlertTriangle, ShieldCheck } from 'lucide-react';
import type { HpiDeletePreview, HpiDerivative } from '@/lib/types';

interface Props {
  symbol: string;
  derivative: HpiDerivative | undefined;
  onClose: () => void;
  onDone: () => void;
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

export function DeleteDialog({ symbol, derivative, onClose, onDone, onPreview, onConfirm }: Props) {
  const [categories, setCategories] = useState<string[]>([]);
  const [rangeType, setRangeType] = useState('last_30_days');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [allowProtected, setAllowProtected] = useState(false);
  const [preview, setPreview] = useState<HpiDeletePreview | null>(null);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const runPreview = async () => {
    setBusy(true); setError(null); setPreview(null);
    const res = await onPreview(buildReq());
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    setPreview(res.preview ?? null);
  };

  const runConfirm = async () => {
    if (!preview) return;
    setBusy(true); setError(null);
    const res = await onConfirm(preview.confirmation_token, reason);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    onDone();
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-card border border-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-red-500">Delete Historical Data — {derivative?.display_name ?? symbol}</h3>
          <button onClick={onClose} className="p-1 hover:bg-secondary rounded"><X className="w-4 h-4" /></button>
        </div>

        <label className="block text-xs font-semibold mb-1">Datasets to delete</label>
        <div className="grid grid-cols-2 gap-1 mb-3">
          {(derivative?.data_categories ?? []).map((cat) => (
            <label key={cat} className="flex items-center gap-1.5 text-xs cursor-pointer">
              <input type="checkbox" className="w-3 h-3" checked={categories.includes(cat)}
                onChange={(e) => setCategories(e.target.checked ? [...categories, cat] : categories.filter((c) => c !== cat))} />
              {cat.replace(/_/g, ' ')}
            </label>
          ))}
        </div>

        <label className="block text-xs font-semibold mb-1">Date range</label>
        <select value={rangeType} onChange={(e) => { setRangeType(e.target.value); setPreview(null); }}
          className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1.5 text-xs mb-2">
          {RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        {rangeType === 'custom' && (
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

        <label className="block text-xs font-semibold mb-1">Reason (recorded in audit log)</label>
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. cleanup before 2025"
          className="w-full bg-secondary/50 border border-border rounded-lg px-2 py-1.5 text-xs mb-3" />

        {preview && (
          <div className="rounded-lg border border-red-500/40 bg-red-500/5 p-3 mb-3 text-xs">
            <p className="font-bold mb-1 flex items-center gap-1"><AlertTriangle className="w-3.5 h-3.5" />Confirm deletion</p>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              <div className="flex justify-between"><span className="text-muted-foreground">Derivative</span><span>{preview.symbol}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Datasets</span><span>{preview.categories.map((c) => c.replace(/_/g, ' ')).join(', ')}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Date range</span>
                <span>{new Date(preview.range_start).toLocaleDateString()} → {new Date(preview.range_end).toLocaleDateString()}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Records</span><span>{preview.total_records.toLocaleString()}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Storage released</span><span>{preview.total_storage_mb} MB</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Price/technical history</span><span className="text-green-600">{preview.price_technical_impact.split('—')[0].trim()}</span></div>
            </div>
            <div className="mt-2 border-t border-red-500/20 pt-2">
              <p className="font-semibold text-red-500">Historical-analysis impact:</p>
              <ul className="list-disc list-inside text-muted-foreground">
                {preview.analytical_impact.map((i) => <li key={i}>{i}</li>)}
              </ul>
            </div>
            {preview.protected_categories.length > 0 && (
              <p className="mt-2 flex items-start gap-1 text-amber-600">
                <ShieldCheck className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                Protected datasets ({preview.protected_categories.map((c) => c.replace(/_/g, ' ')).join(', ')}) will be skipped
                {allowProtected ? ' unless "include protected" is checked.' : '.'}
              </p>
            )}
          </div>
        )}
        {error && <p className="text-xs text-red-500 mb-2">{error}</p>}

        {preview && preview.protected_categories.length > 0 && (
          <label className="flex items-center gap-2 text-xs mb-2 cursor-pointer">
            <input type="checkbox" className="w-3 h-3" checked={allowProtected} onChange={(e) => setAllowProtected(e.target.checked)} />
            Include protected datasets (explicit override)
          </label>
        )}

        <div className="flex justify-end gap-2">
          {!preview && (
            <button onClick={runPreview} disabled={busy || categories.length === 0}
              className="border border-border px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-secondary disabled:opacity-50">
              {busy ? 'Preparing…' : 'Preview Records & Impact'}
            </button>
          )}
          {preview && (
            <button onClick={runConfirm} disabled={busy}
              className="bg-red-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 disabled:opacity-50">
              <Trash2 className="w-3.5 h-3.5" />{busy ? 'Deleting…' : 'Confirm Delete'}
            </button>
          )}
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-secondary">Cancel</button>
        </div>
      </div>
    </div>
  );
}
