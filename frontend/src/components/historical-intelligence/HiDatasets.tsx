/* eslint-disable react-hooks/set-state-in-effect */
'use client';

import * as React from 'react';
import { Download, Trash2, Lock, Unlock, Save, RefreshCw, Check, X } from 'lucide-react';
import type {
  HpiDatasetCard, HpiDerivative, HpiPolicy, HpiSelectionEntry, HpiStorageReport, HpiUniverse,
} from '@/lib/types';
import { categoryLabel, autoDeleteStatus, coverageStatus } from '@/lib/historical-intelligence/labels';
import { fmtMb, fmtNumber, fmtDate, fmtRange } from '@/lib/historical-intelligence/format';
import { Panel } from './Panel';
import { StatusPill } from './StatusPill';
import { EmptyState } from './EmptyState';
import { StorageBar } from './StorageBar';
import { cn } from '@/lib/utils';

interface Props {
  universe: HpiUniverse | null;
  report: HpiStorageReport | null;
  selection: Record<string, HpiSelectionEntry>;
  policies: HpiPolicy[];
  dirty: boolean;
  saving: boolean;
  onToggle: (symbol: string, enabled: boolean) => void;
  onToggleCategory: (symbol: string, category: string, enabled: boolean) => void;
  onSaveSelection: () => void;
  onResetSelection: () => void;
  onToggleProtected: (policy: HpiPolicy) => void;
  onToggleAutoDelete: (policy: HpiPolicy) => void;
  onOpenImport: (symbol: string) => void;
  onOpenDelete: (symbol: string) => void;
}

export function HiDatasets(props: Props) {
  const {
    universe, report, selection, policies, dirty, saving,
    onToggle, onToggleCategory, onSaveSelection, onResetSelection,
    onToggleProtected, onToggleAutoDelete, onOpenImport, onOpenDelete,
  } = props;

  const [selectedSymbol, setSelectedSymbol] = React.useState<string>('');
  const derivatives = React.useMemo(() => universe?.derivatives ?? [], [universe]);
  const datasets = React.useMemo(() => report?.datasets ?? [], [report]);

  React.useEffect(() => {
    if (!selectedSymbol && derivatives.length > 0) {
      const first = datasets.find((d) => d.enabled)?.symbol ?? derivatives[0].symbol;
      setSelectedSymbol(first);
    }
  }, [derivatives, datasets, selectedSymbol]);

  const selectedDerivative = derivatives.find((d) => d.symbol === selectedSymbol);
  const selectedCard = datasets.find((d) => d.symbol === selectedSymbol);
  const selectedEntry = selection[selectedSymbol] ?? { symbol: selectedSymbol, enabled: false, data_categories: [] };
  const selectedPolicies = policies.filter((p) => p.instrument === selectedSymbol);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,18rem)_1fr] gap-4">
        {/* Master list */}
        <Panel title="Derivatives" description="Pick a row to view detail" bare>
          <ul className="divide-y divide-border/60">
            {derivatives.map((d) => {
              const card = datasets.find((ds) => ds.symbol === d.symbol);
              const isActive = selectedSymbol === d.symbol;
              const enabled = card?.enabled ?? false;
              const records = card?.records_stored ?? 0;
              const storage = card?.storage_used_mb ?? 0;
              return (
                <li key={d.symbol}>
                  <button
                    onClick={() => setSelectedSymbol(d.symbol)}
                    className={cn(
                      'w-full text-left flex items-center gap-2 px-3 py-2 rounded-md transition-colors',
                      isActive ? 'bg-primary/10 text-primary' : 'hover:bg-secondary/50'
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm truncate">{d.display_name}</span>
                        <StatusPill tone={enabled ? 'ok' : 'muted'} label={enabled ? 'ON' : 'OFF'} />
                      </div>
                      <div className="mt-1">
                        <StorageBar
                          currentMb={storage}
                          targetMb={report?.target_mb ?? 150}
                          warningMb={report?.warning_mb ?? 175}
                          hardCeilingMb={report?.hard_ceiling_mb ?? 200}
                          size="sm"
                        />
                      </div>
                    </div>
                    <span className="text-xs tabular-nums text-muted-foreground shrink-0">{records.toLocaleString()}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </Panel>

        {/* Detail */}
        <div className="space-y-3 min-w-0">
          {selectedDerivative ? (
            <DetailPanel
              derivative={selectedDerivative}
              card={selectedCard}
              entry={selectedEntry}
              policies={selectedPolicies}
              onToggle={(enabled) => onToggle(selectedDerivative.symbol, enabled)}
              onToggleCategory={(cat, enabled) => onToggleCategory(selectedDerivative.symbol, cat, enabled)}
              onOpenImport={() => onOpenImport(selectedDerivative.symbol)}
              onOpenDelete={() => onOpenDelete(selectedDerivative.symbol)}
              onToggleProtected={onToggleProtected}
              onToggleAutoDelete={onToggleAutoDelete}
            />
          ) : (
            <Panel title="Select a derivative" bare>
              <EmptyState title="Pick a derivative on the left" />
            </Panel>
          )}
        </div>
      </div>

      {/* Sticky save bar */}
      <div
        className={cn(
          'sticky bottom-0 z-30 -mx-4 sm:-mx-5 px-4 sm:px-5 py-3 border-t border-border bg-background/95 backdrop-blur transition-all',
          dirty ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2 pointer-events-none h-0 py-0 border-t-0 overflow-hidden'
        )}
        role="region"
        aria-label="Unsaved selection"
      >
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold">Unsaved changes</span>
          <span className="text-xs text-muted-foreground">Disabled derivatives stop importing and collecting.</span>
          <div className="ml-auto flex gap-2">
            <button
              onClick={onResetSelection}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs hover:bg-secondary"
            >
              <X className="w-3.5 h-3.5" /> Discard
            </button>
            <button
              onClick={onSaveSelection}
              disabled={saving}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold disabled:opacity-50"
            >
              <Save className="w-3.5 h-3.5" /> {saving ? 'Saving…' : 'Save selection'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface DetailProps {
  derivative: HpiDerivative;
  card: HpiDatasetCard | undefined;
  entry: HpiSelectionEntry;
  policies: HpiPolicy[];
  onToggle: (enabled: boolean) => void;
  onToggleCategory: (cat: string, enabled: boolean) => void;
  onOpenImport: () => void;
  onOpenDelete: () => void;
  onToggleProtected: (policy: HpiPolicy) => void;
  onToggleAutoDelete: (policy: HpiPolicy) => void;
}

function DetailPanel({ derivative, card, entry, policies, onToggle, onToggleCategory, onOpenImport, onOpenDelete, onToggleProtected, onToggleAutoDelete }: DetailProps) {
  const auto = autoDeleteStatus(card?.auto_delete_status ?? 'OFF');

  return (
    <Panel
      title={
        <span className="flex items-center gap-2">
          {derivative.display_name}
          <span className="text-xs font-normal text-muted-foreground">{derivative.symbol}</span>
        </span>
      }
      description={derivative.data_categories ? `${derivative.data_categories.length} data categories available` : ''}
      actions={
        <div className="flex gap-2">
          <button
            onClick={onOpenImport}
            disabled={!entry.enabled}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-secondary disabled:opacity-40"
          >
            <Download className="w-3.5 h-3.5" /> Import
          </button>
          <button
            onClick={onOpenDelete}
            disabled={!entry.enabled}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-xs font-medium hover:bg-red-500/10 hover:text-red-500 hover:border-red-500/30 disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" /> Delete
          </button>
        </div>
      }
      bare
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 cursor-pointer text-sm">
            <input
              type="checkbox"
              checked={entry.enabled}
              onChange={(e) => onToggle(e.target.checked)}
              className="w-4 h-4 accent-current"
            />
            <span className="font-semibold">{entry.enabled ? 'Tracking enabled' : 'Tracking disabled'}</span>
          </label>
          {card && (
            <StatusPill tone={auto.tone} label={auto.label} />
          )}
          {card?.protected && <StatusPill tone="primary" label="Protected" icon={<Lock className="w-3 h-3" />} />}
        </div>

        {card && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            <Stat label="Records" value={fmtNumber(card.records_stored)} />
            <Stat label="Storage" value={fmtMb(card.storage_used_mb)} />
            <Stat label="Period" value={card.historical_period_months != null ? `${card.historical_period_months} mo` : '—'} />
            <Stat label="Sampling" value={card.sampling_interval ?? '—'} />
            <Stat label="Oldest" value={fmtDate(card.oldest_record)} />
            <Stat label="Newest" value={fmtDate(card.newest_record)} />
            <Stat label="Enabled cats" value={String(card.data_categories_enabled.length)} />
            <Stat label="Status" value={
              <StatusPill
                tone={coverageStatus(card.enabled ? (card.records_stored > 0 ? 'FULL' : 'MISSING') : 'DISABLED').tone}
                label={coverageStatus(card.enabled ? (card.records_stored > 0 ? 'FULL' : 'MISSING') : 'DISABLED').label}
              />
            } />
          </div>
        )}

        {entry.enabled && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">Data categories</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {derivative.data_categories.map((cat) => {
                const checked = entry.data_categories.includes(cat);
                const stat = card?.category_stats.find((c) => c.category === cat);
                return (
                  <label key={cat} className="flex items-center gap-2 rounded-md border border-border bg-background p-2 cursor-pointer hover:bg-secondary/40">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => onToggleCategory(cat, e.target.checked)}
                      className="w-3.5 h-3.5"
                    />
                    <span className="text-xs flex-1">{categoryLabel(cat)}</span>
                    {stat && stat.records > 0 && (
                      <span className="text-[10px] text-muted-foreground tabular-nums">{fmtNumber(stat.records)} · {fmtMb(stat.storage_mb)}</span>
                    )}
                    {stat?.protected && <Lock className="w-3 h-3 text-amber-600" />}
                  </label>
                );
              })}
            </div>
          </div>
        )}

        {card && card.category_stats.some((c) => c.records > 0) && (
          <div>
            <p className="text-xs font-semibold text-muted-foreground mb-2">Retention & protection</p>
            <ul className="space-y-1.5">
              {card.category_stats.filter((c) => c.records > 0).map((c) => {
                const pol = policies.find((p) => p.feature_group === c.category);
                return (
                  <li key={c.category} className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-xs">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{categoryLabel(c.category)}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {fmtNumber(c.records)} rec · {fmtMb(c.storage_mb)} · {fmtRange(c.oldest, c.newest)}
                      </p>
                    </div>
                    {pol ? (
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => onToggleAutoDelete(pol)}
                          className={cn(
                            'px-2 py-1 rounded-md border text-[10px] font-medium',
                            pol.auto_delete_enabled
                              ? 'bg-green-500/10 text-green-600 border-green-500/30'
                              : 'border-border text-muted-foreground hover:bg-secondary'
                          )}
                          title="Toggle auto-delete"
                        >
                          {pol.auto_delete_enabled ? <><Check className="w-3 h-3 inline" /> Auto</> : 'Auto off'}
                        </button>
                        <button
                          onClick={() => onToggleProtected(pol)}
                          className={cn(
                            'px-2 py-1 rounded-md border text-[10px] font-medium inline-flex items-center gap-1',
                            pol.protected
                              ? 'bg-amber-500/10 text-amber-600 border-amber-500/30'
                              : 'border-border text-muted-foreground hover:bg-secondary'
                          )}
                          title="Toggle protected"
                        >
                          {pol.protected ? <Lock className="w-3 h-3" /> : <Unlock className="w-3 h-3" />}
                          {pol.protected ? 'Protected' : 'Unprotected'}
                        </button>
                      </div>
                    ) : (
                      <span className="text-[10px] text-muted-foreground">No policy</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {card?.category_stats.some((c) => c.records > 0) && (
          <p className="text-[10px] text-muted-foreground inline-flex items-center gap-1">
            <RefreshCw className="w-3 h-3" /> Toggle protection requires explicit opt-in before any auto-delete can touch it.
          </p>
        )}
      </div>
    </Panel>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md bg-muted/50 p-2">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <div className="font-semibold text-sm mt-0.5">{value}</div>
    </div>
  );
}