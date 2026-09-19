'use client';

import React from 'react';

interface GaugeProps {
  value: number; // 0 to 100 or min to max
  min?: number;
  max?: number;
  label?: string;
  sublabel?: string;
  size?: 'sm' | 'md' | 'lg';
  thresholds?: {
    warning?: number;
    danger?: number;
  };
  invertThresholds?: boolean; // if lower is worse
  unit?: string;
  className?: string;
}

type GaugeLevel = 'ok' | 'warning' | 'danger';

const levelStyles: Record<GaugeLevel, { bar: string; text: string; label: string }> = {
  ok: { bar: 'bg-up', text: 'text-up-strong', label: 'normal' },
  warning: { bar: 'bg-warn', text: 'text-warn-strong', label: 'warning' },
  danger: { bar: 'bg-down', text: 'text-down-strong', label: 'critical' },
};

export const Gauge: React.FC<GaugeProps> = ({
  value,
  min = 0,
  max = 100,
  label,
  sublabel,
  size = 'md',
  thresholds = { warning: 70, danger: 90 },
  invertThresholds = false,
  unit = '%',
  className = '',
}) => {
  // Guard non-finite input and `max <= min`: never render NaN/Infinity widths.
  const safeMin = Number.isFinite(min) ? min : 0;
  const safeMax = Number.isFinite(max) ? max : 100;
  const span = safeMax - safeMin;
  const hasSpan = span > 0;
  const numeric = Number.isFinite(value) ? value : safeMin;
  const clampedVal = hasSpan ? Math.min(Math.max(numeric, safeMin), safeMax) : safeMin;
  const percentage = hasSpan ? Math.round(((clampedVal - safeMin) / span) * 100) : 0;

  let level: GaugeLevel = 'ok';
  if (!invertThresholds) {
    if (thresholds.danger !== undefined && percentage >= thresholds.danger) level = 'danger';
    else if (thresholds.warning !== undefined && percentage >= thresholds.warning) level = 'warning';
  } else {
    if (thresholds.danger !== undefined && percentage <= thresholds.danger) level = 'danger';
    else if (thresholds.warning !== undefined && percentage <= thresholds.warning) level = 'warning';
  }

  const heightClass = size === 'sm' ? 'h-1.5' : size === 'lg' ? 'h-3' : 'h-2';
  const display = `${clampedVal.toFixed(1)}${unit}`;
  const valueText = `${display} — ${levelStyles[level].label}`;

  return (
    <div className={`w-full ${className}`}>
      {(label || sublabel) && (
        <div className="flex items-center justify-between text-xs mb-1.5 font-mono">
          {label && <span className="text-ink-2">{label}</span>}
          <span className={`font-semibold ${levelStyles[level].text}`}>
            {display}
            <span className="sr-only"> — {levelStyles[level].label}</span>
          </span>
        </div>
      )}
      <div
        role="progressbar"
        aria-label={label ?? 'Gauge'}
        aria-valuemin={safeMin}
        aria-valuemax={safeMax}
        aria-valuenow={Number(clampedVal.toFixed(2))}
        aria-valuetext={valueText}
        className={`w-full bg-muted-strong rounded-full overflow-hidden ${heightClass}`}
      >
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${levelStyles[level].bar}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {sublabel && <div className="text-[11px] text-ink-3 mt-1 font-mono">{sublabel}</div>}
    </div>
  );
};
