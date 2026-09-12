'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { AIInsightResponse, AIHistoryItem, AIDailyBriefingResponse } from '@/lib/types';
import { buildAnalyzePayload, missingKeyHint, resolveAISettings, toBackendSymbol, useAISettings } from '@/lib/aiPayload';
import { Card, DirectionBadge, EmptyNote, Meter, RetryButton } from '@/components/ui/desk';

type Tab = 'analysis' | 'briefing' | 'history';

function Section({ label, text }: { label: string; text: string }) {
  if (!text) return null;
  return (
    <div className="stat">
      <div className="stat-l">{label}</div>
      <div style={{ fontSize: 12.5, lineHeight: 1.55, whiteSpace: 'pre-wrap' }}>{text}</div>
    </div>
  );
}

export function AIAnalysisCard({ symbol, contextPage }: { symbol: string; contextPage?: string }) {
  const aiSettings = useAISettings();
  const [tab, setTab] = useState<Tab>('analysis');
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [briefing, setBriefing] = useState<AIDailyBriefingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [meta, setMeta] = useState<{ model?: string; latency?: number } | null>(null);

  const backendSymbol = toBackendSymbol(symbol);
  const resolved = resolveAISettings(aiSettings);
  const keyHint = missingKeyHint(aiSettings);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = { ...buildAnalyzePayload(backendSymbol, aiSettings), analysis_type: 'multi_timeframe' };
      const [aRes, hRes, bRes] = await Promise.allSettled([
        api.generateAIAnalysisWithModel(payload as { symbol?: string; model?: string }),
        api.getAIHistory(backendSymbol),
        api.getMarketBriefing(backendSymbol, 'PRE_MARKET'),
      ]);
      if (aRes.status === 'fulfilled') {
        setInsight(aRes.value.data as AIInsightResponse);
        setMeta({ model: (aRes.value as { model_used?: string }).model_used, latency: (aRes.value as { latency_ms?: number }).latency_ms });
      } else {
        throw aRes.reason instanceof Error ? aRes.reason : new Error('AI analysis failed');
      }
      if (hRes.status === 'fulfilled') setHistory(hRes.value.data || []);
      if (bRes.status === 'fulfilled') setBriefing(bRes.value.data as AIDailyBriefingResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI analysis failed');
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

  return (
    <Card
      title="AI Analysis"
      meta={`${backendSymbol} · ${resolved.provider}:${resolved.model}${meta?.latency ? ` · ${meta.latency}ms` : ''}`}
      action={
        <button type="button" className="btn btn-primary" onClick={() => void load()} disabled={loading}>
          {loading ? 'Analyzing…' : insight ? 'Re-analyze' : 'Generate'}
        </button>
      }
    >
      {keyHint ? (
        <p className="muted" style={{ margin: '0 0 10px', fontSize: 12 }}>
          {keyHint} <Link href="/settings" style={{ textDecoration: 'underline' }}>Open Settings → AI Engine</Link>
        </p>
      ) : null}
      <div className="seg" role="tablist" aria-label="AI analysis views" style={{ marginBottom: 12 }}>
        {(['analysis', 'briefing', 'history'] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} className="seg-btn" data-active={tab === t} onClick={() => setTab(t)}>
            {t === 'analysis' ? 'Analysis' : t === 'briefing' ? 'Briefing' : `History${history.length ? ` (${history.length})` : ''}`}
          </button>
        ))}
      </div>

      {loading && !insight && tab === 'analysis' ? (
        <div style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 28, width: '40%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '90%' }}>.</div>
          <div className="skel" style={{ height: 14, width: '70%' }}>.</div>
        </div>
      ) : error && !insight ? (
        <div>
          <EmptyNote>AI analysis unavailable — {error}</EmptyNote>
          <div style={{ marginTop: 10 }}><RetryButton onRetry={() => void load()} /></div>
        </div>
      ) : tab === 'analysis' ? (
        insight ? (
          <div style={{ display: 'grid', gap: 12 }}>
            <div className="toolbar">
              <DirectionBadge direction={insight.market_bias} big />
              <span className="card-meta num">confidence {Math.round(Number(insight.confidence) || 0)}%</span>
              <span className="spacer" />
              <span className="faint mono" style={{ fontSize: 11 }}>{insight.provider_used || resolved.provider}{meta?.model ? ` · ${meta.model}` : ''}</span>
            </div>
            <Meter value={(Number(insight.confidence) || 0) / 100} />
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>{insight.simple_takeaway || insight.executive_summary}</div>
            {insight.simple_takeaway ? <div className="muted" style={{ fontSize: 12.5 }}>{insight.executive_summary}</div> : null}
            <Section label="Options reading" text={insight.options_interpretation} />
            <Section label="Futures flow" text={insight.futures_flow_analysis} />
            <Section label="Regime & levels" text={insight.regime_and_levels} />
            <Section label="Strategy framework" text={insight.recommended_strategy_framework} />
            <Section label="Risk notes" text={insight.risk_management_notes} />
            {error ? <p className="muted" style={{ fontSize: 12, margin: 0 }}>Refresh note: {error}</p> : null}
            <p className="faint" style={{ fontSize: 11, margin: 0 }}>{insight.disclaimer || 'For research & education — not financial advice.'}{contextPage ? ` · ${contextPage}` : ''}</p>
          </div>
        ) : (
          <EmptyNote>No analysis yet — press Generate.</EmptyNote>
        )
      ) : tab === 'briefing' ? (
        briefing ? (
          <div style={{ display: 'grid', gap: 10 }}>
            <div style={{ fontSize: 13, lineHeight: 1.6 }}>{briefing.executive_summary}</div>
            <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
              {Object.entries(briefing.key_levels_to_watch || {}).map(([k, v]) => (
                <div className="stat" key={k}>
                  <div className="stat-l">{k}</div>
                  <div className="stat-v num">{typeof v === 'number' ? v.toLocaleString('en-IN') : String(v)}</div>
                </div>
              ))}
            </div>
            <Section label="Options pin & pivots" text={briefing.options_pin_and_pivots} />
            <Section label="FII / DII read" text={briefing.fii_dii_implication} />
            {(briefing.actionable_playbook || []).length ? (
              <div className="stat">
                <div className="stat-l">Playbook</div>
                <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 12.5, display: 'grid', gap: 4 }}>
                  {briefing.actionable_playbook.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyNote>{loading ? 'Loading briefing…' : 'No briefing — press Generate.'}</EmptyNote>
        )
      ) : history.length ? (
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 8 }}>
          {history.slice(0, 8).map((h) => (
            <li key={h.id} style={{ display: 'flex', gap: 10, alignItems: 'baseline', fontSize: 12.5 }}>
              <DirectionBadge direction={h.market_bias} />
              <span className="num faint">{Math.round(Number(h.confidence) || 0)}%</span>
              <span style={{ flex: 1 }}>{h.executive_summary}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyNote>{loading ? 'Loading history…' : 'No prior analyses for this symbol.'}</EmptyNote>
      )}
    </Card>
  );
}

export default AIAnalysisCard;
