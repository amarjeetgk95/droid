'use client';

import * as React from 'react';
import { api } from '@/lib/api';
import type {
  HpiAuditEntry, HpiDerivative, HpiImportPreview, HpiImportResult,
  HpiPolicy, HpiSelectionEntry, HpiStorageReport, HpiUniverse,
} from '@/lib/types';
import { ToastProvider, useToast } from '@/lib/historical-intelligence/toast';
import { HiSectionNav, hiSectionMeta, type HiSectionId } from '@/components/historical-intelligence/HiSectionNav';
import { HiTopStrip } from '@/components/historical-intelligence/HiTopStrip';
import { HiOverview } from '@/components/historical-intelligence/HiOverview';
import { HiDatasets } from '@/components/historical-intelligence/HiDatasets';
import { HiPatterns } from '@/components/historical-intelligence/HiPatterns';
import { HiShifts } from '@/components/historical-intelligence/HiShifts';
import { HiSeasonality } from '@/components/historical-intelligence/HiSeasonality';
import { HiWatchlist } from '@/components/historical-intelligence/HiWatchlist';
import { HiAudit } from '@/components/historical-intelligence/HiAudit';
import { ImportWizard } from '@/components/historical-intelligence/wizards/ImportWizard';
import { DeleteWizard } from '@/components/historical-intelligence/wizards/DeleteWizard';
import { Database, Sparkles } from 'lucide-react';

function HistoricalIntelligencePageInner() {
  const { toast } = useToast();
  const [section, setSection] = React.useState<HiSectionId>('overview');
  const [universe, setUniverse] = React.useState<HpiUniverse | null>(null);
  const [selection, setSelection] = React.useState<Record<string, HpiSelectionEntry>>({});
  const [savedSelection, setSavedSelection] = React.useState<Record<string, HpiSelectionEntry>>({});
  const [report, setReport] = React.useState<HpiStorageReport | null>(null);
  const [policies, setPolicies] = React.useState<HpiPolicy[]>([]);
  const [audit, setAudit] = React.useState<HpiAuditEntry[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [, setRefreshing] = React.useState(false);
  const [savingSelection, setSavingSelection] = React.useState(false);
  const [importSymbol, setImportSymbol] = React.useState<string | null>(null);
  const [deleteSymbol, setDeleteSymbol] = React.useState<string | null>(null);
  const [analysisSymbol, setAnalysisSymbol] = React.useState<string>('');

  const loadAll = React.useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [u, s, r, p, a] = await Promise.all([
        api.getHpiUniverse(),
        api.getHpiSelection(),
        api.getHpiStorageReport(),
        api.listHpiPolicies(),
        api.getHpiAudit(),
      ]);
      setUniverse(u.data);
      const map = Object.fromEntries(s.data.entries.map((e) => [e.symbol, e]));
      setSelection(map);
      setSavedSelection(map);
      setReport(r.data);
      setPolicies(p.data);
      setAudit(a.data);
      setAnalysisSymbol((cur) => cur || u.data.derivatives[0]?.symbol || '');
    } catch (err) {
      toast({ tone: 'danger', title: 'Failed to load', description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [toast]);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAll();
  }, [loadAll]);

  const refresh = React.useCallback(() => loadAll(true), [loadAll]);

  const dirty = React.useMemo(() => JSON.stringify(selection) !== JSON.stringify(savedSelection), [selection, savedSelection]);

  const toggle = (symbol: string, enabled: boolean) => {
    const entry = selection[symbol] ?? { symbol, enabled: false, data_categories: [] };
    setSelection({ ...selection, [symbol]: { ...entry, enabled, data_categories: enabled ? entry.data_categories : [] } });
  };

  const toggleCategory = (symbol: string, category: string, enabled: boolean) => {
    const entry = selection[symbol] ?? { symbol, enabled: true, data_categories: [] };
    const cats = enabled ? Array.from(new Set([...entry.data_categories, category])) : entry.data_categories.filter((c) => c !== category);
    setSelection({ ...selection, [symbol]: { ...entry, enabled: true, data_categories: cats } });
  };

  const saveSelection = async () => {
    setSavingSelection(true);
    try {
      const res = await api.updateHpiSelection(Object.values(selection));
      const map = Object.fromEntries(res.data.entries.map((e) => [e.symbol, e]));
      setSelection(map);
      setSavedSelection(map);
      toast({ tone: 'ok', title: 'Selection saved', description: 'Disabled derivatives stopped importing and collecting.' });
      refresh();
    } catch (err) {
      toast({ tone: 'danger', title: 'Save failed', description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setSavingSelection(false);
    }
  };

  const resetSelection = () => { setSelection(savedSelection); };

  const toggleProtected = async (policy: HpiPolicy) => {
    try {
      await api.updateHpiPolicy(policy.policy_id, { protected: !policy.protected });
      toast({ tone: 'info', title: policy.protected ? 'Unprotected' : 'Protected', description: `${policy.instrument} / ${policy.feature_group}` });
      refresh();
    } catch (err) {
      toast({ tone: 'danger', title: 'Policy update failed', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  };

  const toggleAutoDelete = async (policy: HpiPolicy) => {
    try {
      await api.updateHpiPolicy(policy.policy_id, { auto_delete_enabled: !policy.auto_delete_enabled });
      toast({ tone: 'info', title: policy.auto_delete_enabled ? 'Auto-delete OFF' : 'Auto-delete ON', description: `${policy.instrument} / ${policy.feature_group}` });
      refresh();
    } catch (err) {
      toast({ tone: 'danger', title: 'Policy update failed', description: err instanceof Error ? err.message : 'Unknown error' });
    }
  };

  const runImport = async (req: Record<string, unknown>, estimateOnly: boolean) => {
    try {
      const res = await api.hpiImport(req);
      const data = res.data as HpiImportPreview | HpiImportResult;
      if (estimateOnly || 'breakdown' in data) {
        return { preview: data as HpiImportPreview };
      }
      toast({
        tone: 'ok',
        title: `Imported ${data.records_imported.toLocaleString()} records`,
        description: `${data.symbol} (+${data.storage_added_mb} MB).`,
      });
      refresh();
      return { result: data as HpiImportResult };
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Import failed' };
    }
  };

  const runDeletePreview = async (req: Record<string, unknown>) => {
    try {
      const res = await api.hpiDeletePreview(req);
      return { preview: res.data };
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Preview failed' };
    }
  };

  const runDeleteConfirm = async (token: string, reason: string) => {
    try {
      const res = await api.hpiDeleteConfirm(token, reason);
      toast({
        tone: 'ok',
        title: `Deleted ${res.data.records_deleted.toLocaleString()} records`,
        description: `Released ${res.data.storage_released_mb} MB. Recorded in audit log.`,
      });
      refresh();
      return {};
    } catch (err) {
      return { error: err instanceof Error ? err.message : 'Delete failed' };
    }
  };

  const derivativeFor = (sym: string): HpiDerivative | undefined =>
    universe?.derivatives.find((d) => d.symbol === sym);

  const derivatives = universe?.derivatives ?? [];
  const meta = hiSectionMeta(section);

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      <header className="flex items-start gap-3">
        <Database className="w-6 h-6 text-primary mt-0.5 shrink-0" />
        <div className="min-w-0">
          <h1 className="text-xl font-bold">Historical Intelligence</h1>
          <p className="text-xs text-muted-foreground">
            Derivatives → datasets → period → sampling → protection → analysis. {meta.description}.
          </p>
        </div>
      </header>

      <HiTopStrip report={report} loading={loading} />

      <div className="flex flex-col lg:flex-row gap-4">
        <HiSectionNav active={section} onSelect={setSection} />
        <div className="flex-1 min-w-0 space-y-4">
          {section === 'overview' && (
            <HiOverview
              universe={universe}
              report={report}
              audit={audit}
              loading={loading}
              onJumpToSection={setSection}
              onOpenImport={(s) => setImportSymbol(s)}
            />
          )}
          {section === 'datasets' && (
            <HiDatasets
              universe={universe}
              report={report}
              selection={selection}
              policies={policies}
              dirty={dirty}
              saving={savingSelection}
              onToggle={toggle}
              onToggleCategory={toggleCategory}
              onSaveSelection={saveSelection}
              onResetSelection={resetSelection}
              onToggleProtected={toggleProtected}
              onToggleAutoDelete={toggleAutoDelete}
              onOpenImport={(s) => setImportSymbol(s)}
              onOpenDelete={(s) => setDeleteSymbol(s)}
            />
          )}
          {section === 'patterns' && (
            <div className="space-y-4">
              <SymbolPicker derivatives={derivatives} value={analysisSymbol} onChange={setAnalysisSymbol} />
              <HiPatterns universe={universe} report={report} refreshKey={audit.length + policies.length} />
            </div>
          )}
          {section === 'shifts' && (
            <div className="space-y-4">
              <SymbolPicker derivatives={derivatives} value={analysisSymbol} onChange={setAnalysisSymbol} />
              <HiShifts symbol={analysisSymbol} />
            </div>
          )}
          {section === 'seasonality' && (
            <div className="space-y-4">
              <SymbolPicker derivatives={derivatives} value={analysisSymbol} onChange={setAnalysisSymbol} />
              <HiSeasonality symbol={analysisSymbol} />
            </div>
          )}
          {section === 'watchlist' && <HiWatchlist />}
          {section === 'audit' && <HiAudit audit={audit} />}
        </div>
      </div>

      {importSymbol && (
        <ImportWizard
          symbol={importSymbol}
          derivative={derivativeFor(importSymbol)}
          initialCategories={selection[importSymbol]?.data_categories ?? []}
          initialSampling="5m"
          samplingIntervals={universe?.sampling_intervals ?? ['1m', '5m', '15m', '1h', '1D']}
          storageBudget={{
            target_mb: report?.target_mb ?? 150,
            warning_mb: report?.warning_mb ?? 175,
            hard_ceiling_mb: report?.hard_ceiling_mb ?? 200,
            current_mb: report?.current_storage_mb ?? 0,
          }}
          onClose={() => setImportSymbol(null)}
          onImport={runImport}
        />
      )}

      {deleteSymbol && (
        <DeleteWizard
          symbol={deleteSymbol}
          derivative={derivativeFor(deleteSymbol)}
          onClose={() => setDeleteSymbol(null)}
          onPreview={runDeletePreview}
          onConfirm={runDeleteConfirm}
        />
      )}
    </div>
  );
}

function SymbolPicker({ derivatives, value, onChange }: { derivatives: HpiDerivative[]; value: string; onChange: (s: string) => void }) {
  if (derivatives.length === 0) return null;
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-card px-4 py-2 text-sm">
      <Sparkles className="w-4 h-4 text-primary" />
      <span className="text-xs text-muted-foreground">Analyse for</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className="ml-auto bg-secondary/50 border border-border rounded-md px-2 py-1 text-xs">
        {derivatives.map((d) => (
          <option key={d.symbol} value={d.symbol}>{d.display_name}</option>
        ))}
      </select>
    </div>
  );
}

export default function HistoricalIntelligencePage() {
  return (
    <ToastProvider>
      <HistoricalIntelligencePageInner />
    </ToastProvider>
  );
}