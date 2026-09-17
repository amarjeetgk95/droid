'use client';

import React, { type ReactNode } from 'react';
import { RetryButton } from '@/components/ui/desk';
import { Button } from '@/components/ui/button';
import { formatFeatureValue } from './contracts';

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-3 text-xs"
      style={{ color: 'var(--ds-bear-strong)' }}
    >
      <span>{message}</span>
      {onRetry ? <RetryButton onRetry={onRetry} /> : null}
    </div>
  );
}

export function ExportButtons({
  onJson,
  onCsv,
  disabled,
}: {
  onJson?: () => void;
  onCsv?: () => void;
  disabled?: boolean;
}) {
  if (!onJson && !onCsv) return null;
  return (
    <div className="flex items-center gap-1.5">
      {onJson ? (
        <Button type="button" variant="outline" size="xs" onClick={onJson} disabled={disabled}>
          JSON
        </Button>
      ) : null}
      {onCsv ? (
        <Button type="button" variant="outline" size="xs" onClick={onCsv} disabled={disabled}>
          CSV
        </Button>
      ) : null}
    </div>
  );
}

export function ValueGrid({
  entries,
  emptyNote,
}: {
  entries: Array<{ key: string; value: unknown }>;
  emptyNote: string;
}) {
  if (entries.length === 0) {
    return <p className="muted" style={{ margin: 0, fontSize: 12 }}>{emptyNote}</p>;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
      {entries.map(({ key, value }) => (
        <div key={key} className="rounded border border-border bg-surface-subtle p-2">
          <div className="text-[10px] uppercase text-ink-3 truncate" title={key}>
            {key}
          </div>
          <div className="num text-sm font-semibold text-ink mt-0.5 break-words">
            {formatFeatureValue(value)}
          </div>
        </div>
      ))}
    </div>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-3 mb-1.5">
      {children}
    </div>
  );
}
