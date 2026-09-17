'use client';

import React from 'react';

export type BadgeVariant =
  | 'success'
  | 'danger'
  | 'warning'
  | 'info'
  | 'purple'
  | 'neutral'
  | 'outline'
  | 'bull'
  | 'bear';

export type BadgeSize = 'xs' | 'sm' | 'md';

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
  className?: string;
  onClick?: () => void;
}

/* `purple` is kept for API compatibility but maps onto the single brand
   accent — the institutional palette has no secondary hue. */
const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-up-wash text-up-strong border-up-line',
  danger: 'bg-down-wash text-down-strong border-down-line',
  warning: 'bg-warn-wash text-warn-strong border-warn-line',
  info: 'bg-accent-wash text-primary border-accent-line',
  purple: 'bg-accent-wash text-primary border-accent-line',
  neutral: 'bg-muted text-ink-2 border-border',
  outline: 'bg-transparent text-ink-2 border-border-strong',
  bull: 'bg-up-wash text-up-strong border-up-line font-bold',
  bear: 'bg-down-wash text-down-strong border-down-line font-bold',
};

const dotColors: Record<BadgeVariant, string> = {
  success: 'bg-up',
  danger: 'bg-down',
  warning: 'bg-warn',
  info: 'bg-primary',
  purple: 'bg-primary',
  neutral: 'bg-ink-4',
  outline: 'bg-ink-4',
  bull: 'bg-up',
  bear: 'bg-down',
};

const sizeStyles: Record<BadgeSize, string> = {
  xs: 'text-[10px] px-1.5 py-0.5 tracking-wider',
  sm: 'text-xs px-2 py-0.5 tracking-wide',
  md: 'text-sm px-2.5 py-1',
};

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  size = 'sm',
  dot = false,
  className = '',
  onClick,
}) => {
  return (
    <span
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 font-mono uppercase font-medium rounded border transition-all duration-150 ${variantStyles[variant]} ${sizeStyles[size]} ${onClick ? 'cursor-pointer hover:opacity-80' : ''} ${className}`}
    >
      {dot && (
        <span
          aria-hidden="true"
          className={`w-1.5 h-1.5 rounded-full inline-block animate-pulse motion-reduce:animate-none ${dotColors[variant]}`}
        />
      )}
      {children}
    </span>
  );
};
