'use client';
import { useEffect, useRef } from 'react';

export function ForecastChart({ data }: { data: any }) {
  const ref = useRef<HTMLDivElement>(null);
  // lightweight-charts rendering placeholder - simple canvas
  if (!data) return null;
  const tf = data.timeframes?.['15m'] || Object.values(data.timeframes || {})[0] as any;
  const forecast = data.forecasts?.['15m'];
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Price Chart & Forecast — {data.symbol} {data.freshness && `(${data.freshness})`}</h3>
      <div ref={ref} className="h-64 bg-muted rounded flex items-center justify-center relative overflow-hidden">
        <div className="text-center text-sm text-muted-foreground">
          <p>Historical Data → Forecast</p>
          <p className="text-xs mt-1">Current: {tf?.current_price?.toFixed(2) ?? '—'} {forecast && `• Expected range ${forecast.expected_range.low.toFixed(0)} – ${forecast.expected_range.high.toFixed(0)}`}</p>
          {forecast && <p className="text-xs">Forecast ({forecast.horizon_minutes}m) Up { (forecast.direction.up*100).toFixed(0)}% • Sideways {(forecast.direction.sideways*100).toFixed(0)}% • Down {(forecast.direction.down*100).toFixed(0)}%</p>}
        </div>
        {forecast && (
          <div className="absolute bottom-4 left-4 right-4 h-12 opacity-40 flex items-end gap-1">
            <div className="flex-1 h-8 bg-primary/20 rounded" />
            <div className="flex-1 h-12 bg-primary/30 rounded border border-dashed border-primary" title="Forecast range" />
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground mt-2">Forecast areas are visually distinguished from historical prices and not guaranteed.</p>
    </div>
  );
}
