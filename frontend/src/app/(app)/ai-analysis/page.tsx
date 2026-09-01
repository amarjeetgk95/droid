'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { AIInsightResponse, AIHistoryItem } from '@/lib/types';
import { AIBiasBanner } from '@/components/ai/AIBiasBanner';
import { AIInsightSections } from '@/components/ai/AIInsightSections';
import { AIRiskDisclaimer } from '@/components/ai/AIRiskDisclaimer';
import { OpenRouterModelSelector } from '@/components/settings/OpenRouterModelSelector';
import { getStoredSettings } from '@/lib/settings';
import { History, Brain, Clock, TrendingUp, AlertTriangle, Activity } from 'lucide-react';

export default function AIAnalysisPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedProvider, setSelectedProvider] = useState<string>('mock_ai');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [allowPaid, setAllowPaid] = useState<boolean>(false);
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [analysisMeta, setAnalysisMeta] = useState<{ model_used?: string; latency_ms?: number } | null>(null);
  const [chartMulti, setChartMulti] = useState<any | null>(null);
  const [triggerMode, setTriggerMode] = useState<string>('manual');
  const [autoInterval, setAutoInterval] = useState<number>(60);

  // hydrate from stored settings
  useEffect(() => {
    try {
      const s = getStoredSettings();
      if (s.ai.openRouterSelectedModel) setSelectedModel(s.ai.openRouterSelectedModel);
      if (s.ai.openRouterAllowPaid !== undefined) setAllowPaid(s.ai.openRouterAllowPaid);
      if (s.ai.provider) setSelectedProvider(s.ai.provider === 'mock_ai' ? 'mock_ai' : s.ai.provider);
    } catch {}
  }, []);

  const fetchChartMulti = async (symbol: string) => {
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
      const res = await fetch(`${base}/api/v1/chart-analysis/${encodeURIComponent(symbol)}`);
      if (res.ok) {
        const j = await res.json();
        setChartMulti(j.data);
      }
    } catch {}
  };

  // helper to get key from Settings — no hardcode, primary source is Settings UI
  const getKeysForProvider = (prov: string) => {
    try {
      const s = getStoredSettings();
      if (prov === 'openrouter') return { openRouterApiKey: s.ai.openRouterApiKey || undefined };
      if (prov === 'gemini') return { geminiApiKey: s.ai.geminiApiKey || undefined, geminiModel: s.ai.geminiModel };
      if (prov === 'ollama') return { ollamaBaseUrl: s.ai.ollamaBaseUrl, ollamaModel: s.ai.ollamaModel };
    } catch {}
    return {};
  };

  // Initial load
  useEffect(() => {
    let isMounted = true;

    const fetchAnalysis = async () => {
      try {
        let res: any;
        if (selectedProvider === 'openrouter') {
          res = await api.generateAIAnalysisWithModel({
            symbol: selectedSymbol,
            model: selectedModel || 'auto',
            provider: 'openrouter',
            analysis_type: 'multi_timeframe',
            allow_paid: allowPaid,
            ...getKeysForProvider('openrouter'),
          });
        } else if (selectedProvider === 'gemini') {
          const k = getKeysForProvider('gemini');
          res = await api.generateAIAnalysis(selectedSymbol, selectedProvider, k as any);
        } else if (selectedProvider === 'ollama') {
          const k = getKeysForProvider('ollama');
          res = await api.generateAIAnalysis(selectedSymbol, selectedProvider, k as any);
        } else {
          res = await api.generateAIAnalysis(selectedSymbol, selectedProvider);
        }
        const histRes = await api.getAIHistory(selectedSymbol);
        if (isMounted) {
          setInsight(res.data);
          setAnalysisMeta({ model_used: res.model_used, latency_ms: res.latency_ms });
          setHistory(histRes.data);
          setError(null);
          fetchChartMulti(selectedSymbol);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to generate AI analysis');
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchAnalysis();
    return () => {
      isMounted = false;
    };
  }, [selectedSymbol, selectedProvider]);

  const handleGenerate = () => {
    setLoading(true);
    setError(null);
    const doGenerate = async () => {
      try {
        let res: any;
        if (selectedProvider === 'openrouter') {
          // validate not paid when freeOnly — key comes from Settings (no hardcode)
          res = await api.generateAIAnalysisWithModel({
            symbol: selectedSymbol,
            model: selectedModel || 'auto',
            provider: 'openrouter',
            analysis_type: 'multi_timeframe',
            allow_paid: allowPaid,
            ...getKeysForProvider('openrouter'),
          });
        } else if (selectedProvider === 'gemini' || selectedProvider === 'ollama') {
          const k = getKeysForProvider(selectedProvider);
          res = await api.generateAIAnalysis(selectedSymbol, selectedProvider, k as any);
          // fallback to model-aware endpoint if provider needs it
          if (!res?.data && selectedProvider === 'gemini') {
            res = await api.generateAIAnalysisWithModel({
              symbol: selectedSymbol,
              provider: 'gemini',
              ...k,
            });
          }
        } else {
          res = await api.generateAIAnalysis(selectedSymbol, selectedProvider);
        }
        setInsight(res.data);
        setAnalysisMeta({ model_used: res.model_used, latency_ms: res.latency_ms });
        setError(null);
        const h = await api.getAIHistory(selectedSymbol);
        setHistory(h.data);
        fetchChartMulti(selectedSymbol);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to generate AI analysis');
      } finally {
        setLoading(false);
      }
    };
    doGenerate();
  };

  // Trigger: auto interval (scheduled)
  useEffect(() => {
    if (triggerMode !== 'interval') return;
    const id = setInterval(() => {
      handleGenerate();
    }, autoInterval * 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerMode, autoInterval, selectedSymbol, selectedProvider, selectedModel, allowPaid]);

  // persist model choice to settings store
  const handleModelChange = (modelId: string) => {
    setSelectedModel(modelId);
    try {
      const s = getStoredSettings();
      s.ai.openRouterSelectedModel = modelId;
      s.ai.openRouterModel = modelId;
      // also persist via localStorage
      if (typeof window !== 'undefined') {
        localStorage.setItem('droid_app_settings_v1', JSON.stringify(s));
      }
    } catch {}
  };

  return (
    <div className="space-y-4">
      {/* Header & Bias Banner */}
      <AIBiasBanner
        insight={insight}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => setSelectedSymbol(sym)}
        selectedProvider={selectedProvider}
        onSelectProvider={(prov) => {
          setSelectedProvider(prov);
          try {
            const s = getStoredSettings();
            s.ai.provider = prov as any;
            localStorage.setItem('droid_app_settings_v1', JSON.stringify(s));
          } catch {}
        }}
        onGenerate={handleGenerate}
        loading={loading}
      />

      {/* Dynamic OpenRouter Selector when openrouter chosen */}
      {selectedProvider === 'openrouter' && (
        <div className="space-y-3">
          <OpenRouterModelSelector
            settings={{
              ...getStoredSettings().ai,
              openRouterSelectedModel: selectedModel,
              openRouterAllowPaid: allowPaid,
              openRouterFreeOnly: !allowPaid,
            } as any}
            onChange={(upd: any) => {
              if (upd.openRouterSelectedModel !== undefined) handleModelChange(upd.openRouterSelectedModel);
              if (upd.openRouterModel !== undefined) handleModelChange(upd.openRouterModel);
              if (upd.openRouterAllowPaid !== undefined) setAllowPaid(upd.openRouterAllowPaid);
              if (upd.openRouterFreeOnly !== undefined) setAllowPaid(!upd.openRouterFreeOnly);
            }}
          />
          {/* Trigger controls — avoid per-tick calls */}
          <div className="bg-card border border-border rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <Clock className="w-4 h-4 text-primary" />
              AI Analysis Triggers
              <span className="text-[10px] px-2 py-0.5 rounded bg-amber-500/10 text-amber-700 border border-amber-500/20">Not per-tick</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
              <div>
                <label className="font-semibold block mb-1">Trigger Mode</label>
                <select
                  value={triggerMode}
                  onChange={(e) => setTriggerMode(e.target.value)}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs cursor-pointer"
                >
                  <option value="manual">Manual Analyze button</option>
                  <option value="interval">Scheduled interval</option>
                  <option value="trend">Trend change</option>
                  <option value="breakout">Breakout / Breakdown</option>
                  <option value="oi">Major OI change</option>
                  <option value="volume">Major volume change</option>
                  <option value="news">Important news event</option>
                </select>
              </div>
              {triggerMode === 'interval' && (
                <div>
                  <label className="font-semibold block mb-1">Interval (seconds)</label>
                  <select
                    value={autoInterval}
                    onChange={(e) => setAutoInterval(parseInt(e.target.value))}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs cursor-pointer"
                  >
                    <option value={30}>30s (high freq)</option>
                    <option value={60}>60s</option>
                    <option value={120}>120s</option>
                    <option value={300}>5 min</option>
                  </select>
                </div>
              )}
              <div className="flex items-end">
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={loading}
                  className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg text-xs font-semibold disabled:opacity-50 cursor-pointer flex items-center justify-center gap-1.5"
                >
                  <Activity className="w-3.5 h-3.5" />
                  Manual Analyze
                </button>
              </div>
            </div>
            <p className="text-[11px] text-muted-foreground">
              AI is not called for every tick. Deterministic indicators (RSI, MACD, EMA, SMA, VWAP, ATR, ADX, Bollinger, S/R, Volume Profile, PCR, Futures positioning) are computed first; AI interprets the compact snapshot. Triggers: {triggerMode}.
              {analysisMeta?.model_used && <span className="ml-2 font-mono">Model: {analysisMeta.model_used} {analysisMeta.latency_ms && `• ${analysisMeta.latency_ms}ms`}</span>}
            </p>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      {error ? (
        <div className="p-8 text-center bg-card border border-destructive/20 rounded-xl text-destructive">
          <p className="font-semibold text-sm">Error generating market intelligence</p>
          <p className="text-xs mt-1 opacity-80">{error}</p>
        </div>
      ) : loading && !insight ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center text-muted-foreground animate-pulse space-y-2">
          <Brain className="w-8 h-8 text-primary mx-auto animate-bounce" />
          <p className="font-semibold text-sm">Synthesizing quantitative derivatives dossier...</p>
          <p className="text-xs text-muted-foreground">
            Analyzing PCR, Max Pain, Futures Basis, Buildup, S/R Pivots, and India VIX.
          </p>
        </div>
      ) : insight ? (
        <div className="space-y-4">
          {/* Probabilistic Outlook — not guaranteed prediction */}
          <div className="bg-card border border-primary/20 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-primary" />
                Probabilistic Outlook
                <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">Not Guaranteed</span>
              </h3>
              <span className="text-[11px] font-mono text-muted-foreground">
                {new Date(insight.timestamp).toLocaleTimeString()} • {insight.provider_used}
              </span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="bg-secondary/30 p-2.5 rounded-lg border">
                <div className="text-muted-foreground text-[11px]">Current Direction</div>
                <div className="font-bold text-sm">{insight.market_bias}</div>
              </div>
              <div className="bg-secondary/30 p-2.5 rounded-lg border">
                <div className="text-muted-foreground text-[11px]">Confidence</div>
                <div className="font-bold text-sm">{insight.confidence}%</div>
              </div>
              <div className="bg-secondary/30 p-2.5 rounded-lg border">
                <div className="text-muted-foreground text-[11px]">Risk</div>
                <div className="font-medium text-xs line-clamp-2">{insight.risk_management_notes?.slice(0, 80) || 'MEDIUM'}</div>
              </div>
              <div className="bg-secondary/30 p-2.5 rounded-lg border">
                <div className="text-muted-foreground text-[11px]">Model</div>
                <div className="font-mono text-xs truncate">{analysisMeta?.model_used || insight.provider_used}</div>
              </div>
            </div>
            {/* Multi-timeframe snapshot */}
            {chartMulti?.multi_timeframe && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                {['1m', '5m', '15m', '1h'].map((tf) => {
                  const tfData = chartMulti.multi_timeframe?.timeframes?.[tf] || chartMulti.timeframes?.[tf];
                  const bias = tfData?.bias || '—';
                  return (
                    <div key={tf} className="bg-secondary/20 p-2 rounded border text-center">
                      <div className="text-[10px] font-mono text-muted-foreground">{tf}</div>
                      <div className="font-semibold">{typeof bias === 'object' ? JSON.stringify(bias) : String(bias).slice(0, 20)}</div>
                      {tfData?.score !== undefined && <div className="text-[10px] text-muted-foreground">score {tfData.score}</div>}
                    </div>
                  );
                })}
              </div>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs pt-2 border-t border-border/50">
              <div>
                <div className="font-semibold text-foreground">Key Reasons</div>
                <div className="text-muted-foreground line-clamp-3">{insight.executive_summary?.slice(0, 240)}</div>
              </div>
              <div>
                <div className="font-semibold text-foreground">Support / Resistance</div>
                <div className="text-muted-foreground line-clamp-3">{insight.regime_and_levels?.slice(0, 200) || '—'}</div>
              </div>
              <div>
                <div className="font-semibold text-foreground">Warnings</div>
                <div className="text-muted-foreground line-clamp-3">{insight.risk_management_notes?.slice(0, 200) || '—'}</div>
              </div>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-amber-600">
              <AlertTriangle className="w-3 h-3" />
              Probabilistic assessment based on deterministic indicators (OHLC, RSI, MACD, EMA, SMA, VWAP, ATR, ADX, Bollinger, S/R, Volume Profile, Open Interest, PCR, Futures positioning). Not financial advice.
            </div>
          </div>

          {/* Structured Quantitative Analysis Cards */}
          <AIInsightSections insight={insight} />

          {/* Risk Management & Compliance Disclaimer */}
          <AIRiskDisclaimer
            riskNotes={insight.risk_management_notes}
            disclaimer={insight.disclaimer}
          />

          {/* Analysis History */}
          {history.length > 1 && (
            <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                <h3 className="font-bold text-xs text-foreground uppercase tracking-wider">
                  Recent Intelligence Reports ({history.length})
                </h3>
              </div>
              <div className="space-y-2">
                {history.slice(1, 5).map((h) => (
                  <div
                    key={h.id}
                    className="bg-secondary/30 p-2.5 rounded-lg border border-border flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-0.5">
                      <span className="font-mono font-semibold text-muted-foreground text-[10px]">
                        {new Date(h.timestamp).toLocaleTimeString('en-IN')}
                      </span>
                      <p className="text-foreground text-xs line-clamp-1">{h.executive_summary}</p>
                    </div>
                    <span className="shrink-0 text-[10px] px-2 py-0.5 rounded font-bold bg-secondary text-primary border border-border">
                      {h.market_bias} ({h.confidence}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
