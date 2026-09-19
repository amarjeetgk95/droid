'use client';

/* Shared presentational bits for the Ops Console. No timers, no fetching —
   all data arrives via props from useOpsConsole. */

import type { ReactNode } from 'react';
import { getObj } from '@/lib/signalsNormalize';
import { badgeClass, fmtCell, kvEntries, tagClass, type OpsTone } from '@/lib/opsDesk';
import type { OpsActionResult } from '@/hooks/useOpsConsole';

export function ToneBadge({ tone, label, title }: { tone: OpsTone; label: string; title?: string }) {
  return (
    <span className={`badge ${badgeClass(tone)}`} title={title}>
      {label}
    </span>
  );
}

export function KvList({ obj, limit = 12 }: { obj: unknown; limit?: number }) {
  const entries = kvEntries(getObj(obj) ?? undefined, limit);
  if (entries.length === 0) return <p className="sg-empty">No fields reported.</p>;
  return (
    <div className="sg-kvlist">
      {entries.map(([key, value]) => (
        <div key={key} className="sg-kv">
          <span className="l">{key}</span>
          <span className="v num">{value}</span>
        </div>
      ))}
    </div>
  );
}

export function CircuitTags({ states, limit = 10 }: { states: Array<[string, string]>; limit?: number }) {
  if (states.length === 0) return <p className="sg-empty">No circuit states reported.</p>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {states.slice(0, limit).map(([name, state]) => {
        const open = !/CLOSED|OK|HEALTHY|NORMAL|LIVE/i.test(state);
        return (
          <span key={name} className={`sg-tag ${tagClass(open ? 'warn' : 'bull')}`} title={state}>
            {name} {state}
          </span>
        );
      })}
    </div>
  );
}

export function OpsCard({
  title,
  meta,
  action,
  children,
}: {
  title: string;
  meta?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card" aria-label={title}>
      <div className="card-hd">
        <h2 className="card-title">{title}</h2>
        {meta ? <span className="card-meta num">{meta}</span> : null}
        {action ? <span style={{ marginLeft: meta ? 0 : 'auto' }}>{action}</span> : null}
      </div>
      <div className="card-bd flex flex-col gap-2">{children}</div>
    </section>
  );
}

export function ToolResult({ result }: { result: OpsActionResult | null }) {
  if (!result) return null;
  if (!result.ok) return <p className="sg-err">{result.message}</p>;
  const dataObj = getObj(result.data);
  const dataData = dataObj ? getObj(dataObj.data) : null;
  const payload = dataData ?? (dataObj && Object.keys(dataObj).length > 0 ? dataObj : null);
  return (
    <div className="flex flex-col gap-2">
      <p className="sg-note">{result.message}</p>
      {payload ? <KvList obj={payload} limit={10} /> : null}
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-l">{label}</span>
      {children}
      {hint ? <span className="sg-rownote">{hint}</span> : null}
    </label>
  );
}

export function fmtCellText(value: unknown): string {
  return fmtCell(value);
}
