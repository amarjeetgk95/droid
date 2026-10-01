'use client';

import { RotateCcw, X } from 'lucide-react';
import type { IndicatorMetadata, ParameterSpec } from '@/lib/api/indicatorResearch';

const PANE_LABEL: Record<string, string> = {
  price: 'price pane',
  separate: 'own pane',
  none: 'signal only',
};

type Props = {
  meta: IndicatorMetadata;
  params: Record<string, unknown>;
  onChange: (params: Record<string, unknown>) => void;
  onReset: () => void;
  onRemove: () => void;
};

/**
 * Parameter controls are generated from the indicator's declared metadata.
 * There is intentionally no per-indicator JSX anywhere in this module: a new
 * Python indicator with a new parameter type shows up here automatically.
 */
export function IndicatorParameterPanel({ meta, params, onChange, onReset, onRemove }: Props) {
  const setValue = (name: string, value: unknown) => onChange({ ...params, [name]: value });

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5">
        <span className="micro-label">Indicator settings</span>
        <span className="badge badge-sm b-neut">{meta.category}</span>
        <button type="button" className="btn-ic ml-auto" onClick={onReset} title="Reset to declared defaults">
          <RotateCcw size={11} />
        </button>
        <button type="button" className="btn-ic" onClick={onRemove} title={`Remove ${meta.name}`} aria-label={`Remove ${meta.name}`}>
          <X size={11} />
        </button>
      </div>

      <div>
        <p className="text-[12px] font-medium text-ink">{meta.name}</p>
        <p className="sg-note">{meta.description}</p>
      </div>

      <div className="flex flex-col gap-2">
        {meta.parameters.length === 0 ? <p className="sg-note">This indicator takes no parameters.</p> : null}
        {meta.parameters.map((spec) => (
          <ParamControl key={spec.name} spec={spec} value={params[spec.name]} onChange={(v) => setValue(spec.name, v)} />
        ))}
      </div>

      <div className="divider" />

      <div className="flex flex-col gap-1">
        <span className="micro-label">Outputs</span>
        <div className="sg-kvlist">
          {meta.outputs.map((out) => (
            <div key={out.name} className="sg-kv">
              <span className="sg-lab" title={out.description ?? undefined}>
                {out.label}
              </span>
              <span className="sg-num">
                {out.role} · {PANE_LABEL[out.pane] ?? out.pane}
              </span>
            </div>
          ))}
        </div>
      </div>

      <details className="sg-sect">
        <summary className="micro-label cursor-pointer">Formula</summary>
        <p className="sg-note mt-1">{meta.formula_summary}</p>
        {meta.reference ? <p className="faint text-[10px]">{meta.reference}</p> : null}
        <p className="faint mt-1 text-[10px]">
          version {meta.version} · requires {meta.requires.join(', ') || 'ohlcv'}
        </p>
      </details>
    </div>
  );
}

function ParamControl({
  spec,
  value,
  onChange,
}: {
  spec: ParameterSpec;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = (
    <span className="field-l" title={spec.description ?? undefined}>
      {spec.label}
    </span>
  );

  if (spec.type === 'boolean') {
    return (
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          className="h-3.5 w-3.5 accent-[var(--ds-accent)]"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
        {label}
      </label>
    );
  }

  if (spec.type === 'choice') {
    return (
      <label className="field">
        {label}
        <select className="input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}>
          {(spec.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </label>
    );
  }

  if (spec.type === 'string') {
    return (
      <label className="field">
        {label}
        <input className="input w-full" value={String(value ?? '')} onChange={(e) => onChange(e.target.value)} />
      </label>
    );
  }

  const step = spec.step ?? (spec.type === 'integer' ? 1 : 0.1);
  return (
    <label className="field">
      <span className="flex items-baseline gap-1.5">
        {label}
        {spec.min !== null && spec.max !== null ? (
          <span className="faint text-[10px]">
            {spec.min}–{spec.max}
          </span>
        ) : null}
      </span>
      <input
        type="number"
        className="input w-full"
        value={value === undefined || value === null ? '' : String(value)}
        min={spec.min ?? undefined}
        max={spec.max ?? undefined}
        step={step}
        onChange={(e) => {
          const raw = e.target.value;
          if (raw === '') {
            onChange(spec.type === 'integer' ? spec.default : '');
            return;
          }
          const n = Number(raw);
          if (!Number.isFinite(n)) return;
          onChange(spec.type === 'integer' ? Math.round(n) : n);
        }}
      />
    </label>
  );
}
