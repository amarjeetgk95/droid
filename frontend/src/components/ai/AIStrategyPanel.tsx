'use client';

import { useState } from 'react';
import { api } from '@/lib/api';
import type { AIOptionsStrategyRecommendation } from '@/lib/types';
import { resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, EmptyNote, RetryButton } from '@/components/ui/desk';
import { AIProvenanceNote } from './AIProvenanceNote';
import { errorMessage, isStrategyRecommendation } from './schema';

type Outlook = 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'HIGH_VOLATILITY' | 'LOW_VOLATILITY' | 'DIRECTIONAL_RANGE';

export function AIStrategyPanel({ symbol }: { symbol: string }) {
  const aiSettings = useAISettings();
  const [outlook, setOutlook] = useState<Outlook>('NEUTRAL');
  const [risk, setRisk] = useState<'LOW' | 'MODERATE' | 'AGGRESSIVE'>('MODERATE');
  const [dte, setDte] = useState<string>('7');
  const [query, setQuery] = useState('');
  const [rec, setRec] = useState<AIOptionsStrategyRecommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const backendSymbol = toBackendSymbol(symbol);
  const resolved = resolveAISettings(aiSettings);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const dteNum = Number(dte);
      const res = await api.recommendOptionsStrategy({
        symbol: backendSymbol,
        outlook,
        custom_query: query.trim() || null,
        target_dte: dte.trim() && Number.isFinite(dteNum) && dteNum > 0 ? dteNum : null,
        max_risk_tolerance: risk,
        provider: resolved.provider,
        model: resolved.model,
        allow_paid: resolved.allow_paid,
        openrouter_api_key: resolved.openRouterApiKey || null,
        gemini_api_key: resolved.geminiApiKey || null,
      });
      if (res.error) throw new Error(res.error);
      if (!res.data) throw new Error('The strategy service returned no recommendation.');
      if (!isStrategyRecommendation(res.data)) {
        // Malformed payload cannot be rendered (legs/name missing) — drop it so
        // the schema error is visible instead of a crash or a stale render.
        setRec(null);
        throw new Error('The strategy response was malformed (missing strategy name or option legs).');
      }
      setRec(res.data);
    } catch (err) {
      setError(errorMessage(err, 'Strategy recommendation failed'));
    } finally {
      setLoading(false);
    }
  };

  const legs = rec && Array.isArray(rec.legs) ? rec.legs : [];
  const breakevens = rec && Array.isArray(rec.breakevens) ? rec.breakevens : [];
  const entryRules = rec && Array.isArray(rec.entry_rules) ? rec.entry_rules : [];
  const exitRules = rec && Array.isArray(rec.exit_rules) ? rec.exit_rules : [];

  return (
    <Card
      title="AI Strategy Architect"
      meta={`${backendSymbol} · risk-defined spreads`}
      action={
        <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={loading}>
          {loading ? 'Designing…' : 'Recommend'}
        </button>
      }
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        <label style={{ fontSize: 12 }} className="muted">Outlook&nbsp;
          <select value={outlook} onChange={(e) => setOutlook(e.target.value as Outlook)} style={{ marginLeft: 4, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 8, padding: '6px 8px', fontSize: 12 }}>
            {(['BULLISH', 'BEARISH', 'NEUTRAL', 'HIGH_VOLATILITY', 'LOW_VOLATILITY', 'DIRECTIONAL_RANGE'] as Outlook[]).map((o) => (
              <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </label>
        <label style={{ fontSize: 12 }} className="muted">Risk&nbsp;
          <select value={risk} onChange={(e) => setRisk(e.target.value as typeof risk)} style={{ marginLeft: 4, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 8, padding: '6px 8px', fontSize: 12 }}>
            <option value="LOW">LOW</option>
            <option value="MODERATE">MODERATE</option>
            <option value="AGGRESSIVE">AGGRESSIVE</option>
          </select>
        </label>
        <label style={{ fontSize: 12 }} className="muted">DTE&nbsp;
          <input value={dte} onChange={(e) => setDte(e.target.value)} inputMode="numeric" placeholder="7" style={{ width: 64, marginLeft: 4, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 8, padding: '6px 8px', fontSize: 12 }} />
        </label>
      </div>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Custom view (optional) — e.g. expect pin near max pain into expiry"
        aria-label="Custom strategy query"
        style={{ width: '100%', background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 10, padding: '8px 12px', fontSize: 12.5, marginBottom: 10 }}
      />
      {error && !rec ? (
        <div>
          <EmptyNote>Strategy unavailable — {error}</EmptyNote>
          <div style={{ marginTop: 10 }}><RetryButton onRetry={() => void run()} /></div>
        </div>
      ) : rec ? (
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="toolbar">
            <strong style={{ fontSize: 14 }}>{rec.strategy_name}</strong>
            <span className="card-meta num">{rec.market_outlook} · RR {rec.risk_reward_ratio}</span>
          </div>
          <p style={{ fontSize: 12.5, lineHeight: 1.6, margin: 0 }}>{rec.rationale}</p>
          {legs.length ? (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
                <thead>
                  <tr className="muted" style={{ textAlign: 'left' }}>
                    <th style={{ padding: '4px 6px' }}>Leg</th>
                    <th style={{ padding: '4px 6px' }}>Strike</th>
                    <th style={{ padding: '4px 6px' }}>Type</th>
                    <th style={{ padding: '4px 6px' }}>Premium</th>
                    <th style={{ padding: '4px 6px' }}>Δ / θ</th>
                  </tr>
                </thead>
                <tbody>
                  {legs.map((l, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--ds-border)' }}>
                      <td style={{ padding: '4px 6px' }}><span className={`badge ${l.action === 'BUY' ? 'b-bull' : 'b-bear'}`}>{l.action}</span></td>
                      <td className="num" style={{ padding: '4px 6px' }}>{l.strike}</td>
                      <td style={{ padding: '4px 6px' }}>{l.option_type}{l.expiry ? ` · ${l.expiry}` : ''}</td>
                      <td className="num" style={{ padding: '4px 6px' }}>{l.estimated_premium}</td>
                      <td className="num" style={{ padding: '4px 6px' }}>{l.delta ?? '—'} / {l.theta ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
            <div className="stat"><div className="stat-l">Max profit</div><div className="stat-v num" style={{ fontSize: 13 }}>{rec.max_profit_pts}</div></div>
            <div className="stat"><div className="stat-l">Max loss</div><div className="stat-v num" style={{ fontSize: 13 }}>{rec.max_loss_pts}</div></div>
            <div className="stat"><div className="stat-l">Net debit/credit</div><div className="stat-v num" style={{ fontSize: 13 }}>{rec.net_debit_credit_pts}</div></div>
            <div className="stat"><div className="stat-l">Breakevens</div><div className="stat-v num" style={{ fontSize: 13 }}>{breakevens.length ? breakevens.join(' / ') : '—'}</div></div>
          </div>
          {entryRules.length ? (
            <div style={{ fontSize: 12.5 }}><strong>Entry:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{entryRules.map((r, i) => <li key={i}>{r}</li>)}</ul></div>
          ) : null}
          {exitRules.length ? (
            <div style={{ fontSize: 12.5 }}><strong>Exit:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{exitRules.map((r, i) => <li key={i}>{r}</li>)}</ul></div>
          ) : null}
          <div className="muted" style={{ fontSize: 12 }}>{rec.risk_management}</div>
          {error ? <p className="muted" style={{ fontSize: 12, margin: 0 }}>Refresh failed: {error}</p> : null}
          <AIProvenanceNote provider={rec.provider_used || resolved.provider} />
        </div>
      ) : (
        <EmptyNote>{loading ? 'Designing strategy…' : 'Pick an outlook and press Recommend.'}</EmptyNote>
      )}
    </Card>
  );
}

export default AIStrategyPanel;
