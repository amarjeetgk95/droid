'use client';

import React from 'react';

export type StatusDotState = 'live' | 'healthy' | 'degraded' | 'error' | 'offline' | 'warning';

interface StatusDotProps {
  status: StatusDotState;
  label?: string;
  pulse?: boolean;
  className?: string;
}

/* Semantic tokens only — no palette hardcodes, no decorative coloured glow. */
const statusColors: Record<StatusDotState, string> = {
  live: 'bg-up',
  healthy: 'bg-up',
  warning: 'bg-warn',
  degraded: 'bg-warn',
  error: 'bg-down',
  offline: 'bg-disabled',
};

export const StatusDot: React.FC<StatusDotProps> = ({
  status,
  label,
  pulse = true,
  className = '',
}) => {
  const dot = statusColors[status] ?? statusColors.offline;

  return (
    <div className={`inline-flex items-center gap-1.5 font-mono text-xs ${className}`}>
      <span className="relative flex h-2 w-2" aria-hidden="true">
        {pulse && status !== 'offline' && (
          <span className={`animate-ping motion-reduce:animate-none absolute inline-flex h-full w-full rounded-full opacity-75 ${dot}`} />
        )}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${dot}`} />
      </span>
      {label && <span className="text-ink-2 font-medium">{label}</span>}
    </div>
  );
};
