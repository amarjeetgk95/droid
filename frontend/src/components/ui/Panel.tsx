'use client';

import type { ReactNode } from 'react';

export function Panel({
  title,
  meta,
  children,
  actions,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="card">
      <header className="card-hd">
        <h3 className="card-title">{title}</h3>
        <div className="flex items-center gap-2">
          {meta ? <span className="card-meta">{meta}</span> : null}
          {actions}
        </div>
      </header>
      <div className="card-bd">{children}</div>
    </section>
  );
}

export function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{children}</span>
    </div>
  );
}
