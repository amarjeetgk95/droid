'use client';

import React from 'react';
import { CheckCircle2 } from 'lucide-react';

interface Props {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
}

/** Compact checkbox row used by the Telegram subscription filters. */
export function TelegramToggle({ checked, onChange, label }: Props) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group py-1">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden="true"
        className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-colors shrink-0 peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--ds-accent)] peer-focus-visible:ring-offset-1 ${
          checked
            ? 'bg-[var(--ds-accent)] border-[var(--ds-accent)] text-[var(--ds-accent-ink)]'
            : 'bg-[var(--ds-surface)] border-[var(--ds-border-strong)] group-hover:border-[var(--ds-ink-3)]'
        }`}
      >
        {checked && <CheckCircle2 className="w-2.5 h-2.5" />}
      </span>
      <span
        className={`text-xs ${checked ? 'text-[var(--ds-ink)] font-medium' : 'text-[var(--ds-ink-3)]'}`}
      >
        {label}
      </span>
    </label>
  );
}
