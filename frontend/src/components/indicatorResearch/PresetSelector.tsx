'use client';

import { Sparkles, Activity, ShieldCheck, Database } from 'lucide-react';
import type { ResearchPreset } from '@/lib/api/indicatorResearch';

type Props = {
  presets: ResearchPreset[];
  onSelect: (preset: ResearchPreset) => void;
};

export function PresetSelector({ presets, onSelect }: Props) {
  return (
    <section className="card" aria-label="Canonical research presets">
      <div className="card-hd">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-accent" />
          <h3 className="card-title">Canonical Research Presets</h3>
        </div>
        <span className="card-meta">Curated setups built to demonstrate specific market edges</span>
      </div>
      <div className="card-bd">
        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {presets.map((preset) => (
            <div
              key={preset.id}
              className="flex flex-col justify-between rounded-lg border border-border-subtle bg-surface-subtle p-3 transition-colors hover:border-accent-line"
            >
              <div>
                <div className="flex items-start justify-between gap-1.5">
                  <span className="text-xs font-semibold text-ink">{preset.name}</span>
                  <div className="flex flex-shrink-0 gap-1">
                    <span className="badge badge-sm b-info">
                      {preset.instrument} · {preset.timeframe}
                    </span>
                    {preset.order_flow_required ? (
                      <span className="badge badge-sm b-bull" title="Requires real order-book/trade feed">
                        ORDER FLOW
                      </span>
                    ) : null}
                  </div>
                </div>
                <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">{preset.description}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {preset.indicators.map((ind) => (
                    <span
                      key={ind.indicator_id}
                      className="rounded bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink-2 border border-border-subtle"
                    >
                      {ind.indicator_id}
                    </span>
                  ))}
                </div>
              </div>

              <button
                type="button"
                className="btn btn-sm mt-3 w-full justify-center"
                onClick={() => onSelect(preset)}
              >
                Load Preset
              </button>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
