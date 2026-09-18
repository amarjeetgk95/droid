'use client';

import React from 'react';

interface PriceDisplayProps {
  price: number;
  change?: number;
  changePct?: number;
  currency?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showSign?: boolean;
  className?: string;
}

const sizeClasses = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-lg font-semibold',
  xl: 'text-2xl font-bold',
};

export const PriceDisplay: React.FC<PriceDisplayProps> = ({
  price,
  change,
  changePct,
  currency = '₹',
  size = 'md',
  showSign = true,
  className = '',
}) => {
  const isUp = (change ?? changePct ?? 0) > 0;
  const isDown = (change ?? changePct ?? 0) < 0;

  const colorClass = isUp
    ? 'text-up-strong font-semibold'
    : isDown
      ? 'text-down-strong font-semibold'
      : 'text-ink-2';

  const formattedPrice = new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);

  return (
    <div className={`inline-flex items-baseline gap-2 font-mono ${className}`}>
      <span className={`text-foreground font-bold ${sizeClasses[size]}`}>
        {currency}
        {formattedPrice}
      </span>

      {(change !== undefined || changePct !== undefined) && (
        <span className={`text-xs font-semibold ${colorClass}`}>
          {isUp && showSign && '+'}
          {change !== undefined && change.toFixed(2)}
          {changePct !== undefined && ` (${isUp && showSign ? '+' : ''}${changePct.toFixed(2)}%)`}
        </span>
      )}
    </div>
  );
};
