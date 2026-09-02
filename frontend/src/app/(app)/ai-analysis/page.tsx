'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { AIInsightResponse, AIHistoryItem } from '@/lib/types';
import { AIBiasBanner } from '@/components/ai/AIBiasBanner';
import { AIInsightSections } from '@/components/ai/AIInsightSections';
import { AIRiskDisclaimer } from '@/components/ai/AIRiskDisclaimer';
import { AIOptionsArchitect } from '@/components/ai/AIOptionsArchitect';
import { AITradeValidator } from '@/components/ai/AITradeValidator';
import { OpenRouterModelSelector } from '@/components/settings/OpenRouterModelSelector';
import { getStoredSettings } from '@/lib/settings';
import {
  History,
  Brain,
  Clock,
  TrendingUp,
  AlertTriangle,
  Activity,
  Layers,
  ShieldCheck,
  Bot,
  FileText,
  Send,
  Square,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Wrench,
  RotateCcw,
} from 'lucide-react';

export default function AIAnalysisPage() {
  const [activeTab, setActiveTab] = useState<'dossier' | 'options' | 'validator' | 'copilot'>('dossier');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('NIFTY');
  const [selectedProvider, setSelectedProvider] = useState<string>('openrouter');
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [allowPaid, setAllowPaid] = useState<boolean>(false);
  const [insight, setInsight] = useState<AIInsightResponse | null>(null);
  const [history, setHistory] = useState<AIHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [analysisMeta, setAnalysisMeta] = useState<{ model_used?: string; latency_ms?: number } | null>(null);
  const [triggerMode, setTriggerMode] = useState<string>('manual');
  const [autoInterval, setAutoInterval] = useState<number>(60);

  // Copilot Console Tab State
  const [copilotMessages, setCopilotMessages] = useState<any[]>([
    {
      role: 'assistant',
      content: `Welcome to the DROID AI Interactive Console. I am calibrated for Indian F&O quantitative derivatives analysis for **${selectedSymbol}**. Ask any question or request a scenario audit.`,
    },
  ]);
  const [copilotInput, setCopilotInput] = useState('');
  const [copilotStreaming, setCopilotStreaming] = useState(false);
  const [copilotStreamingReasoning, setCopilotStreamingReasoning] = useState('');
  const [copilotStreamingContent, setCopilotStreamingContent] = useState('');
  const [copilotActiveTool, setCopilotActiveTool] = useState<string | null>(null);

  // hydrate from stored settings
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

  useEffect(() => {
    let isMounted = true;
    const fetchAnalysis = async () => {
      try {
        const payload = buildUnifiedPayload(selectedSymbol, selectedProvider);
        const res: any = await api.generateAIAnalysisWithModel(payload as any);
        const histRes = await api.getAIHistory(selectedSymbol);
        if (isMounted) {
          setInsight(res.data);
          setAnalysisMeta({ model_used: res.model_used, latency_ms: res.latency_ms });
          setHistory(histRes.data);
          setError(null);
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
        const payload = buildUnifiedPayload(selectedSymbol, selectedProvider);
        const res: any = await api.generateAIAnalysisWithModel(payload as any);
        setInsight(res.data);
        setAnalysisMeta({ model_used: res.model_used, latency_ms: res.latency_ms });
        setError(null);
        const h = await api.getAIHistory(selectedSymbol);
        setHistory(h.data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to generate AI analysis');
      } finally {
        setLoading(false);
      }
    };
    doGenerate();
  };

  const handleSendCopilot = async (overrideText?: string) => {
    const text = (overrideText || copilotInput).trim();
    if (!text || copilotStreaming) return;

    const userMsg = { role: 'user', content: text };
    const newMessages = [...copilotMessages, userMsg];
    setCopilotMessages(newMessages);
    setCopilotInput('');
    setCopilotStreaming(true);
    setCopilotStreamingContent('');
    setCopilotStreamingReasoning('');
    setCopilotActiveTool(null);

    const settings = getStoredSettings();
    let currentReasoning = '';
    let currentContent = '';

    await api.streamAIChat(
      {
        messages: newMessages,
        symbol: selectedSymbol,
        provider: selectedProvider,
        model: selectedModel,
        context_page: 'AI Workspace Console',
        enable_tools: true,
        openrouter_api_key: settings.ai.openRouterApiKey || undefined,
        gemini_api_key: settings.ai.geminiApiKey || undefined,
      },
      (chunk) => {
        if (chunk.type === 'reasoning' && chunk.reasoning_delta) {
          currentReasoning += chunk.reasoning_delta;
          setCopilotStreamingReasoning(currentReasoning);
        } else if (chunk.type === 'content' && chunk.delta) {
          currentContent += chunk.delta;
          setCopilotStreamingContent(currentContent);
        } else if (chunk.type === 'tool_call' && chunk.tool_call) {
          setCopilotActiveTool(chunk.tool_call.function?.name || 'quant_engine');
        } else if (chunk.type === 'tool_result') {
          setCopilotActiveTool(null);
        }
      },
      (err) => {
        setCopilotStreaming(false);
        setCopilotMessages((prev) => [
          ...prev,
          { role: 'assistant', content: currentContent ? `${currentContent}\n\n⚠️ *${err}*` : `⚠️ **Error:** ${err}` },
        ]);
        setCopilotStreamingContent('');
        setCopilotStreamingReasoning('');
      },
      () => {
        setCopilotStreaming(false);
        if (currentContent || currentReasoning) {
          setCopilotMessages((prev) => [
            ...prev,
            { role: 'assistant', content: currentContent || 'Completed.', reasoning_content: currentReasoning || null },
          ]);
        }
        setCopilotStreamingContent('');
        setCopilotStreamingReasoning('');
      }
    );
  };

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
    <div className="space-y-4">
      {/* Top Workspace Tab Navigation */}
      <div className="flex items-center justify-between border-b border-border pb-2 overflow-x-auto no-scrollbar">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('dossier')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'dossier'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            <FileText className="w-4 h-4" />
            Market Intelligence Dossier
          </button>

          <button
            onClick={() => setActiveTab('options')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'options'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            <Layers className="w-4 h-4" />
            Options Strategy Architect
          </button>

          <button
            onClick={() => setActiveTab('validator')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'validator'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            <ShieldCheck className="w-4 h-4" />
            Trade Thesis Auditor
          </button>

          <button
            onClick={() => setActiveTab('copilot')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'copilot'
                ? 'bg-primary text-primary-foreground shadow-xs'
                : 'bg-secondary/60 text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            <Bot className="w-4 h-4" />
            Interactive Copilot Console
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="text-muted-foreground">Active Ticker:</span>
          <select
            value={selectedSymbol}
            onChange={(e) => setSelectedSymbol(e.target.value)}
            className="bg-secondary/80 border border-border rounded-lg px-2.5 py-1.5 font-bold font-mono text-xs cursor-pointer focus:outline-hidden"
          >
            <option value="NIFTY">NIFTY 50</option>
            <option value="BANKNIFTY">BANK NIFTY</option>
            <option value="FINNIFTY">FIN NIFTY</option>
            <option value="MIDCPNIFTY">MIDCAP NIFTY</option>
            <option value="SENSEX">SENSEX</option>
          </select>
        </div>
      </div>

      {/* TAB 1: Market Intelligence Dossier */}
      {activeTab === 'dossier' && (
        <div className="space-y-4">
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
            </div>
          )}

          {error ? (
            <div className="p-6 text-center bg-card border border-destructive/20 rounded-xl text-destructive space-y-2">
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
              </div>

              <AIInsightSections insight={insight} />
              <AIRiskDisclaimer riskNotes={insight.risk_management_notes} disclaimer={insight.disclaimer} />

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
      )}

      {/* TAB 2: Options Strategy Architect */}
      {activeTab === 'options' && (
        <AIOptionsArchitect selectedSymbol={selectedSymbol} />
      )}

      {/* TAB 3: Trade Setup Auditor */}
      {activeTab === 'validator' && (
        <AITradeValidator selectedSymbol={selectedSymbol} />
      )}

      {/* TAB 4: Interactive Copilot Console */}
      {activeTab === 'copilot' && (
        <div className="bg-card border border-border rounded-xl shadow-xs flex flex-col h-[700px] overflow-hidden">
          <div className="p-4 border-b border-border bg-secondary/30 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-primary" />
              <div>
                <h3 className="text-sm font-bold text-foreground">Interactive Copilot Console</h3>
                <p className="text-[11px] text-muted-foreground">Direct quantitative reasoning loop with live tool execution</p>
              </div>
            </div>
            <button
              onClick={() => setCopilotMessages([{ role: 'assistant', content: `Chat reset for ${selectedSymbol}.` }])}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary text-xs font-semibold rounded-lg hover:bg-secondary/80 border border-border cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Reset Console
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
            {copilotMessages.map((m, idx) => (
              <div key={idx} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 space-y-2 ${
                    m.role === 'user'
                      ? 'bg-primary text-primary-foreground font-medium rounded-br-xs'
                      : 'bg-secondary/40 border border-border text-foreground rounded-bl-xs'
                  }`}
                >
                  {m.reasoning_content && (
                    <div className="p-2 bg-secondary/60 rounded border border-border font-mono text-[10.5px] text-muted-foreground whitespace-pre-wrap">
                      <div className="font-bold text-primary mb-1 flex items-center gap-1">
                        <Brain className="w-3.5 h-3.5" /> Reasoning Chain
                      </div>
                      {m.reasoning_content}
                    </div>
                  )}
                  <div className="whitespace-pre-wrap leading-relaxed">{m.content}</div>
                </div>
              </div>
            ))}

            {copilotStreaming && (
              <div className="flex gap-3 justify-start">
                <div className="max-w-[80%] rounded-2xl px-4 py-3 space-y-2 bg-secondary/40 border border-primary/30 text-foreground rounded-bl-xs">
                  {copilotActiveTool && (
                    <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded bg-amber-500/10 text-amber-600 text-[11px] font-mono animate-pulse">
                      <Wrench className="w-3.5 h-3.5 animate-spin" /> Calling: {copilotActiveTool}...
                    </div>
                  )}
                  {copilotStreamingReasoning && (
                    <div className="p-2 bg-secondary/60 rounded border border-border font-mono text-[10.5px] text-muted-foreground whitespace-pre-wrap">
                      <div className="font-bold text-primary mb-1 flex items-center gap-1">
                        <Brain className="w-3.5 h-3.5 animate-bounce" /> Reasoning...
                      </div>
                      {copilotStreamingReasoning}
                    </div>
                  )}
                  <div className="whitespace-pre-wrap leading-relaxed">
                    {copilotStreamingContent}
                    <span className="inline-block w-2 h-3.5 ml-1 bg-primary animate-pulse" />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="p-3 border-t border-border bg-card">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={copilotInput}
                onChange={(e) => setCopilotInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSendCopilot();
                }}
                placeholder={`Query ${selectedSymbol} derivatives, Greeks, or scenarios...`}
                className="flex-1 bg-secondary/50 border border-border rounded-xl px-4 py-2.5 text-xs focus:outline-hidden focus:ring-1 focus:ring-primary"
                disabled={copilotStreaming}
              />
              <button
                onClick={() => handleSendCopilot()}
                disabled={copilotStreaming || !copilotInput.trim()}
                className="px-4 py-2.5 bg-primary text-primary-foreground font-semibold rounded-xl text-xs disabled:opacity-50 cursor-pointer flex items-center gap-1.5"
              >
                <Send className="w-4 h-4" />
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
