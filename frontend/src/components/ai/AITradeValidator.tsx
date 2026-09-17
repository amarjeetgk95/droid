'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import type { AITradeValidationResponse } from '@/lib/types';
import { resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, EmptyNote, RetryButton, fmtNum } from '@/components/ui/desk';
import { AIProvenanceNote } from './AIProvenanceNote';
import { errorMessage, isTradeValidation } from './schema';

const DECISION_CLS: Record<string, string> = {
  CONFIRM: 'b-bull',
  REJECT: 'b-bear',
  WATCH: 'b-warn',
  UNCERTAIN: 'b-neut',
};

export function AITradeValidator({ symbol, spotPrice }: { symbol: string; spotPrice?: number | null }) {
  const aiSettings = useAISettings();
  const [direction, setDirection] = useState<'BUY' | 'SELL'>('BUY');
  const [entry, setEntry] = useState('');
  const [sl, setSl] = useState('');
  const [target, setTarget] = useState('');
  const [thesis, setThesis] = useState('');
  const [result, setResult] = useState<AITradeValidationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const backendSymbol = toBackendSymbol(symbol);
  const resolved = resolveAISettings(aiSettings);

  // Seed entry from the live spot exactly once per mount — never overwrite
  // user input on subsequent ticks.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current || !spotPrice || !Number.isFinite(spotPrice) || spotPrice <= 0) return;
    seededRef.current = true;
    setEntry(String(Math.round(spotPrice)));
  }, [spotPrice]);

  const run = async () => {
    if (!(Number(entry) > 0 && Number(sl) > 0 && Number(target) > 0)) {
      setError('Enter entry, stop loss and target before validating.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.validateTradeSetup({
        symbol: backendSymbol,
        direction,
        entry_price: Number(entry),
        stop_loss: Number(sl),
        target_price: Number(target),
        thesis_notes: thesis.trim() || null,
        provider: resolved.provider,
        model: resolved.model,
        allow_paid: resolved.allow_paid,
        openrouter_api_key: resolved.openRouterApiKey || null,
        gemini_api_key: resolved.geminiApiKey || null,
      });
      if (res.error) throw new Error(res.error);
      if (!res.data) throw new Error('The validator returned no result.');
      if (!isTradeValidation(res.data)) {
        throw new Error('The validation response was malformed (missing decision or verdict).');
      }
      setResult(res.data);
    } catch (err) {
      setError(errorMessage(err, 'Trade validation failed'));
    } finally {
      setLoading(false);
    }
  };

  const valid = Number(entry) > 0 && Number(sl) > 0 && Number(target) > 0;
  const invalidation = result && Array.isArray(result.invalidation_conditions) ? result.invalidation_conditions : [];
  const traps = result && Array.isArray(result.warning_traps) ? result.warning_traps : [];

  return (
    <Card
      title="AI Trade Auditor"
      meta={`${backendSymbol} · thesis vs live walls & regime`}
      action={
        <button type="button" className="btn btn-primary" onClick={() => void run()} disabled={loading || !valid}>
          {loading ? 'Auditing…' : 'Validate setup'}
        </button>
      }
    >
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
        <label style={{ fontSize: 12 }} className="muted">Side&nbsp;
          <select value={direction} onChange={(e) => setDirection(e.target.value as 'BUY' | 'SELL')} style={{ marginLeft: 4, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 8, padding: '6px 8px', fontSize: 12 }}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </label>
        {([
          ['Entry', entry, setEntry],
          ['Stop loss', sl, setSl],
          ['Target', target, setTarget],
        ] as const).map(([label, val, set]) => (
          <label key={label} style={{ fontSize: 12 }} className="muted">{label}&nbsp;
            <input value={val} onChange={(e) => set(e.target.value)} inputMode="decimal" placeholder="—" style={{ width: 110, marginLeft: 4, background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 8, padding: '6px 8px', fontSize: 12 }} />
          </label>
        ))}
      </div>
      <input
        value={thesis}
        onChange={(e) => setThesis(e.target.value)}
        placeholder="Thesis (optional) — e.g. breakout above VWAP with PCR support"
        aria-label="Trade thesis notes"
        style={{ width: '100%', background: 'var(--ds-inset)', border: '1px solid var(--ds-border)', borderRadius: 10, padding: '8px 12px', fontSize: 12.5, marginBottom: 10 }}
      />
      {error && !result ? (
        <div>
          <EmptyNote>Audit unavailable — {error}</EmptyNote>
          <div style={{ marginTop: 10 }}><RetryButton onRetry={() => void run()} /></div>
        </div>
      ) : result ? (
        <div style={{ display: 'grid', gap: 10 }}>
          <div className="toolbar">
            <span className={`badge ${DECISION_CLS[result.decision] || 'b-neut'}`}>{result.decision}</span>
            <span className="card-meta num">score {fmtNum(result.score, 0)} · RR {fmtNum(result.risk_reward_calculated)}</span>
          </div>
          <p style={{ fontSize: 13, lineHeight: 1.6, margin: 0 }}>{result.executive_verdict}</p>
          <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <div className="stat"><div className="stat-l">Technical</div><div style={{ fontSize: 12.5 }}>{result.technical_alignment}</div></div>
            <div className="stat"><div className="stat-l">Derivatives</div><div style={{ fontSize: 12.5 }}>{result.derivatives_alignment}</div></div>
            <div className="stat"><div className="stat-l">Volatility check</div><div style={{ fontSize: 12.5 }}>{result.volatility_regime_check}</div></div>
          </div>
          {invalidation.length ? (
            <div style={{ fontSize: 12.5 }}><strong>Invalidate if:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{invalidation.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
          ) : null}
          {traps.length ? (
            <div style={{ fontSize: 12.5 }} className="muted"><strong>Traps:</strong><ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{traps.map((c, i) => <li key={i}>{c}</li>)}</ul></div>
          ) : null}
          {error ? <p className="muted" style={{ fontSize: 12, margin: 0 }}>Refresh failed: {error}</p> : null}
          <AIProvenanceNote provider={result.provider_used || resolved.provider} />
        </div>
      ) : (
        <EmptyNote>{loading ? 'Auditing against live walls…' : valid ? 'Ready — press Validate setup.' : 'Enter entry / stop / target to audit.'}</EmptyNote>
      )}
    </Card>
  );
}

export default AITradeValidator;
