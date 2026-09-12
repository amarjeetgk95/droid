'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, DirectionBadge, EmptyNote, RetryButton } from '@/components/ui/desk';

type Loose = Record<string, unknown>;

function str(v: unknown, fallback = '—'): string {
  if (v === null || v === undefined || v === '') return fallback;
  return String(v);
}

function num(v: unknown): string {
  return typeof v === 'number' && Number.isFinite(v) ? String(v) : '—';
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12.5, padding: '3px 0' }}>
      <span className="muted">{k}</span>
      <span className="num" style={{ textAlign: 'right' }}>{v}</span>
    </div>
  );
}

export function AIDeepInsightCard({ symbol }: { symbol: string }) {
  const aiSettings = useAISettings();
  const [data, setData] = useState<Loose | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const backendSymbol = toBackendSymbol(symbol);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = resolveAISettings(aiSettings);
      const res = await api.getDeepInsight(backendSymbol, {
        provider: r.provider,
        model: r.model,
        openRouterApiKey: r.openRouterApiKey,
        geminiApiKey: r.geminiApiKey,
      });
      if (res.error) throw new Error(res.error);
      setData(res.data as Loose);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Deep Insight failed');
    } finally {
      setLoading(false);
    }
  }, [backendSymbol, aiSettings]);

  useEffect(() => {
    if (!aiSettings) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- symbol-driven initial fetch
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendSymbol, aiSettings]);

  const market = (data?.market || {}) as Loose;
  const levels = (market.levels || {}) as Loose;
  const mtf = ((data?.multi_timeframe || []) as Loose[]).filter((t) => t && typeof t === 'object');
  const aiView = (data?.ai_view || {}) as Loose;
  const setup = (data?.setup || {}) as Loose;
  const signalState = (data?.signal_state || {}) as Loose;
  const validation = (data?.validation || {}) as Loose;
  const provider = (data?.provider || {}) as Loose;
  const optionsEv = (data?.options_evidence || {}) as Loose;
  const resolved = resolveAISettings(aiSettings);

  return (
    <Card
      title="AI Deep Insight"
      meta={`${backendSymbol} · regime + MTF + AI signal`}
      action={
        <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? 'Scanning…' : 'Refresh'}
        </button>
      }
    >
      {loading && !data ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 26, width: '45%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '80%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '65%' }}>.</div>
        </div>
      ) : error && !data ? (
        <div>
          <EmptyNote>Deep Insight unavailable — {error}</EmptyNote>
          <div style={{ marginTop: 10 }}><RetryButton onRetry={() => void load()} /></div>
        </div>
      ) : data ? (
        <div style={{ display: 'grid', gap: 14 }}>
          {data.error ? <EmptyNote>Partial data — {String(data.error)}</EmptyNote> : null}
          <div>
            <div className="toolbar" style={{ marginBottom: 6 }}>
              <DirectionBadge direction={market.direction || aiView.bias || 'NEUTRAL'} />
              <span className="card-meta num">{String(market.regime || data.regime || 'UNKNOWN').replace(/_/g, ' ')}</span>
              <span className="spacer" />
              <span className="faint mono" style={{ fontSize: 11 }}>
                {str(signalState.state, '')}{signalState.ttl_remaining != null ? ` · TTL ${str(signalState.ttl_remaining)}s` : ''}
              </span>
            </div>
            <Row k="Regime strength" v={num(market.regime_strength)} />
            <Row k="Volatility" v={str(market.volatility)} />
            <Row k="Price / VWAP" v={`${num(levels.current_price)} / ${num(levels.vwap)} (${str(levels.vwap_relation)})`} />
            <Row k="Support / Resistance" v={`${num(levels.support)} / ${num(levels.resistance)}`} />
            <Row k="Options" v={`${str(optionsEv.bias)} · PCR ${num(optionsEv.pcr)} · IV ${str(optionsEv.iv)}`} />
          </div>
          {mtf.length ? (
            <div>
              <div className="stat-l" style={{ marginBottom: 6 }}>Multi-timeframe</div>
              <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))' }}>
                {mtf.map((t, i) => (
                  <div className="stat" key={str(t.timeframe, String(i))}>
                    <div className="stat-l">{str(t.timeframe)}</div>
                    <div className="stat-v" style={{ fontSize: 13 }}>{str(t.direction)}</div>
                    <div className="stat-s num">{num(t.strength)} · {str(t.structure, '')}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div>
            <div className="stat-l" style={{ marginBottom: 6 }}>AI signal</div>
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>{str(aiView.summary, 'No active setup.')}</div>
            <div style={{ display: 'flex', gap: 10, fontSize: 12, marginTop: 4 }} className="muted">
              <span>Bias {str(aiView.bias)}</span>
              <span>Conf {str(aiView.confidence ?? aiView.calibrated_confidence)}</span>
              <span>Setup {str(aiView.setup_type ?? setup.setup_type)}</span>
            </div>
            <Row k="Entry zone" v={str(setup.entry_zone)} />
            <Row k="Stop / Target" v={`${num(setup.stop_loss)} / ${str(setup.target)}`} />
            <Row k="Validation" v={`${str(validation.status)}${validation.rejection_reason ? ` — ${str(validation.rejection_reason)}` : ''}`} />
            <Row k="Provider" v={`${str(provider.name, resolved.provider)} · ${str(provider.model, resolved.model)}${provider.latency_ms ? ` · ${str(provider.latency_ms)}ms` : ''}`} />
          </div>
          {error ? <p className="muted" style={{ fontSize: 12, margin: 0 }}>Refresh note: {error}</p> : null}
        </div>
      ) : (
        <EmptyNote>No Deep Insight yet — press Refresh.</EmptyNote>
      )}
    </Card>
  );
}

export default AIDeepInsightCard;
