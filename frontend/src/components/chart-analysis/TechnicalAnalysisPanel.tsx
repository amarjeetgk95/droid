'use client';
export function TechnicalAnalysisPanel({ data, timeframe='15m' }: { data: any; timeframe?: string }) {
  const tf = data?.timeframes?.[timeframe];
  if (!tf) return null;
  const scores = tf.scores || {};
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">TECHNICAL ANALYSIS — {timeframe}</h3>
      <div className="space-y-1 text-sm">
        <div className="grid grid-cols-2 gap-2">
          <div>Trend: <b className={tf.trend.trend==='BULLISH'?'text-green-600':tf.trend.trend==='BEARISH'?'text-red-600':'text-amber-600'}>{tf.trend.trend}</b> ({tf.trend.score})</div>
          <div>Structure: {tf.price_action.structure} {tf.price_action.hh_hl ? `• ${tf.price_action.hh_hl}`:''}</div>
          <div>Momentum: {tf.momentum.momentum} <span className="text-muted-foreground">(RSI {Number(tf.momentum.rsi).toFixed(0)} • MACD {tf.momentum.macd_histogram>0?'▲':'▼'})</span></div>
          <div>Volatility: {tf.volatility.classification} <span className="text-muted-foreground">ATR {Number(tf.volatility.atr).toFixed(2)} ({tf.volatility.atr_pct?.toFixed(2)}%)</span></div>
          <div>Volume: {tf.volume.available ? `${tf.volume.relationship} (${tf.volume.relative_volume?.toFixed(2)}x)` : 'Unavailable — technical & ML continue without F&O/volume'}</div>
          <div>Pattern: {tf.candlestick?.summary?.pattern ?? tf.chart_patterns?.[0]?.pattern ?? 'None'} {tf.divergences?.length>0 && `• Div ${tf.divergences.length}`}</div>
        </div>
        <div className="border-t border-border pt-2 mt-2">
          <div className="text-xs text-muted-foreground mb-1">Confluence Scores (documented, configurable, versioned v1)</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div>Trend {scores.trend ?? tf.trend.score}/100</div>
            <div>Momentum {scores.momentum ?? tf.momentum.score ?? 50}/100</div>
            <div>Volume {scores.volume ?? tf.volume.score ?? '—'}/100</div>
            <div>Volatility {scores.volatility ?? tf.volatility.score ?? 50}/100</div>
            <div>Structure {scores.structure ?? 60}/100</div>
            <div>Overall <b>{scores.overall ?? tf.score}/100</b></div>
          </div>
          <div className="text-xs mt-1">Support {tf.support_resistance?.support?.toFixed(2) ?? '—'} • Resistance {tf.support_resistance?.resistance?.toFixed(2) ?? '—'} {tf.support_resistance?.confluence && `(Confluence ${tf.support_resistance.confluence})`}</div>
        </div>
        {tf.candlestick?.summary?.count>0 && <p className="text-xs mt-2">Candlestick: {tf.candlestick.summary.pattern} ({tf.candlestick.summary.bias}) — {tf.candlestick.summary.count} patterns</p>}
        {tf.chart_patterns?.length>0 && <p className="text-xs">Chart patterns: {tf.chart_patterns.map((p:any)=>`${p.pattern} (${p.bias})`).join(', ')}</p>}
        {tf.divergences?.length>0 && <p className="text-xs">Divergences: {tf.divergences.map((d:any)=>`${d.type} ${d.indicator}`).join(', ')}</p>}
        <p className="text-[11px] text-muted-foreground mt-2">Grouped scoring methodology documented and versioned (v1). Do not treat all indicators equally. Analysis is decision support — not guaranteed.</p>
      </div>
    </div>
  );
}
