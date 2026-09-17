'use client';

/* DeskShell — shared institutional desk layout (R1).
   Header (identity + truth) → Toolbar (context controls) → content → Footer (provenance).
   No marketing, no emoji, no badges in the title. Feed state renders via FreshnessClock only. */

import type { CSSProperties, ReactNode } from 'react';

export function DeskShell({ children }: { children: ReactNode }) {
  return <div className="ds-page">{children}</div>;
}

export function DeskHeader({
  title,
  meta,
  feed,
  actions,
}: {
  title: string;
  meta?: ReactNode;
  feed?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="desk-header">
      <div className="desk-header__identity">
        <h1 className="desk-header__title">{title}</h1>
        {meta || feed ? (
          <p className="desk-header__meta num">
            {meta}
            {feed}
          </p>
        ) : null}
      </div>
      {actions ? <div className="desk-header__side">{actions}</div> : null}
    </header>
  );
}

export function DeskToolbar({
  children,
  label,
  style,
}: {
  children: ReactNode;
  label?: string;
  style?: CSSProperties;
}) {
  return (
    <div className="desk-toolbar" role="toolbar" aria-label={label ?? 'Desk controls'} style={style}>
      {children}
    </div>
  );
}

export function DeskFooter({ children }: { children: ReactNode }) {
  return <footer className="desk-footer num">{children}</footer>;
}
