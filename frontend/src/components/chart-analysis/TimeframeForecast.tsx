'use client';
export function TimeframeForecast({ data }: { data: any }) {
  if (!data?.forecasts) return null;
  const order: string[] = ['1m','5m','15m','1h'];
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-3">Multi-Timeframe Forecast</h3>
      <div className="space-y-2">
        {order.map(tf => {
          const fc = data.forecasts[tf];
          const tfData = data.timeframes[tf];
          if (!fc || !tfData) return null;
          const bias = tfData.bias;
          const arrow = bias==='BULLISH'?'↑':bias==='BEARISH'?'↓':'→';
          return (
            <div key={tf} className="flex items-center justify-between border border-border rounded px-3 py-2 text-sm">
              <span className="font-mono w-8">{tf}</span>
              <span>{arrow} {(fc.direction.up*100).toFixed(0)}% {bias}</span>
              <span className="text-muted-foreground">Score {tfData.score}</span>
              <span className="text-xs">Exp {fc.expected_move_percent.toFixed(2)}%</span>
              <span className={`px-2 py-0.5 rounded text-xs ${fc.confidence==='HIGH'?'bg-green-100 text-green-800':fc.confidence==='MODERATE'?'bg-yellow-100 text-yellow-800':'bg-muted'}`}>{fc.confidence}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
