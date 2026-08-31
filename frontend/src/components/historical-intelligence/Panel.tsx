'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface PanelProps extends Omit<React.HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  bare?: boolean;
  tone?: 'default' | 'primary';
}

const TONE: Record<NonNullable<PanelProps['tone']>, string> = {
  default: 'border-border bg-card',
  primary: 'border-primary/30 bg-primary/5',
};

export function Panel({ title, description, actions, className, children, bare, tone = 'default', ...props }: PanelProps) {
  return (
    <section
      className={cn('rounded-xl border text-card-foreground shadow-sm', TONE[tone], !bare && 'p-4 sm:p-5', className)}
      {...props}
    >
      {(title || actions) && (
        <header className={cn('flex items-start gap-3', bare ? 'p-4 sm:p-5 pb-3' : 'mb-3')}>
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-sm sm:text-base font-semibold leading-tight">{title}</h2>}
            {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
          </div>
          {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
        </header>
      )}
      {bare ? <div className="px-4 sm:px-5 pb-4 sm:pb-5">{children}</div> : children}
    </section>
  );
}