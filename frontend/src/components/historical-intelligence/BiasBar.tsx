'use client';

import * as React from 'react';
import { cn } from '@/lib/utils';

interface BiasBarProps {
  bullish: number;
  neutral: number;
  bearish: number;
  className?: string;
  showLabels?: boolean;
}

export function BiasBar({ bullish, neutral, bearish, className, showLabels = true }: BiasBarProps) {
  const total = bullish + neutral + bearish || 1;
  const bullPct = (bullish / total) * 100;
  const neutralPct = (neutral / total) * 100;
  const bearPct = (bearish / total) * 100;

  return (
    <div className={cn('w-full', className)}>
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-muted">
        {bullPct > 0 && (
          <div className="bg-green-500 transition-all" style={{ width: `${bullPct}%` }} title={`Bullish ${bullish}%`} />
        )}
        {neutralPct > 0 && (
          <div className="bg-amber-400 transition-all" style={{ width: `${neutralPct}%` }} title={`Neutral ${neutral}%`} />
        )}
        {bearPct > 0 && (
          <div className="bg-red-500 transition-all" style={{ width: `${bearPct}%` }} title={`Bearish ${bearish}%`} />
        )}
      </div>
      {showLabels && (
        <div className="mt-1 flex justify-between text-[10px] text-muted-foreground">
          <span className="text-green-600 font-medium">{bullish}% bull</span>
          <span>{neutral}% neutral</span>
          <span className="text-red-500 font-medium">{bearish}% bear</span>
        </div>
      )}
    </div>
  );
}