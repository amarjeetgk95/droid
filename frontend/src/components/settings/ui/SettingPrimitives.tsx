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
    <section
      className={`bg-card border border-border/60 rounded-xl overflow-hidden shadow-2xs transition-colors ${className}`}
    >
      <div className="px-5 py-4 border-b border-border/40 bg-muted/20 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-start sm:items-center gap-2.5">
          {Icon && (
            <div className="text-muted-foreground p-1 rounded-md bg-secondary/50">
              <Icon className="w-4 h-4" />
            </div>
          )}
          <div>
            <h2 className="text-sm font-semibold tracking-tight text-foreground">{title}</h2>
            {description && (
              <p className="text-xs text-muted-foreground mt-0.5 leading-normal">{description}</p>
            )}
          </div>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className="divide-y divide-border/40">{children}</div>
    </section>
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
      <div className={`px-5 py-4 space-y-2.5 ${className}`}>
        <div>
          {htmlFor ? (
            <label htmlFor={htmlFor} className="text-xs font-medium text-foreground block">
              {label}
            </label>
          ) : (
            <span className="text-xs font-medium text-foreground block">{label}</span>
          )}
          {description && (
            <p className="text-[11px] text-muted-foreground mt-0.5 leading-normal">{description}</p>
          )}
        </div>
        <div>{children}</div>
        {error && <p className="text-[11px] text-destructive mt-1 font-medium">{error}</p>}
      </div>
    );
  }

  return (
    <div
      className={`px-5 py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs ${className}`}
    >
      <div className="max-w-md pr-2">
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-xs font-medium text-foreground block cursor-pointer">
            {label}
          </label>
        ) : (
          <span className="text-xs font-medium text-foreground block">{label}</span>
        )}
        {description && (
          <p className="text-[11px] text-muted-foreground mt-0.5 leading-normal">{description}</p>
        )}
        {error && <p className="text-[11px] text-destructive mt-1 font-medium">{error}</p>}
      </div>
      <div className="shrink-0 flex items-center sm:justify-end">{children}</div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 3. SettingSwitch (Linear / Apple style toggle)                             */
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
      className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-150 ease-in-out focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'bg-primary' : 'bg-muted-foreground/25 hover:bg-muted-foreground/35'
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-xs ring-0 transition duration-150 ease-in-out ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/* 4. SettingSegmented                                                        */
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
  size = 'md',
  className = '',
}: SettingSegmentedProps<T>) {
  return (
    <div
      className={`inline-flex items-center p-1 bg-secondary/70 border border-border/50 rounded-lg gap-0.5 ${className}`}
    >
      {options.map((option) => {
        const isSelected = value === option.id;
        const Icon = option.icon;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            className={`flex items-center gap-1.5 rounded-md font-medium transition-all cursor-pointer ${
              size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3 py-1.5 text-xs'
            } ${
              isSelected
                ? 'bg-card text-foreground shadow-2xs font-semibold'
                : 'text-muted-foreground hover:text-foreground hover:bg-card/50'
            }`}
          >
            {Icon && <Icon className={size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'} />}
            <span>{option.label}</span>
            {option.badge && (
              <span
                className={`text-[9px] px-1 py-0.2 rounded font-mono ${
                  isSelected ? 'bg-secondary text-foreground' : 'bg-muted text-muted-foreground'
                }`}
              >
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
/* 5. SettingInput & SettingSelect                                            */
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
        className={`w-full max-w-xs bg-secondary/40 border border-border/70 rounded-md px-2.5 py-1.5 text-xs text-foreground placeholder:text-muted-foreground/60 transition-colors focus:outline-hidden focus:border-ring focus:ring-1 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed ${
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
          className={`w-full appearance-none bg-secondary/40 border border-border/70 rounded-md pl-2.5 pr-8 py-1.5 text-xs text-foreground cursor-pointer transition-colors focus:outline-hidden focus:border-ring focus:ring-1 focus:ring-ring disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
        >
          {children}
        </select>
        <ChevronDown className="w-3.5 h-3.5 text-muted-foreground absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
      </div>
    );
  }
);
SettingSelect.displayName = 'SettingSelect';
