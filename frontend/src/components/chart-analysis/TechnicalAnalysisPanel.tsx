'use client';
export function TechnicalAnalysisPanel({ data, timeframe='15m' }: { data: any; timeframe?: string }) {
  const tf = data?.timeframes?.[timeframe];
  if (!tf) return null;
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">Technical Analysis ({timeframe})</h3>
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div>Trend: <b>{tf.trend.trend}</b> ({tf.trend.score})</div>
        <div>Structure: {tf.price_action.structure}</div>
        <div>Momentum: {tf.momentum.momentum} (RSI {tf.momentum.rsi})</div>
        <div>Volatility: {tf.volatility.classification} ATR {tf.volatility.atr}</div>
        <div>Volume: {tf.volume.available ? `${tf.volume.relationship}` : 'Unavailable'}</div>
        <div>Overall Score: <b>{tf.scores.overall}/100</b></div>
      </div>
      {tf.candlestick.summary.count>0 && <p className="text-xs mt-2">Candlestick: {tf.candlestick.summary.pattern} ({tf.candlestick.summary.bias})</p>}
      {tf.divergences.length>0 && <p className="text-xs">Divergences: {tf.divergences.map((d:any)=>d.type).join(', ')}</p>}
    </div>
  );
}
