'use client';
export function ForecastSummary({ data }: { data: any }) {
  if (!data?.forecasts) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Expected Future Movement</h3>
      {Object.entries(data.forecasts).map(([tf, fc]: any) => (
        <div key={tf} className="text-sm flex justify-between">
          <span>{tf} ({fc.horizon_minutes}m)</span>
          <span>{fc.expected_range.low.toFixed(0)} – {fc.expected_range.high.toFixed(0)} ({fc.expected_move_percent.toFixed(2)}%)</span>
          <span className="text-muted-foreground">Invalidation {fc.invalidation_level}</span>
        </div>
      ))}
      {data.timeframes?.['15m'] && (
        <div className="mt-2 text-sm">
          Support: {data.timeframes['15m'].support_resistance.support} • Resistance: {data.timeframes['15m'].support_resistance.resistance}
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-2">Probabilistic forecast — not guaranteed. Bullish probability shown where applicable.</p>
    </div>
  );
}
