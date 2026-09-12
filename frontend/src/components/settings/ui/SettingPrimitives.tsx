'use client';

import React, { forwardRef } from 'react';
import { ChevronDown } from 'lucide-react';

/* -------------------------------------------------------------------------- */
/* 1. SettingSection                                                          */
/* -------------------------------------------------------------------------- */
export interface SettingSectionProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  className?: string;
}

export function SettingSection({
  title,
  description,
  action,
  icon: Icon,
  children,
  className = '',
}: SettingSectionProps) {
  return (
    <section className={`card ${className}`}>
      <div className="card-hd">
        <div className="flex items-center gap-2 min-w-0">
          {Icon && (
            <span className="muted shrink-0 flex items-center">
              <Icon className="w-3.5 h-3.5" />
            </span>
          )}
          <div className="min-w-0">
            <h2 className="card-title">{title}</h2>
            {description && (
              <p className="muted" style={{ margin: 0, fontSize: '11px', lineHeight: 1.25 }}>
                {description}
              </p>
            )}
          </div>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className="divide-y divide-[var(--ds-border-subtle)]">{children}</div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* 1b. StatTile — Institutional metric tile matching .stat from Droid desk    */
/* -------------------------------------------------------------------------- */

export interface StatTileProps {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: 'default' | 'positive' | 'negative';
  className?: string;
}

export function StatTile({ label, value, sub, tone = 'default', className = '' }: StatTileProps) {
  const toneClass =
    tone === 'positive' ? 'v-bull' : tone === 'negative' ? 'v-bear' : '';

  return (
    <div className={`stat ${className}`}>
      <div className="stat-l">{label}</div>
      <div className={`stat-v ${toneClass}`}>{value}</div>
      {sub && <div className="stat-s num">{sub}</div>}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 2. SettingRow                                                              */
/* -------------------------------------------------------------------------- */
export interface SettingRowProps {
  label: React.ReactNode;
  description?: React.ReactNode;
  error?: string;
  children?: React.ReactNode;
  vertical?: boolean;
  className?: string;
  htmlFor?: string;
}

export function SettingRow({
  label,
  description,
  error,
  children,
  vertical = false,
  className = '',
  htmlFor,
}: SettingRowProps) {
  if (vertical) {
    return (
      <div className={`px-4 py-3 space-y-2 ${className}`}>
        <div>
          {htmlFor ? (
            <label htmlFor={htmlFor} className="text-xs font-semibold text-[var(--ds-ink)] block">
              {label}
            </label>
          ) : (
            <span className="text-xs font-semibold text-[var(--ds-ink)] block">{label}</span>
          )}
          {description && (
            <p className="text-[11px] text-[var(--ds-ink-2)] mt-0.5 leading-normal">{description}</p>
          )}
        </div>
        <div>{children}</div>
        {error && <p className="text-[11px] text-[var(--ds-bear)] mt-1 font-medium">{error}</p>}
      </div>
    );
  }

  return (
    <div
      className={`px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs ${className}`}
    >
      <div className="max-w-md pr-2">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-xs font-semibold text-[var(--ds-ink)] block cursor-pointer">
            {label}
          </label>
        ) : (
          <span className="text-xs font-semibold text-[var(--ds-ink)] block">{label}</span>
        )}
        {description && (
          <p className="text-[11px] text-[var(--ds-ink-2)] mt-0.5 leading-normal">{description}</p>
        )}
        {error && <p className="text-[11px] text-[var(--ds-bear)] mt-1 font-medium">{error}</p>}
      </div>
      <div className="shrink-0 flex items-center sm:justify-end">{children}</div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 3. SettingSwitch (Crisp Hairline Institutional Toggle)                     */
/* -------------------------------------------------------------------------- */
export interface SettingSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
  'aria-label'?: string;
}

export function SettingSwitch({
  checked,
  onChange,
  disabled = false,
  id,
  'aria-label': ariaLabel,
}: SettingSwitchProps) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-4.5 w-8 shrink-0 cursor-pointer rounded-full border transition-colors duration-120 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--ds-accent)] disabled:cursor-not-allowed disabled:opacity-40 ${
        checked
          ? 'bg-[var(--ds-accent)] border-[var(--ds-accent)]'
          : 'bg-[var(--ds-inset-2)] border-[var(--ds-border-strong)] hover:bg-[var(--ds-border)]'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-xs transition duration-120 mt-[1px] ${
          checked ? 'translate-x-3.5' : 'translate-x-0.5'
        }`}
      />
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/* 4. SettingSegmented (Using global .seg and .seg-btn)                       */
/* -------------------------------------------------------------------------- */
export interface SegmentedOption<T extends string = string> {
  id: T;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  badge?: string;
}

export interface SettingSegmentedProps<T extends string = string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: 'sm' | 'md';
  className?: string;
}

export function SettingSegmented<T extends string = string>({
  options,
  value,
  onChange,
  className = '',
}: SettingSegmentedProps<T>) {
  return (
    <div className={`seg ${className}`} role="group">
      {options.map((option) => {
        const isSelected = value === option.id;
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            data-active={isSelected}
            aria-pressed={isSelected}
            className="seg-btn flex items-center gap-1.5"
          >
            {Icon && <Icon className="w-3.5 h-3.5" />}
            <span>{option.label}</span>
            {option.badge && (
              <span className="badge b-neut" style={{ fontSize: '9px', padding: '1px 4px' }}>
                {option.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 5. SettingInput & SettingSelect (Institutional Form Controls)              */
/* -------------------------------------------------------------------------- */
export interface SettingInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  mono?: boolean;
}

export const SettingInput = forwardRef<HTMLInputElement, SettingInputProps>(
  ({ mono, className = '', ...props }, ref) => {
    return (
      <input
        ref={ref}
        {...props}
        className={`w-full max-w-xs bg-[var(--ds-surface)] border border-[var(--ds-border-strong)] rounded-[var(--radius-md)] px-2.5 py-1.5 text-xs text-[var(--ds-ink)] placeholder:text-[var(--ds-ink-3)] transition-colors focus:outline-none focus:border-[var(--ds-accent)] focus:ring-1 focus:ring-[var(--ds-accent)] disabled:opacity-40 disabled:cursor-not-allowed ${
          mono ? 'font-mono' : ''
        } ${className}`}
      />
    );
  }
);
SettingInput.displayName = 'SettingInput';

export interface SettingSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {}

export const SettingSelect = forwardRef<HTMLSelectElement, SettingSelectProps>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div className="relative w-full max-w-xs">
        <select
          ref={ref}
          {...props}
          className={`w-full appearance-none bg-[var(--ds-surface)] border border-[var(--ds-border-strong)] rounded-[var(--radius-md)] pl-2.5 pr-8 py-1.5 text-xs text-[var(--ds-ink)] cursor-pointer transition-colors focus:outline-none focus:border-[var(--ds-accent)] focus:ring-1 focus:ring-[var(--ds-accent)] disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
        >
          {children}
        </select>
        <ChevronDown className="w-3.5 h-3.5 text-[var(--ds-ink-3)] absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
      </div>
    );
  }
);
SettingSelect.displayName = 'SettingSelect';
