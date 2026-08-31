'use client';

import * as React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Minus, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';

type Tone = 'ok' | 'warn' | 'danger' | 'muted' | 'primary';

const TONE_STYLES: Record<Tone, string> = {
  ok: 'bg-green-500/10 text-green-600 border-green-500/30',
  warn: 'bg-amber-500/10 text-amber-600 border-amber-500/30',
  danger: 'bg-red-500/10 text-red-500 border-red-500/30',
  muted: 'bg-muted text-muted-foreground border-border',
  primary: 'bg-primary/10 text-primary border-primary/30',
};

const ICONS: Record<Tone, React.ReactNode> = {
  ok: <CheckCircle2 className="w-3 h-3" />,
  warn: <AlertTriangle className="w-3 h-3" />,
  danger: <XCircle className="w-3 h-3" />,
  muted: <Minus className="w-3 h-3" />,
  primary: <Lock className="w-3 h-3" />,
};

interface StatusPillProps {
  tone: Tone;
  label: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
  size?: 'xs' | 'sm';
}

export function StatusPill({ tone, label, icon, className, size = 'xs' }: StatusPillProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border font-medium whitespace-nowrap',
        size === 'xs' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs',
        TONE_STYLES[tone],
        className
      )}
    >
      {icon ?? ICONS[tone]}
      {label}
    </span>
  );
}