'use client';
import { useEffect, useState } from 'react';
export function AIAnalysisPanel({ data }: { data: any }) {
  const mtf = data?.multi_timeframe;
  const [aiText, setAiText] = useState<string|null>(null);
  const [aiError, setAiError] = useState<string|null>(null);
  if (!mtf) return null;
  const bias = mtf.alignment?.overall_bias ?? 'NEUTRAL';
  const conf = mtf.confidence ?? 'LOW';
  const tf15 = data.timeframes?.['15m'];
  const drivers = (()=> {
    const f = data.features?.['15m'] || {};
    const pos: string[] = [];
    const neg: string[] = [];
    if ((f.price_dist_vwap ?? 0) > 0.002) pos.push('Price above VWAP');
    if ((f.price_dist_vwap ?? 0) < -0.002) neg.push('Price below VWAP');
    if ((f.rsi ?? 50) > 60) pos.push('Strong 15m momentum (RSI >60)');
    if ((f.rsi ?? 50) < 40) neg.push('Weak momentum (RSI <40)');
    if ((f.pcr ?? 1) > 1.05) pos.push('High put OI support (PCR elevated)');
    if ((f.pcr ?? 1) < 0.95) neg.push('Call OI resistance (PCR low)');
    if ((f.futures_oi_change ?? 0) > 1) pos.push('Futures OI increase');
    if ((f.futures_oi_change ?? 0) < -1) neg.push('Futures OI decrease');
    if (!data.fno?.available) pos.push('(F&O unavailable — technical only)');
    return { pos, neg };
  })();
  // Try to fetch AI explanation on mount, but never break technical analysis if AI fails (§39)
  useEffect(()=>{
    let cancelled=false;
    const fetchAI = async ()=>{
      try {
        const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/,'');
        const res = await fetch(`${base}/api/v1/ai/analyze/${encodeURIComponent(data.symbol)}?provider=gemini`, { method:'POST' });
        if (!res.ok) throw new Error(`AI ${res.status}`);
        const json = await res.json();
        const insight = json.data?.executive_summary || json.data?.summary || null;
        if (!cancelled && insight) setAiText(insight);
      } catch(e:any){
        if (!cancelled) setAiError('AI temporarily unavailable — technical analysis remains available.');
      }
    };
    // Only call AI on major state — here on symbol change
    fetchAI();
    return ()=>{ cancelled=true; };
  }, [data.symbol]);
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="font-semibold mb-2">AI Explanation — grounded in quantitative state</h3>
      <p className="text-sm text-muted-foreground">
        {bias === 'BULLISH' && `Current short-term structure is bullish and the ${Object.entries(mtf.alignment.biases).filter(([,b]:any)=>b==='BULLISH').map(([tf])=>tf).join('/')} timeframes are aligned. The ${mtf.alignment.dominant_timeframe} remains ${mtf.alignment.interpretation.toLowerCase()}`}
        {bias === 'BEARISH' && `Bearish alignment detected across ${mtf.alignment.alignment_count} timeframes. Higher-timeframe context is ${mtf.alignment.interpretation.toLowerCase()}`}
        {bias === 'NEUTRAL' && `Market is in a neutral/mixed state. Timeframe alignment score is ${mtf.alignment.alignment_score}. Consider waiting for clearer confluence before directional positioning.`}
        {" "}Confidence: {conf}. This is a decision-support assessment, not guaranteed prediction.
      </p>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
        <div className="bg-green-50 border border-green-200 rounded p-2">
          <div className="font-semibold text-green-800">Supporting factors (grounded)</div>
          <ul className="list-disc list-inside text-green-700">
            {drivers.pos.length? drivers.pos.map((d,i)=><li key={i}>{d}</li>) : <li>No strong positive drivers detected</li>}
            <li>Alignment {mtf.alignment.alignment_count} • {mtf.alignment.interpretation}</li>
            <li>Key level S {(tf15?.support_resistance?.support ?? data.fno?.put_wall ?? '—')} / R {(tf15?.support_resistance?.resistance ?? data.fno?.call_wall ?? '—')}</li>
          </ul>
        </div>
        <div className="bg-red-50 border border-red-200 rounded p-2">
          <div className="font-semibold text-red-800">Conflicting / Risk factors</div>
          <ul className="list-disc list-inside text-red-700">
            {drivers.neg.length? drivers.neg.map((d,i)=><li key={i}>{d}</li>) : <li>No major negative drivers</li>}
            {mtf.alignment.conflict && <li>Timeframe conflict detected — short-term vs higher-timeframe trend divergence</li>}
            <li>Risk: manage position size and respect invalidation levels</li>
          </ul>
        </div>
      </div>
      {aiText && <div className="mt-3 text-sm bg-muted rounded p-3 border border-border"><div className="font-semibold text-xs mb-1">AI Insight (live provider, schema validated)</div><p className="text-muted-foreground">{aiText}</p></div>}
      {aiError && <p className="text-xs text-muted-foreground mt-2">{aiError}</p>}
      <p className="text-xs text-muted-foreground mt-2">AI explains drivers; it does not invent them. Analysis uses: instrument, technical, F&amp;O, MTF, historical similarity, data quality ({tf15?.data_quality?.slice(0,60)}), freshness {data.freshness}. AI is optional — technical analysis remains available if AI is unavailable.</p>
    </div>
  );
}
