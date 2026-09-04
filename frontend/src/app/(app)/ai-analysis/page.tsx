'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { AIInsightResponse, AIHistoryItem } from '@/lib/types';
import { AIExecutiveHero } from '@/components/ai/AIExecutiveHero';
import { AIQuantPillars } from '@/components/ai/AIQuantPillars';
import { AITradePlaybook } from '@/components/ai/AITradePlaybook';
import { JargonBuster } from '@/components/ai/JargonBuster';
import { AIOptionsArchitect } from '@/components/ai/AIOptionsArchitect';
import { AITradeValidator } from '@/components/ai/AITradeValidator';
import { OpenRouterModelSelector } from '@/components/settings/OpenRouterModelSelector';
import { getStoredSettings } from '@/lib/settings';
import {
  Brain,
  RefreshCw,
  History,
  Layers,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
} from 'lucide-react';

export default function AIAnalysisPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedProvider, setSelectedProvider] = useState<string>('openrouter');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [allowPaid, setAllowPaid] = useState<boolean>(false);
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Expandable Utility Tools
  const [showOptionsArchitect, setShowOptionsArchitect] = useState<boolean>(false);
  const [showTradeValidator, setShowTradeValidator] = useState<boolean>(false);

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'SENSEX'];

  // Hydrate settings
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

  const buildUnifiedPayload = (symbol: string, providerOverride?: string) => {
    try {
      const s = getStoredSettings();
      const a = s.ai as any;
      let effectiveProvider = providerOverride || selectedProvider || 'openrouter';
      if (effectiveProvider === 'mock_ai') effectiveProvider = 'openrouter';

      const base: Record<string, unknown> = {
        symbol,
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
      return { symbol, provider: providerOverride || selectedProvider || 'openrouter', model: selectedModel || 'auto', analysis_type: 'multi_timeframe', allow_paid: allowPaid };
    }
  };

  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = buildUnifiedPayload(selectedSymbol, selectedProvider);
      const res: any = await api.generateAIAnalysisWithModel(payload as any);
      setInsight(res.data);
      const histRes = await api.getAIHistory(selectedSymbol);
      setHistory(histRes.data);
    } catch (err: any) {
      setError(err instanceof Error ? err.message : 'Failed to generate market intelligence');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalysis();
  }, [selectedSymbol, selectedProvider]);

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

  return (
    <div className="space-y-5 max-w-7xl mx-auto pb-8">
      {/* Top Header Bar */}
      <div className="bg-card border border-border rounded-2xl p-4 shadow-xs flex flex-wrap items-center justify-between gap-4">
        {/* Symbol Selector Chips */}
        <div className="flex items-center gap-2">
          {symbols.map((sym) => (
            <button
              key={sym}
              onClick={() => setSelectedSymbol(sym)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                selectedSymbol === sym
                  ? 'bg-primary text-primary-foreground shadow-xs'
                  : 'bg-secondary/70 hover:bg-secondary text-muted-foreground hover:text-foreground'
              }`}
            >
              {sym}
            </button>
          ))}
        </div>

        {/* Engine Selector & Refresh Action */}
        <div className="flex items-center gap-3">
          <select
            value={selectedProvider}
            onChange={(e) => {
              setSelectedProvider(e.target.value);
              try {
                const s = getStoredSettings();
                s.ai.provider = e.target.value as any;
                localStorage.setItem('droid_app_settings_v1', JSON.stringify(s));
              } catch {}
            }}
            className="bg-secondary/80 text-xs px-3 py-2 rounded-xl border border-border text-foreground font-semibold focus:outline-hidden cursor-pointer"
          >
            <option value="openrouter">Auto AI (recommended)</option>
            <option value="gemini">Google Gemini</option>
            <option value="openai">OpenAI</option>
            <option value="ollama">On-device (Ollama)</option>
            <option value="mock_ai">Offline mode</option>
          </select>

          <button
            onClick={fetchAnalysis}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-bold transition-all cursor-pointer shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Analysis</span>
          </button>
        </div>
      </div>

      {/* Model Selector (When OpenRouter is active) */}
      {selectedProvider === 'openrouter' && (
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
      )}

      {/* Error state */}
      {error ? (
        <div className="p-6 text-center bg-card border border-destructive/20 rounded-2xl text-destructive space-y-2 shadow-xs">
          <p className="font-semibold text-sm">Could not read the market right now</p>
          <p className="text-xs opacity-80">{error}</p>
          <button
            onClick={fetchAnalysis}
            className="mt-1 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-xs font-bold cursor-pointer"
          >
            Try again
          </button>
        </div>
      ) : loading && !insight ? (
        <div className="bg-card border border-border rounded-2xl p-14 text-center text-muted-foreground animate-pulse space-y-3">
          <Brain className="w-10 h-10 text-primary mx-auto animate-bounce" />
          <p className="font-bold text-sm text-foreground">Reading the market for {selectedSymbol}…</p>
          <p className="text-xs text-muted-foreground">
            Checking price movement, big trader positions, and market mood. Takes about 10–20 seconds.
          </p>
        </div>
      ) : insight ? (
        <div className="space-y-5 animate-in fade-in duration-300">
          {/* 1. Market direction + simple explanation */}
          <AIExecutiveHero insight={insight} symbol={selectedSymbol} />

          {/* 2. Confused by a word? Plain-language glossary */}
          <JargonBuster />

          {/* 3. Three simple questions answered */}
          <AIQuantPillars insight={insight} />

          {/* 4. What to do + when to exit */}
          <AITradePlaybook insight={insight} />

          {/* 4. Specialized Utility Tools (Collapsible for zero clutter) */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            {/* Options Strategy Structurer Card */}
            <div className="bg-card border border-border rounded-2xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-primary/10 rounded-lg text-primary">
                    <Layers className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-foreground">Options Strategy Helper</h3>
                    <p className="text-[11px] text-muted-foreground">Build a safe, limited-loss option plan</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowOptionsArchitect((prev) => !prev)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-secondary text-xs font-semibold text-foreground hover:bg-secondary/80 border border-border cursor-pointer transition-colors"
                >
                  {showOptionsArchitect ? 'Hide' : 'Open Tool'}
                  {showOptionsArchitect ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>

              {showOptionsArchitect && (
                <div className="pt-2 border-t border-border/60">
                  <AIOptionsArchitect selectedSymbol={selectedSymbol} />
                </div>
              )}
            </div>

            {/* Trade Thesis Auditor Card */}
            <div className="bg-card border border-border rounded-2xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-emerald-500/10 rounded-lg text-emerald-500">
                    <ShieldCheck className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-xs font-bold text-foreground">Check My Trade Idea</h3>
                    <p className="text-[11px] text-muted-foreground">Let AI double-check your plan for hidden risks</p>
                  </div>
                </div>
                <button
                  onClick={() => setShowTradeValidator((prev) => !prev)}
                  className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-secondary text-xs font-semibold text-foreground hover:bg-secondary/80 border border-border cursor-pointer transition-colors"
                >
                  {showTradeValidator ? 'Hide' : 'Open Tool'}
                  {showTradeValidator ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </button>
              </div>

              {showTradeValidator && (
                <div className="pt-2 border-t border-border/60">
                  <AITradeValidator selectedSymbol={selectedSymbol} />
                </div>
              )}
            </div>
          </div>

          {/* 6. Past reports */}
          {history.length > 1 && (
            <div className="bg-card border border-border rounded-2xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                <h3 className="font-bold text-xs text-foreground uppercase tracking-wider">
                  What AI said earlier ({history.length})
                </h3>
              </div>
              <div className="space-y-2">
                {history.slice(1, 4).map((h) => (
                  <div
                    key={h.id}
                    className="bg-secondary/30 p-2.5 rounded-xl border border-border flex items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-0.5">
                      <span className="font-mono font-semibold text-muted-foreground text-[10px]">
                        {new Date(h.timestamp).toLocaleTimeString('en-IN')}
                      </span>
                      <p className="text-foreground text-xs line-clamp-1">{h.executive_summary}</p>
                    </div>
                    <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full font-bold bg-secondary text-primary border border-border">
                      {h.market_bias === 'BULLISH' ? 'Up ↑' : h.market_bias === 'BEARISH' ? 'Down ↓' : h.market_bias === 'VOLATILE' ? 'Risky ⚡' : 'Sideways →'} ({h.confidence}%)
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
