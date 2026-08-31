'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

interface StorageBarProps {
  currentMb: number;
  targetMb: number;
  warningMb: number;
  hardCeilingMb: number;
  status?: 'WITHIN_TARGET' | 'WARNING' | 'EXCEEDS_HARD';
  size?: 'sm' | 'md';
  className?: string;
  projectedMb?: number | null;
}

export function StorageBar({ currentMb, targetMb, warningMb, hardCeilingMb, status, size = 'md', className, projectedMb }: StorageBarProps) {
  const safeCeiling = Math.max(hardCeilingMb, 1);
  const currentPct = Math.min(100, (currentMb / safeCeiling) * 100);
  const targetPct = (targetMb / safeCeiling) * 100;
  const warningPct = (warningMb / safeCeiling) * 100;

  const tone = status === 'EXCEEDS_HARD' ? 'red' : status === 'WARNING' ? 'amber' : 'green';
  const fillClass = tone === 'red' ? 'bg-red-500' : tone === 'amber' ? 'bg-amber-500' : 'bg-green-500';

  const [animated, setAnimated] = useState(false);
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setAnimated(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  return (
    <div className={cn('w-full', className)}>
      <div className={cn('relative rounded-full bg-muted overflow-hidden', size === 'sm' ? 'h-1.5' : 'h-2.5')}>
        <div
          className={cn('h-full transition-all duration-500', fillClass)}
          style={{ width: animated ? `${currentPct}%` : '0%' }}
        />
        {typeof projectedMb === 'number' && projectedMb > currentMb && (
          <div
            className="absolute top-0 bottom-0 bg-primary/30 border-l border-primary"
            style={{ left: `${currentPct}%`, width: `${Math.min(100, (projectedMb / safeCeiling) * 100) - currentPct}%` }}
            title={`Projected ${projectedMb.toFixed(1)} MB`}
          />
        )}
        <div className="absolute top-0 bottom-0 w-px bg-amber-500/70" style={{ left: `${warningPct}%` }} title={`Warning ${warningMb} MB`} />
        <div className="absolute top-0 bottom-0 w-px bg-red-500/70" style={{ left: `${targetPct}%` }} title={`Target ${targetMb} MB`} />
      </div>
    </div>
  );
}