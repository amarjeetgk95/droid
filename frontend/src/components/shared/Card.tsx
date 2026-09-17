'use client';

import React from 'react';

interface CardProps {
  children: React.ReactNode;
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  headerAction?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  glow?: 'cyan' | 'emerald' | 'indigo' | 'rose' | 'amber' | 'none';
  noPadding?: boolean;
}

/* `glow` is kept for API compatibility; tones map onto the semantic families
   (border emphasis only — the design system has no coloured shadows). */
const glowStyles: Record<NonNullable<CardProps['glow']>, string> = {
  none: '',
  cyan: 'border-primary',
  emerald: 'border-up-line',
  indigo: 'border-accent-line',
  rose: 'border-down-line',
  amber: 'border-warn-line',
};

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  headerAction,
  footer,
  className = '',
  glow = 'none',
  noPadding = false,
}) => {
  return (
    <div
      className={`relative rounded-lg border border-border bg-card text-foreground transition-all duration-200 ${glowStyles[glow]} ${className}`}
    >
      {(title || subtitle || headerAction) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-surface-subtle">
          <div>
            {title && <div className="text-sm font-semibold tracking-wide text-foreground">{title}</div>}
            {subtitle && <div className="text-xs text-ink-3 mt-0.5">{subtitle}</div>}
          </div>
          {headerAction && <div className="flex items-center gap-2">{headerAction}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-4'}>{children}</div>
      {footer && (
        <div className="px-4 py-2.5 border-t border-border-subtle bg-surface-subtle text-xs text-ink-3">
          {footer}
        </div>
      )}
    </div>
  );
};
