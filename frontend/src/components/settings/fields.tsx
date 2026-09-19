'use client';

import type { ReactNode } from 'react';

export function TextField({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  hint,
  error,
  min,
  max,
  step,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
  type?: 'text' | 'number' | 'password' | 'time';
  placeholder?: string;
  hint?: string;
  error?: string;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className="field">
      <span className="field-l">{label}</span>
      <input
        className={`input ${type === 'number' ? 'num' : ''}`}
        type={type}
        value={value}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        autoComplete={type === 'password' ? 'new-password' : 'off'}
        spellCheck={false}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint && !error ? <span className="text-[11px] text-ink-2">{hint}</span> : null}
      {error ? <span className="text-[11px] font-semibold text-down-strong">{error}</span> : null}
    </label>
  );
}

export function SelectField<T extends string>({
  label,
  value,
  options,
  onChange,
  hint,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-l">{label}</span>
      <select className="input" value={value} onChange={(event) => onChange(event.target.value as T)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
      {hint ? <span className="text-[11px] text-ink-2">{hint}</span> : null}
    </label>
  );
}

export function ToggleField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        {label}
      </span>
      {hint ? <span className="text-[11px] text-ink-2">{hint}</span> : null}
    </label>
  );
}

export function SectionGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>;
}
