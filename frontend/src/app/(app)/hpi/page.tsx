'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type {
  HpiAuditEntry, HpiDeletePreview, HpiDerivative, HpiImportPreview,
  HpiImportResult, HpiPolicy, HpiSelectionEntry, HpiStorageReport, HpiUniverse,
} from '@/lib/types';
import { DerivativeSelectionPanel } from '@/components/hpi/DerivativeSelectionPanel';
import { StorageBudgetBar } from '@/components/hpi/StorageBudgetBar';
import { DataManagementPanel } from '@/components/hpi/DataManagementPanel';
import { ImportDialog } from '@/components/hpi/ImportDialog';
import { DeleteDialog } from '@/components/hpi/DeleteDialog';
import { PatternAnalysisPanel } from '@/components/hpi/PatternAnalysisPanel';

export default function HpiPage() {
  const [universe, setUniverse] = useState<HpiUniverse | null>(null);
  const [selection, setSelection] = useState<Record<string, HpiSelectionEntry>>({});
  const [report, setReport] = useState<HpiStorageReport | null>(null);
  const [policies, setPolicies] = useState<HpiPolicy[]>([]);
  const [audit, setAudit] = useState<HpiAuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const [importSymbol, setImportSymbol] = useState<string | null>(null);
  const [deleteSymbol, setDeleteSymbol] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [u, s, r, p, a] = await Promise.all([
        api.getHpiUniverse(),
        api.getHpiSelection(),
        api.getHpiStorageReport(),
        api.listHpiPolicies(),
        api.getHpiAudit(),
      ]);
      setUniverse(u.data);
      setSelection(Object.fromEntries(s.data.entries.map((e) => [e.symbol, e])));
      setReport(r.data);
      setPolicies(p.data);
      setAudit(a.data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load HPI data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const refresh = () => { setRefreshKey((k) => k + 1); loadAll(); };

  const saveSelection = async () => {
    setSaving(true); setError(null);
    try {
      await api.updateHpiSelection(Object.values(selection));
      setNotice('Derivative selection saved. Disabled derivatives stop importing, collecting, and confirming.');
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save selection');
    } finally {
      setSaving(false);
    }
  };

  const toggle = (symbol: string, enabled: boolean) => {
    const entry = selection[symbol] ?? { symbol, enabled: false, data_categories: [] };
    setSelection({ ...selection, [symbol]: { ...entry, enabled, data_categories: enabled ? entry.data_categories : [] } });
  };

  const toggleCategory = (symbol: string, category: string, enabled: boolean) => {
    const entry = selection[symbol] ?? { symbol, enabled: true, data_categories: [] };
    const cats = enabled ? [...entry.data_categories, category] : entry.data_categories.filter((c) => c !== category);
    setSelection({ ...selection, [symbol]: { ...entry, enabled: true, data_categories: cats } });
  };

  const runImport = async (req: Record<string, unknown>, estimateOnly: boolean) => {
    try {
      const res = await api.hpiImport(req);
      const data = res.data as HpiImportPreview | HpiImportResult;
      if (estimateOnly || 'breakdown' in data) {
        return { preview: data as HpiImportPreview };
      }
      setNotice(`Imported ${data.records_imported.toLocaleString()} records for ${(data as HpiImportResult).symbol} (+${(data as HpiImportResult).storage_added_mb} MB).`);
      refresh();
      return { result: data as HpiImportResult };
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Import failed' };
    }
  };

  const runPreview = async (req: Record<string, unknown>) => {
    try {
      const res = await api.hpiDeletePreview(req);
      return { preview: res.data };
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Preview failed' };
    }
  };

  const runConfirm = async (token: string, reason: string) => {
    try {
      const res = await api.hpiDeleteConfirm(token, reason);
      setNotice(`Deleted ${res.data.records_deleted.toLocaleString()} records, released ${res.data.storage_released_mb} MB. Deletion recorded in audit log.`);
      refresh();
      return {};
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Delete failed' };
    }
  };

  const toggleProtected = async (policy: HpiPolicy) => {
    try {
      await api.updateHpiPolicy(policy.policy_id, { protected: !policy.protected });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Policy update failed');
    }
  };

  const toggleAutoDelete = async (policy: HpiPolicy) => {
    try {
      await api.updateHpiPolicy(policy.policy_id, { auto_delete_enabled: !policy.auto_delete_enabled });
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Policy update failed');
    }
  };

  const derivativeFor = (sym: string): HpiDerivative | undefined =>
    universe?.derivatives.find((d) => d.symbol === sym);

  return (
    <div className="space-y-4 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold">Historical Pattern Intelligence (HPI)</h1>
        <p className="text-xs text-muted-foreground">
          User-controlled derivative & historical data: which derivatives → which datasets → which period → which sampling → what is protected → what is deleted.
        </p>
      </div>

      {error && <div className="bg-red-500/10 border border-red-500/30 text-red-500 text-xs rounded-lg p-3">{error}</div>}
      {notice && <div className="bg-green-500/10 border border-green-500/30 text-green-600 text-xs rounded-lg p-3">{notice}</div>}
      {loading && !report && <p className="text-xs text-muted-foreground">Loading…</p>}

      <StorageBudgetBar report={report} />

      <DerivativeSelectionPanel
        universe={universe?.derivatives ?? []}
        selection={selection}
        onToggle={toggle}
        onToggleCategory={toggleCategory}
        onSave={saveSelection}
        saving={saving}
      />

      <DataManagementPanel
        datasets={report?.datasets ?? []}
        policies={policies}
        onToggleProtected={toggleProtected}
        onToggleAutoDelete={toggleAutoDelete}
        onImport={(sym) => setImportSymbol(sym)}
        onDelete={(sym) => setDeleteSymbol(sym)}
      />

      <PatternAnalysisPanel universe={universe} selection={selection} report={report} refreshKey={refreshKey} />

      {audit.length > 0 && (
        <div className="bg-card border border-border rounded-xl p-4">
          <h2 className="text-base font-bold mb-2">Deletion Audit Log</h2>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {audit.slice(0, 30).map((a) => (
              <div key={a.deletion_id} className="flex items-center gap-2 text-[11px] bg-muted/50 rounded px-2 py-1">
                <span className="font-semibold">{a.derivative}</span>
                <span>{a.dataset.replace(/_/g, ' ')}</span>
                <span className="text-muted-foreground">{new Date(a.start_date).toLocaleDateString()} → {new Date(a.end_date).toLocaleDateString()}</span>
                <span>{a.records_deleted.toLocaleString()} rec · {a.storage_released_mb} MB</span>
                <span className="ml-auto text-muted-foreground">{a.reason} · {new Date(a.timestamp).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {importSymbol && (
        <ImportDialog
          symbol={importSymbol}
          derivative={derivativeFor(importSymbol)}
          selectedCategories={selection[importSymbol]?.data_categories ?? []}
          samplingIntervals={universe?.sampling_intervals ?? ['1m', '5m', '15m', '1h', '1D']}
          onClose={() => setImportSymbol(null)}
          onDone={() => { setImportSymbol(null); refresh(); }}
          onImport={runImport}
        />
      )}

      {deleteSymbol && (
        <DeleteDialog
          symbol={deleteSymbol}
          derivative={derivativeFor(deleteSymbol)}
          onClose={() => setDeleteSymbol(null)}
          onDone={() => { setDeleteSymbol(null); refresh(); }}
          onPreview={runPreview}
          onConfirm={runConfirm}
        />
      )}
    </div>
  );
}
