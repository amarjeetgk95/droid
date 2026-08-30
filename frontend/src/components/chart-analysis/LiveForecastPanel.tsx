'use client';
/**
 * LiveForecastPanel — shows LIVE FORECAST per spec §25, with overall bias/confidence,
 * current price, generation timestamps, data age, model version.
 * Distinct from TimeframeForecast (compact) — this panel is the dedicated LIVE panel.
 */
export function LiveForecastPanel({ data }: { data:any }) {
  if (!data?.forecasts) return null;
  const order: string[] = ['1m','5m','15m','1h'];
  const overall = data.multi_timeframe?.alignment?.overall_bias ?? 'NEUTRAL';
  const overallConf = data.multi_timeframe?.confidence ?? 'LOW';
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-3">LIVE FORECAST</h3>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {order.map(tf=>{
          const fc=data.forecasts[tf];
          const bias=data.timeframes?.[tf]?.bias;
          if(!fc) return <div key={tf} className="border border-border rounded p-2 text-center text-muted-foreground text-xs">{tf} — loading</div>;
          const arrow = bias==='BULLISH'?'↑':bias==='BEARISH'?'↓':'→';
          const pct = (fc.direction.up*100).toFixed(0);
          return (
            <div key={tf} className="border border-border rounded p-2 text-center">
              <div className="text-xs text-muted-foreground">{tf}</div>
              <div className={`text-lg font-bold ${bias==='BULLISH'?'text-green-600':bias==='BEARISH'?'text-red-600':'text-amber-600'}`}>{arrow} {pct}%</div>
              <div className="text-[10px] text-muted-foreground">{bias}</div>
              <div className="text-[10px]">{fc.confidence}</div>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="bg-muted rounded p-2"><div className="text-muted-foreground text-xs">Overall</div><div className="font-semibold">{overall}</div></div>
        <div className="bg-muted rounded p-2"><div className="text-muted-foreground text-xs">Confidence</div><div className="font-semibold">{overallConf}</div></div>
      </div>
      <div className="mt-3 text-xs text-muted-foreground space-y-1">
        <div>Current price: {data.timeframes?.['15m']?.current_price?.toFixed(2) ?? data.timeframes?.['5m']?.current_price?.toFixed(2) ?? '—'}</div>
        <div>Prediction generated at: {new Date(data.generated_at).toLocaleString()}</div>
        <div>Data timestamp: {data.data_timestamp ? new Date(data.data_timestamp).toLocaleString() : '—'} • Age {data.data_age_seconds}s</div>
        <div>Model: {data.forecasts?.['15m']?.model_meta?.model_version ?? 'ensemble-v1'} • Feature v1 • Freshness {data.freshness}</div>
      </div>
      <p className="text-[11px] text-muted-foreground mt-2">Probabilistic estimate — not guaranteed. Confidence ≠ certainty.</p>
    </div>
  );
}
