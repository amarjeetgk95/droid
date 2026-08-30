'use client';

import type { HpiDerivative, HpiSelectionEntry } from '@/lib/types';

interface Props {
  universe: HpiDerivative[];
  selection: Record<string, HpiSelectionEntry>;
  onToggle: (symbol: string, enabled: boolean) => void;
  onToggleCategory: (symbol: string, category: string, enabled: boolean) => void;
  onSave: () => void;
  saving: boolean;
}

export function DerivativeSelectionPanel({ universe, selection, onToggle, onToggleCategory, onSave, saving }: Props) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-bold">Derivative Selection</h2>
          <p className="text-xs text-muted-foreground">Fixed universe of 7 derivatives. Disabled derivatives: no import, no collection, no derivative confirmation — existing data is kept.</p>
        </div>
        <button onClick={onSave} disabled={saving} className="bg-primary text-primary-foreground text-xs font-semibold px-3 py-1.5 rounded-lg disabled:opacity-50">
          {saving ? 'Saving…' : 'Save Selection'}
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {universe.map((d) => {
          const entry = selection[d.symbol] ?? { symbol: d.symbol, enabled: false, data_categories: [] };
          return (
            <div key={d.symbol} className={`rounded-lg border p-3 ${entry.enabled ? 'border-primary/60 bg-primary/5' : 'border-border'}`}>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={entry.enabled} onChange={(e) => onToggle(d.symbol, e.target.checked)} className="w-4 h-4 accent-current" />
                <span className="font-semibold text-sm">{d.display_name}</span>
                <span className="ml-auto text-[10px] text-muted-foreground">{d.asset_class} · {d.exchange}</span>
              </label>
              {entry.enabled && (
                <div className="mt-2 grid grid-cols-2 gap-1">
                  {d.data_categories.map((cat) => (
                    <label key={cat} className="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={entry.data_categories.includes(cat)}
                        onChange={(e) => onToggleCategory(d.symbol, cat, e.target.checked)}
                        className="w-3 h-3"
                      />
                      {cat.replace(/_/g, ' ')}
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
