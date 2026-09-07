'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useDeepInsight, DeepInsightProvider } from '@/context/DeepInsightContext';
import { DeepInsightPanel } from '@/components/ai/DeepInsightPanel';
import { AIExecutiveHero } from '@/components/ai/AIExecutiveHero';
import { AIQuantPillars } from '@/components/ai/AIQuantPillars';
import { AITradePlaybook } from '@/components/ai/AITradePlaybook';
import { JargonBuster } from '@/components/ai/JargonBuster';
import { AIOptionsArchitect } from '@/components/ai/AIOptionsArchitect';
import { AITradeValidator } from '@/components/ai/AITradeValidator';
import { OpenRouterModelSelector } from '@/components/settings/OpenRouterModelSelector';
import { PageTabs, PageTabItem } from '@/components/ui/PageTabs';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import { AIInsightResponse, AIHistoryItem } from '@/lib/types';
import { getStoredSettings } from '@/lib/settings';
import {
  Brain,
  Zap,
  RefreshCw,
  History as HistoryIcon,
  Layers,
  ShieldCheck,
  ShieldAlert,
  Clock,
  Columns,
  Sparkles,
  SlidersHorizontal,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Wrench,
  Radio,
} from 'lucide-react';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

function AICommandCenterContent() {
  const { state: deepInsightState, symbol, setSymbol, evaluate } = useDeepInsight();

  // Research states
  const [selectedProvider, setSelectedProvider] = useState<string>('openrouter');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [allowPaid, setAllowPaid] = useState<boolean>(false);
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [researchLoading, setResearchLoading] = useState<boolean>(true);
  const [researchError, setResearchError] = useState<string | null>(null);
  const [showModelSelector, setShowModelSelector] = useState<boolean>(false);
  const [splitView, setSplitView] = useState<boolean>(false);

  // Hydrate provider & model settings on mount
  useEffect(() => {
    try {
      const s = getStoredSettings();
      if (s.ai.openRouterSelectedModel) setSelectedModel(s.ai.openRouterSelectedModel);
      if (s.ai.openRouterAllowPaid !== undefined) setAllowPaid(s.ai.openRouterAllowPaid);
      const connMode = (s.ai as unknown as { connectionMode?: string }).connectionMode;
      const directProv = (s.ai as unknown as { directProvider?: string }).directProvider;
      if (connMode === 'OpenRouter') {
        setSelectedProvider('openrouter');
      } else if (connMode === 'Local Ollama') {
        setSelectedProvider('ollama');
      } else if (connMode === 'Direct Provider' && directProv) {
        const map: Record<string, string> = {
          OpenAI: 'openai',
          'Novita AI': 'novita',
          NVIDIA: 'nvidia',
          'Google Gemini': 'gemini',
          'Custom OpenAI-Compatible': 'custom_openai',
        };
        setSelectedProvider(map[directProv] || 'openai');
      } else if (s.ai.provider) {
        setSelectedProvider(s.ai.provider === 'mock_ai' ? 'openrouter' : s.ai.provider);
      }
    } catch {}
  }, []);

  const buildUnifiedPayload = useCallback((sym: string, providerOverride?: string) => {
    try {
      const s = getStoredSettings();
      const a = s.ai as any;
      let effectiveProvider = providerOverride || selectedProvider || 'openrouter';
      if (effectiveProvider === 'mock_ai') effectiveProvider = 'openrouter';

      const base: Record<string, unknown> = {
        symbol: sym,
        provider: effectiveProvider,
        analysis_type: 'multi_timeframe',
      };
      if (effectiveProvider === 'openrouter') {
        base.model = selectedModel || a.openRouterSelectedModel || 'auto';
        base.allow_paid = allowPaid ?? a.openRouterAllowPaid ?? false;
        if (a.openRouterApiKey) base.openRouterApiKey = a.openRouterApiKey;
      } else if (effectiveProvider === 'gemini') {
        base.geminiApiKey = a.geminiApiKey;
        base.geminiModel = a.geminiModel;
      } else if (effectiveProvider === 'ollama') {
        base.ollamaBaseUrl = a.ollamaBaseUrl;
        base.ollamaModel = a.ollamaModel;
      } else if (effectiveProvider === 'openai') {
        base.openaiApiKey = a.openaiApiKey;
        base.openaiModel = a.openaiModel;
        if (a.openaiBaseUrl) base.openaiBaseUrl = a.openaiBaseUrl;
        base.model = a.openaiModel;
      }
      return base;
    } catch {
      return {
        symbol: sym,
        provider: providerOverride || selectedProvider || 'openrouter',
        model: selectedModel || 'auto',
        analysis_type: 'multi_timeframe',
        allow_paid: allowPaid,
      };
    }
  }, [selectedProvider, selectedModel, allowPaid]);

  const fetchResearch = useCallback(async (sym: string, prov?: string) => {
    setResearchLoading(true);
    setResearchError(null);
    try {
      const payload = buildUnifiedPayload(sym, prov);
      const res: any = await api.generateAIAnalysisWithModel(payload as any);
      setInsight(res.data);
      const histRes = await api.getAIHistory(sym);
      setHistory(histRes.data || []);
    } catch (err: any) {
      setResearchError(err instanceof Error ? err.message : 'Failed to generate AI research report');
    } finally {
      setResearchLoading(false);
    }
  }, [buildUnifiedPayload]);

  // Initial load and symbol change: evaluate live signal & fetch research
  useEffect(() => {
    evaluate(symbol);
    fetchResearch(symbol, selectedProvider);
  }, [symbol, selectedProvider, evaluate, fetchResearch]);

  // Unified refresh handler
  const handleRefreshAll = useCallback(() => {
    evaluate(symbol);
    fetchResearch(symbol, selectedProvider);
  }, [evaluate, fetchResearch, symbol, selectedProvider]);

  const handleModelChange = (modelId: string) => {
    setSelectedModel(modelId);
    try {
      const s = getStoredSettings();
      s.ai.openRouterSelectedModel = modelId;
      s.ai.openRouterModel = modelId;
      if (typeof window !== 'undefined') {
        localStorage.setItem('droid_app_settings_v1', JSON.stringify(s));
      }
    } catch {}
  };

  // Telemetry items from Deep Insight state
  const spot = deepInsightState.market?.levels?.current_price;
  const regime = deepInsightState.market?.regime;
  const bias = deepInsightState.aiView?.bias;
  const valStatus = deepInsightState.validation?.status;
  const ttlRemaining = deepInsightState.signalState?.ttl_remaining ?? 0;
  const isRefreshing = deepInsightState.status === 'loading' || researchLoading;

  // Tabs configuration
  const tabs: PageTabItem[] = useMemo(() => [
    {
      id: 'signal',
      label: 'Live Signal',
      icon: Radio,
      badge: bias ? bias : undefined,
      badgeClassName:
        bias === 'LONG'
          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
          : bias === 'SHORT'
          ? 'bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/30'
          : 'bg-muted text-muted-foreground',
      content: (
        <div className="h-[calc(100vh-12rem)] min-h-[600px] flex flex-col min-h-0">
          <DeepInsightPanel />
        </div>
      ),
    },
    {
      id: 'research',
      label: 'AI Research & Playbook',
      icon: Brain,
      badge: insight?.market_bias ? insight.market_bias : undefined,
      badgeClassName:
        insight?.market_bias === 'BULLISH'
          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
          : insight?.market_bias === 'BEARISH'
          ? 'bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/30'
          : 'bg-muted text-muted-foreground',
      content: (
        <div className="space-y-5">
          {researchError ? (
            <div className="p-6 text-center bg-card border border-destructive/20 rounded-2xl text-destructive space-y-2 shadow-xs">
              <div className="flex items-center justify-center gap-2 text-destructive">
                <AlertCircle className="w-5 h-5" />
                <p className="font-semibold text-sm">Could not read the market right now</p>
              </div>
              <p className="text-xs opacity-80">{researchError}</p>
              <button
                onClick={() => fetchResearch(symbol, selectedProvider)}
                className="mt-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer hover:bg-primary/90 transition-all"
              >
                Try again
              </button>
            </div>
          ) : researchLoading && !insight ? (
            <div className="bg-card border border-border rounded-2xl p-14 text-center text-muted-foreground animate-pulse space-y-3">
              <Brain className="w-10 h-10 text-primary mx-auto animate-bounce" />
              <p className="font-bold text-sm text-foreground">Reading the market for {symbol}…</p>
              <p className="text-xs text-muted-foreground">
                Analyzing price action, institutional options positioning, and macro sentiment.
              </p>
            </div>
          ) : insight ? (
            <div className="space-y-5 animate-in fade-in duration-300">
              <AIExecutiveHero insight={insight} symbol={symbol} />
              <JargonBuster />
              <AIQuantPillars insight={insight} />
              <AITradePlaybook insight={insight} />
            </div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'tools',
      label: 'Strategy & Risk Tools',
      icon: Wrench,
      content: (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="bg-card border border-border rounded-2xl p-4 space-y-3 shadow-xs">
            <div className="flex items-center gap-2.5 pb-2 border-b border-border/70">
              <div className="p-1.5 bg-primary/10 rounded-lg text-primary">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-foreground">Options Strategy Helper</h3>
                <p className="text-[11px] text-muted-foreground">Build risk-defined options spreads for {symbol}</p>
              </div>
            </div>
            <AIOptionsArchitect selectedSymbol={symbol} />
          </div>

          <div className="bg-card border border-border rounded-2xl p-4 space-y-3 shadow-xs">
            <div className="flex items-center gap-2.5 pb-2 border-b border-border/70">
              <div className="p-1.5 bg-emerald-500/10 rounded-lg text-emerald-500">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-foreground">Check My Trade Idea</h3>
                <p className="text-[11px] text-muted-foreground">AI-assisted risk & validation auditor for {symbol}</p>
              </div>
            </div>
            <AITradeValidator selectedSymbol={symbol} />
          </div>
        </div>
      ),
    },
    {
      id: 'history',
      label: 'Intelligence History',
      icon: HistoryIcon,
      badge: history.length > 0 ? history.length : undefined,
      badgeClassName: 'bg-muted text-muted-foreground font-mono',
      content: (
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-2xl p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center gap-2">
                <HistoryIcon className="w-4 h-4 text-primary" />
                <h3 className="font-bold text-sm text-foreground">
                  AI Intelligence Archive ({history.length})
                </h3>
              </div>
              <span className="text-xs text-muted-foreground">Symbol: {symbol}</span>
            </div>

            {history.length === 0 ? (
              <p className="text-xs text-muted-foreground py-6 text-center">
                No past AI reports logged yet for {symbol}. Run an analysis to start building history.
              </p>
            ) : (
              <div className="space-y-2.5">
                {history.map((h) => (
                  <div
                    key={h.id}
                    className="bg-secondary/40 hover:bg-secondary/60 transition-colors p-3.5 rounded-xl border border-border/70 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-semibold text-muted-foreground text-[11px]">
                          {new Date(h.timestamp).toLocaleString('en-IN', {
                            dateStyle: 'short',
                            timeStyle: 'medium',
                          })}
                        </span>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md font-bold uppercase ${
                            h.market_bias === 'BULLISH'
                              ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                              : h.market_bias === 'BEARISH'
                              ? 'bg-red-500/15 text-red-600 dark:text-red-400'
                              : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {h.market_bias} ({h.confidence}%)
                        </span>
                      </div>
                      <p className="text-foreground text-xs leading-relaxed">{h.executive_summary}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ),
    },
  ], [bias, insight, researchError, researchLoading, symbol, selectedProvider, fetchResearch, history]);

  return (
    <div className="space-y-4 max-w-[1600px] mx-auto pb-10">
      {/* ─────────────────────────────────────────────────────────────────
          UNIFIED TOP COMMAND BAR
          ───────────────────────────────────────────────────────────────── */}
      <div className="bg-card/90 backdrop-blur-md border border-border rounded-2xl p-3 shadow-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Left: Symbol Chips + Live Spot Quote & Telemetry */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Symbol Chips */}
            <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl border border-border/50">
              {SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  onClick={() => setSymbol(sym)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                    symbol === sym
                      ? 'bg-primary text-primary-foreground shadow-xs'
                      : 'text-muted-foreground hover:text-foreground hover:bg-background/60'
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>

            {/* Live Spot Quote */}
            {spot !== undefined && spot !== null && (
              <div className="flex items-center gap-2 pl-2 border-l border-border/60">
                <span className="text-xs text-muted-foreground font-semibold">{symbol}</span>
                <span className="text-sm font-bold font-mono text-foreground tabular-nums">
                  ₹{spot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            )}

            {/* Regime Badge */}
            {regime && regime !== 'UNKNOWN' && (
              <Badge variant="outline" className="text-[10px] font-semibold tracking-wider uppercase h-5 px-2">
                Regime: {regime}
              </Badge>
            )}

            {/* AI Live Direction Pill */}
            {bias && (
              <Badge
                variant={bias === 'LONG' ? 'success' : bias === 'SHORT' ? 'destructive' : 'secondary'}
                className="text-[11px] font-bold px-2.5 py-0.5 h-5 flex items-center gap-1"
              >
                {bias === 'LONG' ? (
                  <TrendingUp className="w-3 h-3" />
                ) : bias === 'SHORT' ? (
                  <TrendingDown className="w-3 h-3" />
                ) : null}
                <span>AI: {bias}</span>
              </Badge>
            )}

            {/* Validation Gate */}
            {valStatus && (
              <div className="hidden sm:flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-md border border-border/60 bg-muted/40 font-medium">
                {valStatus === 'ACCEPT' || valStatus === 'PASS' ? (
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                ) : (
                  <ShieldAlert className="w-3.5 h-3.5 text-red-500 shrink-0" />
                )}
                <span className="text-muted-foreground">Validation:</span>
                <span
                  className={
                    valStatus === 'ACCEPT' || valStatus === 'PASS'
                      ? 'text-emerald-500 font-semibold'
                      : 'text-red-500 font-semibold'
                  }
                >
                  {valStatus}
                </span>
              </div>
            )}

            {/* TTL Timer */}
            {deepInsightState.signalState && (
              <div className="hidden md:flex items-center gap-1 text-[11px] text-muted-foreground font-mono">
                <Clock className="w-3 h-3 text-muted-foreground" />
                <span>TTL: {ttlRemaining}s</span>
              </div>
            )}
          </div>

          {/* Right: View Toggle, Model Selector, Engine & Refresh */}
          <div className="flex items-center gap-2.5 ml-auto">
            {/* Desktop Side-by-Side Split View Toggle */}
            <button
              onClick={() => setSplitView((v) => !v)}
              title={splitView ? 'Switch to Tabbed View' : 'Switch to Side-by-Side View'}
              className={`hidden xl:flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer transition-all ${
                splitView
                  ? 'bg-primary/10 border-primary/40 text-primary'
                  : 'bg-secondary/70 border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              <Columns className="w-3.5 h-3.5" />
              <span>{splitView ? 'Tabbed' : 'Split View'}</span>
            </button>

            {/* Model Selector Toggle (when OpenRouter is active) */}
            {selectedProvider === 'openrouter' && (
              <button
                onClick={() => setShowModelSelector((v) => !v)}
                title="Select AI Model"
                className={`flex items-center gap-1 px-2.5 py-1.5 rounded-xl border text-xs font-semibold cursor-pointer transition-all ${
                  showModelSelector
                    ? 'bg-primary/10 border-primary/40 text-primary'
                    : 'bg-secondary/70 border-border text-muted-foreground hover:text-foreground'
                }`}
              >
                <SlidersHorizontal className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Model</span>
                {showModelSelector ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}

            {/* Provider Dropdown */}
            <select
              value={selectedProvider}
              onChange={(e) => {
                const newProv = e.target.value;
                setSelectedProvider(newProv);
                try {
                  const s = getStoredSettings();
                  s.ai.provider = newProv as any;
                  localStorage.setItem('droid_app_settings_v1', JSON.stringify(s));
                } catch {}
              }}
              className="bg-secondary/80 text-xs px-2.5 py-1.5 rounded-xl border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
            >
              <option value="openrouter">Auto AI (OpenRouter)</option>
              <option value="gemini">Google Gemini</option>
              <option value="openai">OpenAI</option>
              <option value="ollama">On-device (Ollama)</option>
            </select>

            {/* Refresh Action */}
            <button
              onClick={handleRefreshAll}
              disabled={isRefreshing}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
          </div>
        </div>

        {/* Expandable OpenRouter Model Selector Drawer */}
        {selectedProvider === 'openrouter' && showModelSelector && (
          <div className="pt-2 border-t border-border/70 animate-in fade-in duration-200">
            <OpenRouterModelSelector
              settings={
                {
                  ...getStoredSettings().ai,
                  openRouterSelectedModel: selectedModel,
                  openRouterAllowPaid: allowPaid,
                  openRouterFreeOnly: !allowPaid,
                } as any
              }
              onChange={(upd: any) => {
                if (upd.openRouterSelectedModel !== undefined) handleModelChange(upd.openRouterSelectedModel);
                if (upd.openRouterModel !== undefined) handleModelChange(upd.openRouterModel);
                if (upd.openRouterAllowPaid !== undefined) setAllowPaid(upd.openRouterAllowPaid);
                if (upd.openRouterFreeOnly !== undefined) setAllowPaid(!upd.openRouterFreeOnly);
              }}
            />
          </div>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────────────
          MAIN CONTENT: SPLIT VIEW OR TABBED VIEW
          ───────────────────────────────────────────────────────────────── */}
      {splitView ? (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
          {/* Left Column (7 cols): Live Signal & Bento */}
          <div className="xl:col-span-7 flex flex-col gap-3 min-h-[640px]">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <Radio className="w-4 h-4 text-primary" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-foreground">
                  Live Signal & Market Structure
                </h2>
              </div>
              <Badge variant="outline" className="text-[10px] uppercase font-mono">
                Real-time
              </Badge>
            </div>
            <div className="flex-1 min-h-0">
              <DeepInsightPanel />
            </div>
          </div>

          {/* Right Column (5 cols): AI Research, Quant Pillars & Playbook */}
          <div className="xl:col-span-5 flex flex-col gap-4">
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <Brain className="w-4 h-4 text-primary" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-foreground">
                  AI Deep Research & Playbook
                </h2>
              </div>
              <Badge variant="outline" className="text-[10px] uppercase font-mono">
                Synthesized
              </Badge>
            </div>

            {researchError ? (
              <div className="p-4 bg-card border border-destructive/20 rounded-xl text-destructive text-xs space-y-2">
                <p className="font-semibold">{researchError}</p>
                <button
                  onClick={() => fetchResearch(symbol, selectedProvider)}
                  className="px-3 py-1 rounded-lg bg-primary text-primary-foreground text-xs font-bold cursor-pointer"
                >
                  Retry
                </button>
              </div>
            ) : researchLoading && !insight ? (
              <div className="p-8 bg-card border border-border rounded-xl text-center text-muted-foreground animate-pulse space-y-2">
                <Brain className="w-8 h-8 text-primary mx-auto animate-bounce" />
                <p className="text-xs font-semibold">Generating research for {symbol}…</p>
              </div>
            ) : insight ? (
              <div className="space-y-4">
                <AIExecutiveHero insight={insight} symbol={symbol} />
                <AIQuantPillars insight={insight} />
                <AITradePlaybook insight={insight} />
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <PageTabs
          tabs={tabs}
          defaultTab="signal"
          syncWithUrl={true}
          queryParam="tab"
        />
      )}
    </div>
  );
}

export default function AICommandCenterPage() {
  return (
    <DeepInsightProvider>
      <AICommandCenterContent />
    </DeepInsightProvider>
  );
}
