'use client';

import { ShieldCheck, Download, Trash2, Lock, Unlock } from 'lucide-react';
import type { HpiDatasetCard, HpiPolicy } from '@/lib/types';

interface Props {
  datasets: HpiDatasetCard[];
  policies: HpiPolicy[];
  onToggleProtected: (policy: HpiPolicy) => void;
  onToggleAutoDelete: (policy: HpiPolicy) => void;
  onImport: (symbol: string) => void;
  onDelete: (symbol: string) => void;
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

export function DataManagementPanel({ datasets, policies, onToggleProtected, onToggleAutoDelete, onImport, onDelete }: Props) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-base font-bold mb-1">Derivative Data Management</h2>
      <p className="text-xs text-muted-foreground mb-3">Per-derivative datasets. Protected datasets are never auto-deleted; deletions always require explicit confirmation.</p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {datasets.map((d) => (
          <div key={d.symbol} className={`rounded-lg border p-3 ${d.enabled ? 'border-border' : 'border-border/50 opacity-70'}`}>
            <div className="flex items-center gap-2 mb-2">
              <span className="font-bold text-sm">{d.symbol}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted">{d.enabled ? 'ENABLED' : 'DISABLED'}</span>
              {d.protected && <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 flex items-center gap-1"><ShieldCheck className="w-3 h-3" />PROTECTED</span>}
              <div className="ml-auto flex gap-1">
                <button onClick={() => onImport(d.symbol)} disabled={!d.enabled} title="Import history"
                  className="p-1.5 rounded-md border border-border hover:bg-secondary disabled:opacity-40"><Download className="w-3.5 h-3.5" /></button>
                <button onClick={() => onDelete(d.symbol)} disabled={!d.enabled} title="Delete historical data"
                  className="p-1.5 rounded-md border border-border hover:bg-red-500/10 hover:text-red-500 disabled:opacity-40"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px]">
              <div className="flex justify-between"><span className="text-muted-foreground">Categories</span><span>{d.data_categories_enabled.length}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Historical period</span><span>{d.historical_period_months != null ? `${d.historical_period_months} mo` : '—'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Sampling</span><span>{d.sampling_interval ?? '—'}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Records stored</span><span>{d.records_stored.toLocaleString()}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Storage used</span><span>{d.storage_used_mb.toFixed(2)} MB</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Auto delete</span><span>{d.auto_delete_status}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Oldest record</span><span>{fmtDate(d.oldest_record)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Newest record</span><span>{fmtDate(d.newest_record)}</span></div>
            </div>
            {d.category_stats.some((c) => c.records > 0) && (
              <div className="mt-2 border-t border-border pt-2 space-y-1">
                {d.category_stats.filter((c) => c.records > 0).map((c) => {
                  const pol = policies.find((p) => p.instrument === d.symbol && p.feature_group === c.category);
                  return (
                    <div key={c.category} className="flex items-center gap-2 text-[11px]">
                      <span className="w-28 text-muted-foreground">{c.label}</span>
                      <span>{c.records.toLocaleString()} rec · {c.storage_mb.toFixed(2)} MB</span>
                      <div className="ml-auto flex gap-1">
                        {pol ? (
                          <>
                            <button onClick={() => onToggleAutoDelete(pol)}
                              className={`px-1.5 py-0.5 rounded text-[10px] border ${pol.auto_delete_enabled ? 'bg-green-500/10 text-green-600 border-green-500/30' : 'text-muted-foreground'}`}
                              title="Toggle auto-delete">Auto: {pol.auto_delete_enabled ? 'ON' : 'OFF'}</button>
                            <button onClick={() => onToggleProtected(pol)}
                              className={`px-1.5 py-0.5 rounded text-[10px] border flex items-center gap-1 ${pol.protected ? 'bg-amber-500/10 text-amber-600 border-amber-500/30' : 'text-muted-foreground'}`}
                              title="Toggle protected">
                              {pol.protected ? <Lock className="w-2.5 h-2.5" /> : <Unlock className="w-2.5 h-2.5" />}
                              {pol.protected ? 'Protected' : 'Unprotected'}</button>
                          </>
                        ) : (
                          <span className="text-[10px] text-muted-foreground">no policy</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
