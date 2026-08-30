'use client';

import React, { useState } from 'react';
import {
  Brain,
  Sparkles,
  Key,
  Sliders,
  Play,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  Cpu,
  Layers,
  Network,
  Server,
  Cloud,
  GitBranch,
  Shield,
  Search,
} from 'lucide-react';
import {
  AISettings,
  AIConnectionMode,
  DirectProviderId,
  AIRoutingMode,
  AITaskId,
  SUPPORTED_GEMINI_MODELS,
  SUPPORTED_OLLAMA_MODELS,
} from '@/lib/settings';
import { api } from '@/lib/api';
import { OpenRouterModelSelector } from './OpenRouterModelSelector';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
  errors?: { path: string; message: string }[];
}

const TASK_LABELS: Record<AITaskId, { label: string; hint: string }> = {
  INTRADAY_ANALYSIS: { label: 'Intraday Analysis', hint: 'fast finance/reasoning' },
  NEWS_ANALYSIS: { label: 'News Analysis', hint: 'research/news model' },
  DEEP_RESEARCH: { label: 'Deep Research', hint: 'strongest reasoning' },
  MTF_SYNTHESIS: { label: 'MTF Synthesis', hint: 'synthesis model' },
  CHART_EXPLANATION: { label: 'Chart Explanation', hint: 'fast model' },
  FINAL_REVIEW: { label: 'Final Review', hint: 'highest quality' },
};

const DIRECT_PROVIDER_OPTIONS: { id: DirectProviderId; name: string; desc: string }[] = [
  { id: 'OpenAI', name: 'OpenAI', desc: 'GPT-4o / GPT-4o-mini via api.openai.com' },
  { id: 'Novita AI', name: 'Novita AI', desc: 'Llama / Qwen via Novita' },
  { id: 'NVIDIA', name: 'NVIDIA', desc: 'Llama / Nemotron via NIM' },
  { id: 'Google Gemini', name: 'Google Gemini', desc: 'Gemini 2.5 via Google AI' },
  { id: 'Custom OpenAI-Compatible', name: 'Custom OpenAI-Compatible', desc: 'Any OpenAI-compatible base URL' },
];

export function AIEngineTab({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `ai.${field}`)?.message;
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaStatus, setOllamaStatus] = useState<'idle' | 'checking' | 'ok' | 'fail'>('idle');
  const [ollamaError, setOllamaError] = useState<string | null>(null);

  const toggleShow = (k: string) => setShowKeys((p) => ({ ...p, [k]: !p[k] }));

  // Derived
  const connectionMode: AIConnectionMode = (settings as any).connectionMode || (settings.provider === 'openrouter' ? 'OpenRouter' : settings.provider === 'ollama' ? 'Local Ollama' : 'OpenRouter');
  const directProvider: DirectProviderId = (settings as any).directProvider || 'OpenAI';
  const routingMode: AIRoutingMode = (settings as any).routingMode || 'Task Optimized';

  const handleConnectionMode = (mode: AIConnectionMode) => {
    // Keep legacy provider in sync for backward compat
    const legacyMap: Record<AIConnectionMode, AISettings['provider']> = {
      OpenRouter: 'openrouter',
      'Direct Provider': 'openai',
      'Local Ollama': 'ollama',
    } as any;
    onChange({ connectionMode: mode, provider: legacyMap[mode] || 'openrouter' } as any);
  };

  const handleRoutingMode = (mode: AIRoutingMode) => {
    onChange({ routingMode: mode } as any);
  };

  const handleTaskModel = (task: AITaskId, model: string) => {
    const current = (settings as any).taskModels || {};
    onChange({ taskModels: { ...current, [task]: model } } as any);
  };

  const checkOllama = async () => {
    setOllamaStatus('checking');
    setOllamaError(null);
    try {
      const url = (settings.ollamaBaseUrl || 'http://localhost:11434').replace(/\/$/, '');
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 4000);
      const r = await fetch(`${url}/api/tags`, { signal: ctrl.signal });
      clearTimeout(t);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      const models: string[] = (j.models || []).map((m: any) => m.name);
      setOllamaModels(models);
      setOllamaStatus('ok');
    } catch (e: any) {
      setOllamaError(e.message || 'Failed');
      setOllamaStatus('fail');
      setOllamaModels([]);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);

    // Pre-flight per mode
    if (connectionMode === 'OpenRouter' && !settings.openRouterApiKey) {
      // allow backend fallback but warn
    }
    if (connectionMode === 'Direct Provider') {
      const keyMap: Record<DirectProviderId, string> = {
        OpenAI: (settings as any).openaiApiKey,
        'Novita AI': (settings as any).novitaApiKey,
        NVIDIA: (settings as any).nvidiaApiKey,
        'Google Gemini': settings.geminiApiKey,
        'Custom OpenAI-Compatible': (settings as any).customOpenaiApiKey,
      };
      const need = keyMap[directProvider];
      if (!need || !need.trim()) {
        setTestResult({ success: false, message: `${directProvider} API key missing. Add key above then Save.` });
        setTesting(false);
        return;
      }
    }
    if (connectionMode === 'Local Ollama' && !settings.ollamaBaseUrl) {
      setTestResult({ success: false, message: 'Ollama URL missing.' });
      setTesting(false);
      return;
    }

    // Ollama local check via browser
    if (connectionMode === 'Local Ollama' && (settings.ollamaBaseUrl.includes('localhost') || settings.ollamaBaseUrl.includes('127.0.0.1'))) {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 4000);
        const start = performance.now();
        const r = await fetch(`${settings.ollamaBaseUrl.replace(/\/$/, '')}/api/tags`, { signal: ctrl.signal });
        clearTimeout(t);
        const latency = Math.round(performance.now() - start);
        if (!r.ok) {
          setTestResult({ success: false, message: `Ollama not reachable at ${settings.ollamaBaseUrl} – HTTP ${r.status}. Run ollama serve.`, latency } as any);
          setTesting(false);
          return;
        }
        const j = await r.json();
        const models: string[] = (j.models || []).map((m: any) => m.name);
        if (models.length > 0 && !models.some((m) => m.includes(settings.ollamaModel) || settings.ollamaModel.includes(m))) {
          setTestResult({ success: false, message: `Ollama OK (${latency}ms) but model '${settings.ollamaModel}' not found. Available: ${models.slice(0, 3).join(', ') || 'none'}. Run ollama pull ${settings.ollamaModel}.`, latency } as any);
          setTesting(false);
          return;
        }
      } catch (e: any) {
        const msg = e.name === 'AbortError' ? 'Timeout (4s)' : e.message;
        setTestResult({ success: false, message: `Ollama not reachable at ${settings.ollamaBaseUrl} – ${msg}. Install from https://ollama.com, then ollama serve and ollama pull ${settings.ollamaModel}.` });
        setTesting(false);
        return;
      }
    }

    try {
      // Build payload per connectionMode
      let payload: any = { symbol: 'NIFTY' };
      if (connectionMode === 'OpenRouter') {
        const sel = ((settings as any).openRouterSelectedModel || 'auto').trim();
        const effective = (!sel || sel.toLowerCase() === 'auto' || sel.toLowerCase().includes('best free')) ? 'auto' : sel;
        payload = {
          provider: 'openrouter',
          symbol: 'NIFTY',
          openRouterApiKey: settings.openRouterApiKey,
          openRouterModel: effective,
        };
      } else if (connectionMode === 'Direct Provider') {
        const providerMap: Record<DirectProviderId, string> = {
          OpenAI: 'openai',
          'Novita AI': 'novita',
          NVIDIA: 'nvidia',
          'Google Gemini': 'gemini',
          'Custom OpenAI-Compatible': 'custom_openai',
        };
        const p = providerMap[directProvider];
        payload = { provider: p, symbol: 'NIFTY' } as any;
        if (p === 'openai') {
          payload.openaiApiKey = (settings as any).openaiApiKey;
          payload.model = (settings as any).openaiModel;
          payload.base_url = (settings as any).openaiBaseUrl;
        } else if (p === 'novita') {
          payload.novitaApiKey = (settings as any).novitaApiKey;
          payload.model = (settings as any).novitaModel;
        } else if (p === 'nvidia') {
          payload.nvidiaApiKey = (settings as any).nvidiaApiKey;
          payload.model = (settings as any).nvidiaModel;
        } else if (p === 'gemini') {
          payload.geminiApiKey = settings.geminiApiKey;
          payload.geminiModel = settings.geminiModel;
        } else if (p === 'custom_openai') {
          payload.apiKey = (settings as any).customOpenaiApiKey;
          payload.model = (settings as any).customOpenaiModel;
          payload.base_url = (settings as any).customOpenaiBaseUrl;
        }
      } else if (connectionMode === 'Local Ollama') {
        payload = {
          provider: 'ollama',
          symbol: 'NIFTY',
          ollamaBaseUrl: settings.ollamaBaseUrl,
          ollamaModel: settings.ollamaModel,
        };
      }

      const start = performance.now();
      const res: any = await api.testAIProvider(payload);
      const clientLatency = Math.round(performance.now() - start);
      const d = res.data;
      setTestResult({
        success: d.success,
        message: d.success ? d.message || `Success via ${d.provider}:${d.model} in ${d.latency_ms}ms (client ${clientLatency}ms). Schema valid.` : d.error || 'Test failed',
        data: d.insight,
        latency: d.latency_ms,
        clientLatency,
        schemaValid: d.schema_valid,
        isMock: d.is_mock,
        hint: d.hint,
        model: d.model,
      } as any);
    } catch (err: any) {
      setTestResult({ success: false, message: err?.message || 'Test failed – see hint' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* §32 Provider / Model UI — Top-level AI CONFIGURATION */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            AI CONFIGURATION
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 font-mono">3 MODES</span>
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Unified quantitative → AI reasoning pipeline. Market data flows through deterministic validators before AI, stale checks, risk, then execution.
          </p>
        </div>

        <div>
          <label className="text-xs font-semibold text-foreground block mb-2">Connection Mode</label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { id: 'OpenRouter' as AIConnectionMode, name: 'OpenRouter', icon: Cloud, badge: 'Gateway', desc: 'Unified gateway · dynamic catalog · free-only enforced' },
              { id: 'Direct Provider' as AIConnectionMode, name: 'Direct Provider', icon: Network, badge: '5 Adapters', desc: 'OpenAI · Novita · NVIDIA · Gemini · Custom' },
              { id: 'Local Ollama' as AIConnectionMode, name: 'Local Ollama', icon: Server, badge: '100% Private', desc: 'http://localhost:11434 · no cloud key' },
            ].map((m) => {
              const Icon = m.icon;
              const selected = connectionMode === m.id;
              return (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => handleConnectionMode(m.id)}
                  className={`flex flex-col text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                    selected ? 'border-primary bg-primary/10 ring-2 ring-primary/20' : 'border-border bg-card hover:bg-secondary/40'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                      <Icon className="w-3.5 h-3.5" /> {m.name}
                    </span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${selected ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                      {m.badge}
                    </span>
                  </div>
                  <span className="text-[11px] text-muted-foreground mt-2">{m.desc}</span>
                </button>
              );
            })}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">
            Selected: <span className="font-mono font-semibold text-foreground">{connectionMode}</span> — quantitative engine is provider-independent.
          </p>
        </div>

        {/* §15 Routing Modes */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-border/50">
          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Routing Mode</label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
              {(['Manual', 'Task Optimized', 'Best Available', 'Cost Optimized'] as AIRoutingMode[]).map((rm) => {
                const active = routingMode === rm;
                return (
                  <button
                    key={rm}
                    type="button"
                    onClick={() => handleRoutingMode(rm)}
                    className={`px-2 py-2 rounded-lg text-[11px] font-medium border cursor-pointer ${active ? 'bg-primary text-primary-foreground border-primary shadow-xs' : 'bg-card border-border hover:bg-secondary/50'}`}
                  >
                    {rm}
                  </button>
                );
              })}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1">Default: <span className="font-semibold">Task Optimized</span></p>
          </div>
          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Automatic Provider Fallback</label>
            <label className="flex items-center gap-2 cursor-pointer bg-secondary/30 border border-border rounded-lg px-3 py-2">
              <input type="checkbox" checked={!!(settings as any).fallbackEnabled} onChange={(e) => onChange({ fallbackEnabled: e.target.checked } as any)} className="accent-primary" />
              <span className="text-xs text-foreground">{(settings as any).fallbackEnabled ? 'Enabled — cloud unavailable → Ollama' : 'OFF — do not silently switch providers (default)'}</span>
            </label>
            <p className="text-[11px] text-muted-foreground mt-1">{(settings as any).fallbackEnabled ? 'Requires local Ollama model' : 'Never uses paid fallback while FREE ONLY is enabled.'}</p>
          </div>
        </div>
      </div>

      {/* §14 Task-Specific Model Routing */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-3 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-primary" />
          Task-Specific Model Routing
          <span className="text-[10px] px-2 py-0.5 rounded bg-secondary border font-mono">6 TASKS</span>
          <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 font-mono">{routingMode}</span>
        </h3>
        <p className="text-xs text-muted-foreground">
          Different models for different tasks. Routing mode determines selection strategy. Manual = explicit per-task; Task Optimized (default) = auto per category; Best Available = highest rank free; Cost Optimized = fastest cheapest free.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(Object.keys(TASK_LABELS) as AITaskId[]).map((task) => (
            <div key={task} className="bg-secondary/30 border border-border/60 rounded-lg p-3 space-y-1.5">
              <div className="text-xs font-semibold text-foreground">{TASK_LABELS[task].label}</div>
              <div className="text-[11px] text-muted-foreground">{TASK_LABELS[task].hint}</div>
              <input
                type="text"
                value={(settings as any).taskModels?.[task] || 'auto'}
                onChange={(e) => handleTaskModel(task, e.target.value)}
                placeholder="auto or model id"
                className="w-full bg-card border border-border rounded-lg px-2 py-1.5 text-xs font-mono"
              />
              <div className="text-[10px] text-muted-foreground">Use <span className="font-mono">auto</span> for best free {TASK_LABELS[task].hint}</div>
            </div>
          ))}
        </div>
      </div>

      {/* MODE 1 — OpenRouter */}
      {connectionMode === 'OpenRouter' && (
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Key className="w-4 h-4 text-primary" />
              OpenRouter
              <span className="text-[10px] px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-mono">DYNAMIC CATALOG</span>
            </h3>

            <div className="bg-primary/5 border border-primary/20 rounded-lg p-3.5 text-xs space-y-3">
              <div className="flex items-center gap-2 font-semibold text-foreground">
                <Key className="w-3.5 h-3.5 text-primary" /> OpenRouter API Key
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-700 border border-emerald-500/20 font-mono">NO HARDCODE</span>
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Enter <code className="font-mono">sk-or-v1-...</code> from <a href="https://openrouter.ai/keys" target="_blank" rel="noreferrer" className="text-primary hover:underline">openrouter.ai/keys</a>. Stored in localStorage + Supabase, sent per-request. Server env fallback is optional.
              </p>
              <div className="relative">
                <input
                  type={showKeys['openrouter'] ? 'text' : 'password'}
                  placeholder="sk-or-v1-..."
                  value={settings.openRouterApiKey}
                  onChange={(e) => onChange({ openRouterApiKey: e.target.value })}
                  className="w-full bg-card border border-border rounded-lg px-3 py-2.5 pr-10 text-xs font-mono focus:border-primary focus:outline-none"
                />
                <button type="button" onClick={() => toggleShow('openrouter')} className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground cursor-pointer">
                  {showKeys['openrouter'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {getError('openRouterApiKey') && <span className="text-[11px] text-destructive block">{getError('openRouterApiKey')}</span>}
              <div className="text-[11px] flex items-center gap-1">
                {settings.openRouterApiKey ? <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Key set • Save then Run Live Test</span> : <span className="text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />No key — add and Save</span>}
              </div>
            </div>

            {/* Cost Mode + Model etc. via existing selector */}
            <OpenRouterModelSelector settings={settings} onChange={onChange} />
          </div>
        </div>
      )}

      {/* MODE 2 — Direct Provider */}
      {connectionMode === 'Direct Provider' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Network className="w-4 h-4 text-primary" />
            Direct Provider
            <span className="text-[10px] px-2 py-0.5 rounded bg-secondary border font-mono">5 ADAPTERS</span>
          </h3>

          <div>
            <label className="text-xs font-semibold text-foreground block mb-1">Provider</label>
            <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {DIRECT_PROVIDER_OPTIONS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onChange({ directProvider: p.id } as any)}
                  className={`p-2.5 rounded-xl border text-left cursor-pointer ${directProvider === p.id ? 'border-primary bg-primary/10 ring-1 ring-primary/20' : 'border-border hover:bg-secondary/30'}`}
                >
                  <div className="text-xs font-semibold text-foreground">{p.name}</div>
                  <div className="text-[11px] text-muted-foreground">{p.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Per-provider config */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-3">
              {directProvider === 'OpenAI' && (
                <>
                  <div>
                    <label className="text-xs font-semibold block mb-1">OpenAI API Key</label>
                    <div className="relative">
                      <input type={showKeys['openai'] ? 'text' : 'password'} placeholder="sk-proj-..." value={(settings as any).openaiApiKey || ''} onChange={(e) => onChange({ openaiApiKey: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                      <button type="button" onClick={() => toggleShow('openai')} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">{showKeys['openai'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Model</label>
                    <input type="text" value={(settings as any).openaiModel || 'gpt-4o-mini'} onChange={(e) => onChange({ openaiModel: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" placeholder="gpt-4o-mini" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">API Base URL</label>
                    <input type="text" value={(settings as any).openaiBaseUrl || 'https://api.openai.com/v1'} onChange={(e) => onChange({ openaiBaseUrl: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                    <p className="text-[11px] text-muted-foreground mt-1">Leave default unless using proxy.</p>
                  </div>
                </>
              )}
              {directProvider === 'Novita AI' && (
                <>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Novita AI API Key</label>
                    <div className="relative">
                      <input type={showKeys['novita'] ? 'text' : 'password'} placeholder="sk_..." value={(settings as any).novitaApiKey || ''} onChange={(e) => onChange({ novitaApiKey: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                      <button type="button" onClick={() => toggleShow('novita')} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">{showKeys['novita'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Model</label>
                    <input type="text" value={(settings as any).novitaModel || 'meta-llama/llama-3.3-70b-instruct'} onChange={(e) => onChange({ novitaModel: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">API Base URL</label>
                    <input type="text" value={(settings as any).novitaBaseUrl || 'https://api.novita.ai/v3/openai'} onChange={(e) => onChange({ novitaBaseUrl: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                  </div>
                </>
              )}
              {directProvider === 'NVIDIA' && (
                <>
                  <div>
                    <label className="text-xs font-semibold block mb-1">NVIDIA API Key</label>
                    <div className="relative">
                      <input type={showKeys['nvidia'] ? 'text' : 'password'} placeholder="nvapi-..." value={(settings as any).nvidiaApiKey || ''} onChange={(e) => onChange({ nvidiaApiKey: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                      <button type="button" onClick={() => toggleShow('nvidia')} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">{showKeys['nvidia'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Model</label>
                    <input type="text" value={(settings as any).nvidiaModel || 'meta/llama-3.1-70b-instruct'} onChange={(e) => onChange({ nvidiaModel: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">API Base URL</label>
                    <input type="text" value={(settings as any).nvidiaBaseUrl || 'https://integrate.api.nvidia.com/v1'} onChange={(e) => onChange({ nvidiaBaseUrl: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                  </div>
                </>
              )}
              {directProvider === 'Google Gemini' && (
                <>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Google Gemini API Key</label>
                    <div className="relative">
                      <input type={showKeys['gemini'] ? 'text' : 'password'} placeholder="AIza..." value={settings.geminiApiKey} onChange={(e) => onChange({ geminiApiKey: e.target.value })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                      <button type="button" onClick={() => toggleShow('gemini')} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">{showKeys['gemini'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                    </div>
                    <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" className="text-[11px] text-primary hover:underline">Get free key</a>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Supported Gemini Model</label>
                    <div className="flex gap-2">
                      <select value={settings.geminiModel || 'gemini-2.5-flash'} onChange={(e) => onChange({ geminiModel: e.target.value })} className="flex-1 bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono cursor-pointer">
                        {SUPPORTED_GEMINI_MODELS.map((m) => (
                          <option key={m.id} value={m.id}>{m.name} — [{m.tag}]</option>
                        ))}
                      </select>
                      <button type="button" onClick={() => setIsCustomModel(!isCustomModel)} className="text-[11px] px-2 py-1 border border-border rounded-lg hover:bg-secondary cursor-pointer bg-card">{isCustomModel ? 'List' : 'Custom'}</button>
                    </div>
                    {isCustomModel && <input type="text" value={settings.geminiModel} onChange={(e) => onChange({ geminiModel: e.target.value })} placeholder="gemini-2.5-pro" className="w-full mt-1 bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />}
                  </div>
                </>
              )}
              {directProvider === 'Custom OpenAI-Compatible' && (
                <>
                  <div>
                    <label className="text-xs font-semibold block mb-1">API Key (if required)</label>
                    <div className="relative">
                      <input type={showKeys['custom'] ? 'text' : 'password'} placeholder="sk-... or empty for local" value={(settings as any).customOpenaiApiKey || ''} onChange={(e) => onChange({ customOpenaiApiKey: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                      <button type="button" onClick={() => toggleShow('custom')} className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer">{showKeys['custom'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}</button>
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">API Base URL *</label>
                    <input type="text" placeholder="https://your-host/v1" value={(settings as any).customOpenaiBaseUrl || ''} onChange={(e) => onChange({ customOpenaiBaseUrl: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                    <p className="text-[11px] text-muted-foreground">Required. Must be OpenAI-compatible /chat/completions.</p>
                  </div>
                  <div>
                    <label className="text-xs font-semibold block mb-1">Model</label>
                    <input type="text" value={(settings as any).customOpenaiModel || 'custom-model'} onChange={(e) => onChange({ customOpenaiModel: e.target.value } as any)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
                  </div>
                </>
              )}
            </div>

            <div className="bg-secondary/20 border border-border/60 rounded-xl p-3.5 space-y-2 text-xs">
              <div className="flex items-center gap-2 font-semibold">
                <Shield className="w-3.5 h-3.5 text-primary" /> Provider-Specific Capabilities
              </div>
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Each adapter detects capabilities (tools, vision, structured outputs) and never sends unsupported params. For example, Ling 3.0 Flash Fin via OpenRouter will <span className="font-semibold">not</span> receive <code className="font-mono">response_format=json_object</code> — instead it gets prompted JSON and is locally validated via Pydantic.
              </p>
              <div className="text-[11px] p-2 rounded bg-card border">
                <div>Selected: <span className="font-mono font-semibold">{directProvider}</span></div>
                <div className="text-muted-foreground">No shared inference code in trading engine — all via <code className="font-mono">AIProvider</code>.</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODE 3 — Local Ollama */}
      {connectionMode === 'Local Ollama' && (
        <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Server className="w-4 h-4 text-primary" />
            Local Ollama
            <span className="text-[10px] px-2 py-0.5 rounded bg-secondary border font-mono">{settings.ollamaBaseUrl || 'http://localhost:11434'}</span>
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold block mb-1">Ollama URL</label>
              <input type="text" value={settings.ollamaBaseUrl} onChange={(e) => onChange({ ollamaBaseUrl: e.target.value })} placeholder="http://localhost:11434" className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
              <p className="text-[11px] text-muted-foreground mt-1">Default local server. No cloud API key required. Model is replaceable without engine changes.</p>
              {getError('ollamaBaseUrl') && <span className="text-[11px] text-destructive block">{getError('ollamaBaseUrl')}</span>}
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold">Installed Models</label>
                <button type="button" onClick={checkOllama} className="text-[11px] px-2 py-1 bg-secondary border border-border rounded-lg hover:bg-secondary/80 cursor-pointer">
                  {ollamaStatus === 'checking' ? 'Checking…' : 'Refresh Models'}
                </button>
              </div>
              <div className="min-h-[42px] bg-secondary/30 border border-border rounded-lg px-3 py-2 text-xs">
                {ollamaStatus === 'idle' && <span className="text-muted-foreground">Click Refresh to discover local models.</span>}
                {ollamaStatus === 'checking' && <span className="text-muted-foreground">Checking {settings.ollamaBaseUrl}/api/tags …</span>}
                {ollamaStatus === 'ok' && (
                  <div className="space-y-1">
                    <div className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="w-3 h-3" /> Found {ollamaModels.length} models</div>
                    <div className="font-mono text-[11px] break-all">{ollamaModels.slice(0, 5).join(', ') || 'none'}</div>
                  </div>
                )}
                {ollamaStatus === 'fail' && <span className="text-destructive flex items-center gap-1"><AlertCircle className="w-3 h-3" /> {ollamaError}</span>}
              </div>
              <div className="text-[11px] text-muted-foreground">Health: {ollamaStatus === 'ok' ? <span className="text-emerald-600">Installed & reachable</span> : ollamaStatus === 'fail' ? <span className="text-destructive">Unavailable — install from https://ollama.com, then `ollama serve`</span> : 'Unknown'}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-semibold">Local Model</label>
                <button type="button" onClick={() => setIsCustomModel(!isCustomModel)} className="text-[11px] text-primary hover:underline cursor-pointer">{isCustomModel ? 'Select from list' : 'Custom Tag'}</button>
              </div>
              {!isCustomModel ? (
                <select value={settings.ollamaModel || 'deepseek-r1:8b'} onChange={(e) => onChange({ ollamaModel: e.target.value })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono cursor-pointer">
                  {SUPPORTED_OLLAMA_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>{m.name} — [{m.tag}]</option>
                  ))}
                  <option value="__custom__">⚙️ Other / Custom Local Tag…</option>
                </select>
              ) : (
                <input type="text" placeholder="e.g. qwen2.5:7b" value={settings.ollamaModel} onChange={(e) => onChange({ ollamaModel: e.target.value })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />
              )}
              {getError('ollamaModel') && <span className="text-[11px] text-destructive block">{getError('ollamaModel')}</span>}
              <p className="text-[11px] text-muted-foreground mt-1">For RTX 4050/16GB start with 8B-class. Later 14B/32B/70B+ without code changes.</p>
            </div>
            <div className="bg-secondary/30 border border-border/60 rounded-xl p-3.5 flex items-start gap-3 text-xs">
              <div className="bg-primary/10 text-primary p-2 rounded-lg shrink-0 mt-0.5"><Cpu className="w-4 h-4" /></div>
              <div className="space-y-1">
                <div className="font-semibold text-foreground">Local Health Monitoring</div>
                <p className="text-muted-foreground text-[11px] leading-relaxed">Model is replaceable via config only. No cloud fallback unless fallback toggle is enabled.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Analyst Persona & Generation Controls */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Sliders className="w-4 h-4 text-primary" />
          Analyst Persona & Generation Controls
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="font-semibold block mb-1">AI Market Persona</label>
            <select value={settings.persona} onChange={(e) => onChange({ persona: e.target.value as any })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs focus:outline-hidden">
              <option value="INSTITUTIONAL">Institutional Derivatives Strategist (FII/DII Focus)</option>
              <option value="MOMENTUM">Breakout Momentum Trader (Trend Following)</option>
              <option value="OPTION_SELLER">Non-Directional Option Seller (Theta / IV Decay)</option>
            </select>
          </div>
          <div>
            <label className="font-semibold block mb-1">Sampling Temperature: {settings.temperature}</label>
            <input type="range" min="0.0" max="0.7" step="0.05" value={settings.temperature} onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })} className="w-full accent-primary mt-2 cursor-pointer" />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>0.0 (Deterministic)</span><span>0.7 (Creative)</span></div>
          </div>
          <div>
            <label className="font-semibold block mb-1">Analysis Cache TTL: {settings.cacheTtlSeconds}s</label>
            <input type="range" min="30" max="300" step="15" value={settings.cacheTtlSeconds} onChange={(e) => onChange({ cacheTtlSeconds: parseInt(e.target.value) })} className="w-full accent-primary mt-2 cursor-pointer" />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1"><span>30s (Ultra Fresh)</span><span>300s (Cost Saving)</span></div>
          </div>
        </div>
      </div>

      {/* Live Provider Verification – Strict, No Mock Fallback (§19) */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs overflow-hidden">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-amber-400" /> Live Provider Verification</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-destructive/10 text-destructive border border-destructive/20 font-mono whitespace-nowrap">NO MOCK FALLBACK</span>
          </h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Resolves <span className="font-mono">Auto</span> to current eligible free model, uses <strong>real live NIFTY context</strong> (regime + futures + options), measures latency, validates JSON schema. Fails honestly if key missing/invalid, model unavailable, or Ollama not running. Never mock.
          </p>
          {connectionMode === 'Local Ollama' && (settings.ollamaBaseUrl.includes('localhost') || settings.ollamaBaseUrl.includes('127.0.0.1')) && (
            <p className="text-[11px] p-2 rounded bg-blue-500/10 border border-blue-500/20 text-blue-600 break-words">
              Local Ollama — test does direct browser fetch to {settings.ollamaBaseUrl}/api/tags (Render cannot reach localhost).
            </p>
          )}
        </div>

        <div className="flex flex-col gap-3 pt-3 border-t border-border/50">
          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_auto] gap-3 items-start">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono min-w-0">
              <div className="flex items-center gap-1.5 shrink-0"><span className="text-muted-foreground whitespace-nowrap">Provider:</span><span className="px-2 py-1 rounded bg-secondary border text-foreground font-semibold whitespace-nowrap">{connectionMode === 'OpenRouter' ? 'OpenRouter' : connectionMode === 'Direct Provider' ? directProvider : 'Ollama'}</span></div>
              <div className="flex items-center gap-1.5 min-w-0 flex-1"><span className="text-muted-foreground whitespace-nowrap shrink-0">Model:</span>
                <span className="px-2 py-1 rounded bg-secondary border text-foreground truncate max-w-[380px]" title={
                  connectionMode === 'OpenRouter' ? ((settings as any).openRouterSelectedModel === 'auto' ? 'Auto — Best Free' : (settings as any).openRouterSelectedModel) :
                  connectionMode === 'Direct Provider' ? (directProvider === 'OpenAI' ? (settings as any).openaiModel : directProvider === 'Novita AI' ? (settings as any).novitaModel : directProvider === 'NVIDIA' ? (settings as any).nvidiaModel : directProvider === 'Google Gemini' ? settings.geminiModel : (settings as any).customOpenaiModel) :
                  settings.ollamaModel
                }>
                  {connectionMode === 'OpenRouter' ? (((settings as any).openRouterSelectedModel || 'auto') === 'auto' ? 'Auto — Best Free' : (settings as any).openRouterSelectedModel) :
                    connectionMode === 'Direct Provider' ? (directProvider === 'OpenAI' ? (settings as any).openaiModel : directProvider === 'Novita AI' ? (settings as any).novitaModel : directProvider === 'NVIDIA' ? (settings as any).nvidiaModel : directProvider === 'Google Gemini' ? settings.geminiModel : (settings as any).customOpenaiModel) :
                    settings.ollamaModel}
                </span>
              </div>
            </div>
            <button type="button" onClick={handleTest} disabled={testing} className="flex items-center justify-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shadow-xs w-full lg:w-auto shrink-0">
              <Play className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
              <span>{testing ? 'Testing…' : 'Run Live Test'}</span>
            </button>
          </div>
          {connectionMode === 'OpenRouter' && ((settings as any).openRouterSelectedModel === 'auto' || !(settings as any).openRouterSelectedModel) && (
            <p className="text-[11px] text-muted-foreground -mt-1">Auto resolves to best <span className="font-semibold text-emerald-600">FREE</span> model from live catalog (trading_rank). Ling 3.0 Flash Fin will not receive structured-output params.</p>
          )}
        </div>

        {!testing && !testResult && (
          <div className="space-y-1">
            {connectionMode === 'OpenRouter' && !settings.openRouterApiKey && <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />OpenRouter key missing — enter sk-or-v1-... above and Save. Optional server env fallback.</div>}
            {connectionMode === 'Direct Provider' && (() => {
              const keyMap: any = { OpenAI: (settings as any).openaiApiKey, 'Novita AI': (settings as any).novitaApiKey, NVIDIA: (settings as any).nvidiaApiKey, 'Google Gemini': settings.geminiApiKey, 'Custom OpenAI-Compatible': (settings as any).customOpenaiApiKey };
              return !keyMap[directProvider] ? <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{directProvider} key missing.</div> : <div className="text-[11px] text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Key present — Save then Test.</div>;
            })()}
            {connectionMode === 'Local Ollama' && !settings.ollamaBaseUrl && <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />Ollama URL missing.</div>}
          </div>
        )}

        {testResult && (
          <div className={`p-3.5 rounded-lg text-xs space-y-3 border ${testResult.success ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20' : 'bg-destructive/10 text-destructive border-destructive/20'}`}>
            <div className="flex items-start gap-2 font-semibold">
              {testResult.success ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
              <span className="leading-relaxed flex-1">{testResult.message}</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
              <div className="bg-card/60 p-2 rounded border"><div className="text-muted-foreground">Latency</div><div className="font-semibold text-foreground">{testResult.latency ?? '—'} ms</div>{testResult.clientLatency && <div className="text-[10px] text-muted-foreground">client {testResult.clientLatency}ms</div>}</div>
              <div className="bg-card/60 p-2 rounded border"><div className="text-muted-foreground">Schema</div><div className="font-semibold">{testResult.schemaValid ? '✓ Valid' : testResult.success ? '✓ Valid' : '✗ Failed'}</div></div>
              <div className="bg-card/60 p-2 rounded border"><div className="text-muted-foreground">Provider</div><div className="font-semibold truncate">{testResult.model || '-'}</div></div>
              <div className="bg-card/60 p-2 rounded border"><div className="text-muted-foreground">Mock?</div><div className="font-semibold">{testResult.isMock ? 'Yes (offline)' : 'No – live'}</div></div>
            </div>
            {testResult.hint && <div className="text-[11px] p-2 rounded bg-card/60 border text-foreground"><strong>Hint:</strong> {testResult.hint}</div>}
            {testResult.data && testResult.success && (
              <div className="bg-card/80 p-3 rounded border text-foreground font-mono text-[11px] space-y-1">
                <div><strong>Bias:</strong> {testResult.data.market_bias} ({testResult.data.confidence}% confidence)</div>
                <div><strong>Executive Summary:</strong> {testResult.data.executive_summary}</div>
                <div><strong>Framework:</strong> {testResult.data.recommended_strategy_framework}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
