'use client';
export function ForecastSummary({ data }: { data: any }) {
  if (!data?.forecasts) return null;
  const order = data?.chart_timeframes || ['1m','5m','15m','1h','4h','1D'];
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Expected Future Movement — Instrument → Timeframe → Current Price → Market Regime → Technical Bias → Derivatives Bias → AI Forecast → Confidence → Key Levels → Risk/Invalidation</h3>
      {order.map((tf: string) => {
        const fc: any = data.forecasts[tf];
        if (!fc) return null;
        if ((fc as any).data_unavailable) {
          return <div key={tf} className="text-sm flex justify-between border border-dashed border-amber-200 rounded px-2 py-1 bg-amber-50/50"><span>{tf === '1D' ? 'Daily' : tf}</span><span className="text-amber-700">Data unavailable</span><span className="text-muted-foreground">—</span></div>;
        }
        return (
          <div key={tf} className="text-sm flex justify-between">
            <span>{tf === '1D' ? 'Daily' : tf} ({fc.horizon_minutes}m)</span>
            <span>{fc.expected_range.low.toFixed(0)} – {fc.expected_range.high.toFixed(0)} ({fc.expected_move_percent.toFixed(2)}%)</span>
            <span className="text-muted-foreground">Invalidation {fc.invalidation_level ?? '—'} {fc.confidence === 'LOW' && fc.data_unavailable !== true ? '• Mixed / Low Confidence' : ''}</span>
          </div>
        );
      })}
      {data.timeframes?.['15m'] && !(data.timeframes['15m'] as any).data_unavailable && (
        <div className="mt-2 text-sm">
          Support: {data.timeframes['15m'].support_resistance.support} • Resistance: {data.timeframes['15m'].support_resistance.resistance}
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-2">Probabilistic forecast — not guaranteed. Bullish probability shown where applicable. Instrument universe fixed: NIFTY | BANKNIFTY | FINNIFTY | SENSEX | BTC | ETH | SOL.</p>
    </div>
  );
}
