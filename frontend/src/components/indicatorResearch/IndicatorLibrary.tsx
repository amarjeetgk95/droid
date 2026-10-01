'use client';

import { useMemo, useState } from 'react';
import { Search, X } from 'lucide-react';
import type { IndicatorCatalog, IndicatorMetadata, CategoryInfo } from '@/lib/api/indicatorResearch';

const OUTPUT_TYPE_LABEL: Record<string, string> = {
  oscillator: 'Oscillator',
  overlay: 'Overlay',
  multi_output: 'Multi-output',
  signal_only: 'Signal only',
};

type Props = {
  catalog: IndicatorCatalog | null;
  loading: boolean;
  error: string | null;
  selectedIds: string[];
  activeId: string | null;
  onSelect: (meta: IndicatorMetadata) => void;
  onRemove: (id: string) => void;
  onRetry: () => void;
};

/**
 * Indicator picker. Everything it renders comes from the backend catalogue —
 * adding a Python indicator file makes it appear here with no frontend change.
 */
export function IndicatorLibrary({ catalog, loading, error, selectedIds, activeId, onSelect, onRemove, onRetry }: Props) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  const indicators = catalog?.indicators ?? [];
  const categories: CategoryInfo[] = catalog?.categories ?? [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return indicators.filter((meta) => {
      if (category && category !== 'all' && meta.category !== category) return false;
      if (!q) return true;
      return (
        meta.name.toLowerCase().includes(q) ||
        meta.id.toLowerCase().includes(q) ||
        meta.category.toLowerCase().includes(q) ||
        meta.tags.some((t) => t.toLowerCase().includes(q))
      );
    });
  }, [indicators, category, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, IndicatorMetadata[]>();
    for (const meta of filtered) {
      const list = map.get(meta.category) ?? [];
      list.push(meta);
      map.set(meta.category, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <span className="micro-label">Indicators</span>
        <span className="card-meta num ml-auto">{indicators.length}</span>
      </div>

      <label className="relative block">
        <Search size={12} className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
        <input
          className="input w-full pl-7"
          placeholder="Search indicators…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search indicators"
        />
      </label>

      <div className="flex flex-wrap gap-1">
        <button
          type="button"
          className={`chip ${category === null ? 'is-active' : ''}`}
          aria-pressed={category === null}
          onClick={() => setCategory(null)}
        >
          All
        </button>
        {categories.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`chip ${category === c.id ? 'is-active' : ''}`}
            aria-pressed={category === c.id}
            onClick={() => setCategory(category === c.id ? null : c.id)}
            title={`${c.count} indicator${c.count === 1 ? '' : 's'} in ${c.label}`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {loading && indicators.length === 0 ? (
        <p className="sg-note">Loading indicator catalogue…</p>
      ) : null}

      {error ? (
        <div className="notice notice--warn">
          <span>{error}</span>
          <button type="button" className="btn btn-ic ml-auto" onClick={onRetry}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="sg-scroll flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto pr-1">
        {grouped.map(([cat, list]) => (
          <div key={cat} className="flex flex-col gap-1">
            <span className="micro-label">{cat}</span>
            {list.map((meta) => {
              const isSelected = selectedIds.includes(meta.id);
              const isActive = activeId === meta.id;
              return (
                <div
                  key={meta.id}
                  className={`flex items-start gap-1.5 rounded-md border px-2 py-1.5 transition-colors ${
                    isActive ? 'border-accent-line bg-accent-wash' : 'border-border-subtle hover:bg-surface-subtle'
                  }`}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => onSelect(meta)}
                    title={meta.description}
                  >
                    <span className="flex items-center gap-1.5">
                      <span className="truncate text-[12px] font-medium text-ink">{meta.name}</span>
                      {meta.category === 'microstructure' || meta.tags?.includes('order_flow') || meta.requires?.includes('depth') ? (
                        <span className="badge badge-sm b-bull" title="Requires real order-book depth / trade data">
                          order flow
                        </span>
                      ) : null}
                      {isSelected ? <span className="badge badge-sm b-info">added</span> : null}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] text-ink-3">
                      {OUTPUT_TYPE_LABEL[meta.output_type] ?? meta.output_type} · {meta.outputs.length} output
                      {meta.outputs.length === 1 ? '' : 's'} · {meta.parameters.length} param
                      {meta.parameters.length === 1 ? '' : 's'}
                    </span>
                  </button>
                  {isSelected ? (
                    <button
                      type="button"
                      className="btn-ic"
                      aria-label={`Remove ${meta.name}`}
                      title="Remove from this experiment"
                      onClick={() => onRemove(meta.id)}
                    >
                      <X size={11} />
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        ))}
        {grouped.length === 0 && !loading ? <p className="sg-note">No indicator matches this filter.</p> : null}
      </div>
    </div>
  );
}
