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
  Info,
  ChevronDown,
} from 'lucide-react';
import {
  AISettings,
  SUPPORTED_GEMINI_MODELS,
  SUPPORTED_OPENROUTER_MODELS,
  SUPPORTED_OLLAMA_MODELS,
  SupportedModelOption,
} from '@/lib/settings';
import { api } from '@/lib/api';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function AIEngineTab({ settings, onChange }: Props) {
  const [showKey, setShowKey] = useState(false);
  const [isCustomModel, setIsCustomModel] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
    data?: any;
  } | null>(null);

  // Active Model Resolution & Details
  const getActiveModelOption = (): SupportedModelOption | undefined => {
    if (settings.provider === 'gemini') {
      return SUPPORTED_GEMINI_MODELS.find((m) => m.id === settings.geminiModel);
    }
    if (settings.provider === 'openrouter') {
      return SUPPORTED_OPENROUTER_MODELS.find((m) => m.id === settings.openRouterModel);
    }
    if (settings.provider === 'ollama') {
      return SUPPORTED_OLLAMA_MODELS.find((m) => m.id === settings.ollamaModel);
    }
    return undefined;
  };

  const activeModelOption = getActiveModelOption();

  const handleTestAI = async () => {
    setTesting(true);
    setTestResult(null);

    // Pre-flight validation – honest, no silent mock
    if (settings.provider === 'gemini' && !settings.geminiApiKey) {
      setTestResult({ success: false, message: 'Gemini API key missing. Paste your AIza… key above, then save.' });
      setTesting(false);
      return;
    }
    if (settings.provider === 'openrouter' && !settings.openRouterApiKey) {
      setTestResult({ success: false, message: 'OpenRouter API key missing. Paste your sk-or-… key above, then save.' });
      setTesting(false);
      return;
    }
    if (settings.provider === 'ollama') {
      if (!settings.ollamaBaseUrl) {
        setTestResult({ success: false, message: 'Ollama URL missing. Set your Ollama base URL (e.g. http://localhost:11434).' });
        setTesting(false);
        return;
      }
      // Direct browser check for Ollama – backend on Render cannot reach localhost
      const isLocal = settings.ollamaBaseUrl.includes('localhost') || settings.ollamaBaseUrl.includes('127.0.0.1');
      if (isLocal) {
        try {
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 4000);
          const start = performance.now();
          const r = await fetch(`${settings.ollamaBaseUrl.replace(/\/$/, '')}/api/tags`, { signal: ctrl.signal });
          clearTimeout(t);
          const latency = Math.round(performance.now() - start);
          if (!r.ok) {
            setTestResult({
              success: false,
              message: `Ollama not reachable at ${settings.ollamaBaseUrl} – HTTP ${r.status}. Is Ollama running? Run \`ollama serve\`.`,
              latency,
            } as any);
            setTesting(false);
            return;
          }
          const j = await r.json();
          const models: string[] = (j.models || []).map((m: any) => m.name);
          if (models.length > 0 && !models.some((m) => m.includes(settings.ollamaModel) || settings.ollamaModel.includes(m))) {
            setTestResult({
              success: false,
              message: `Ollama is running at ${settings.ollamaBaseUrl} (latency ${latency}ms) but model '${settings.ollamaModel}' not found. Available: ${models.slice(0, 3).join(', ') || 'none'}. Run \`ollama pull ${settings.ollamaModel}\`.`,
              latency,
            } as any);
            setTesting(false);
            return;
          }
          // Local Ollama is reachable – now do full prompt test via backend (which will also try but we already proved connectivity)
          // Fall through to backend test for full prompt + schema validation
        } catch (e: any) {
          const msg = e.name === 'AbortError' ? 'Timeout (4s)' : e.message;
          setTestResult({
            success: false,
            message: `Ollama not reachable at ${settings.ollamaBaseUrl} – ${msg}. Is Ollama installed? Install from https://ollama.com, then \`ollama serve\` and \`ollama pull ${settings.ollamaModel}\`. Backend cannot test localhost directly; this browser check proves it.`,
          });
          setTesting(false);
          return;
        }
      }
    }

    try {
      const payload: any = {
        provider: settings.provider,
        symbol: 'NIFTY',
        geminiApiKey: settings.geminiApiKey,
        geminiModel: settings.geminiModel,
        openRouterApiKey: settings.openRouterApiKey,
        openRouterModel: settings.openRouterModel,
        ollamaBaseUrl: settings.ollamaBaseUrl,
        ollamaModel: settings.ollamaModel,
      };
      const start = performance.now();
      const res: any = await api.testAIProvider(payload);
      const clientLatency = Math.round(performance.now() - start);
      const d = res.data;
      // Backend already returns latency_ms and schema_valid
      setTestResult({
        success: d.success,
        message: d.success
          ? d.message || `Success via ${d.provider}:${d.model} in ${d.latency_ms}ms (client ${clientLatency}ms). Schema valid.`
          : d.error || 'Test failed',
        data: d.insight,
        latency: d.latency_ms,
        clientLatency,
        schemaValid: d.schema_valid,
        isMock: d.is_mock,
        hint: d.hint,
        model: d.model,
      } as any);
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.message || 'Test failed – see hint',
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. AI Provider Selection */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            AI Model Engine & Provider
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Choose the intelligence engine for automated market synthesis, bias detection, and strategy formulation.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            {
              id: 'mock_ai',
              name: 'Mock AI Analyst',
              badge: 'Deterministic',
              desc: 'Instant local heuristics for offline testing',
            },
            {
              id: 'gemini',
              name: 'Google Gemini',
              badge: 'Recommended',
              desc: 'Gemini 2.5 Flash / Pro via Google AI Studio',
            },
            {
              id: 'openrouter',
              name: 'OpenRouter Gateway',
              badge: 'Multi-Model',
              desc: 'Claude 3.7 Sonnet, DeepSeek R1, GPT-4o',
            },
            {
              id: 'ollama',
              name: 'Local Ollama',
              badge: '100% Private',
              desc: 'Self-hosted LLMs via Render cloud',
            },
          ].map((p) => {
            const isSelected = settings.provider === p.id;
            return (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  onChange({ provider: p.id as any });
                  setIsCustomModel(false);
                }}
                className={`flex flex-col text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'border-primary bg-primary/10 ring-2 ring-primary/20'
                    : 'border-border bg-card hover:bg-secondary/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-xs text-foreground">{p.name}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
                      isSelected
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-muted text-muted-foreground'
                    }`}
                  >
                    {p.badge}
                  </span>
                </div>
                <span className="text-[11px] text-muted-foreground mt-2">{p.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Provider API Key & Model Dropdown Configuration */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Key className="w-4 h-4 text-primary" />
          {settings.provider === 'mock_ai'
            ? 'Mock AI Model & Heuristic Configuration'
            : settings.provider === 'gemini'
            ? 'Google Gemini API Key & Model Selection'
            : settings.provider === 'openrouter'
            ? 'OpenRouter API Key & Supported Models'
            : 'Ollama Server Endpoint & Local Models'}
        </h3>

        {/* 2A. Google Gemini Config */}
        {settings.provider === 'gemini' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* API Key */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  Google Gemini API Key
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    placeholder="AIzaSy..."
                    value={settings.geminiApiKey}
                    onChange={(e) => onChange({ geminiApiKey: e.target.value })}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <span className="text-[11px] text-muted-foreground mt-1 block">
                  Get a free API key from{' '}
                  <a
                    href="https://aistudio.google.com/app/apikey"
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary hover:underline"
                  >
                    Google AI Studio
                  </a>
                  .
                </span>
              </div>

              {/* Model Dropdown */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-foreground">
                    Supported Gemini Model
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsCustomModel(!isCustomModel)}
                    className="text-[11px] text-primary hover:underline cursor-pointer"
                  >
                    {isCustomModel ? 'Select from list' : 'Custom Model'}
                  </button>
                </div>

                {!isCustomModel ? (
                  <div className="relative">
                    <select
                      value={settings.geminiModel || 'gemini-2.5-flash'}
                      onChange={(e) => {
                        if (e.target.value === '__custom__') {
                          setIsCustomModel(true);
                        } else {
                          onChange({ geminiModel: e.target.value });
                        }
                      }}
                      className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono cursor-pointer"
                    >
                      {SUPPORTED_GEMINI_MODELS.map((model) => (
                        <option key={model.id} value={model.id}>
                          {model.name} — [{model.tag}]
                        </option>
                      ))}
                      <option value="__custom__">⚙️ Other / Custom Model ID...</option>
                    </select>
                  </div>
                ) : (
                  <input
                    type="text"
                    placeholder="e.g. gemini-2.5-pro or tunedModels/..."
                    value={settings.geminiModel}
                    onChange={(e) => onChange({ geminiModel: e.target.value })}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono focus:outline-hidden focus:border-primary"
                  />
                )}
              </div>
            </div>

            {/* Model Info Card */}
            {activeModelOption && (
              <div className="bg-secondary/30 border border-border/60 rounded-xl p-3.5 flex items-start gap-3 text-xs">
                <div className="bg-primary/10 text-primary p-2 rounded-lg shrink-0 mt-0.5">
                  <Cpu className="w-4 h-4" />
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">{activeModelOption.name}</span>
                    <span className="text-[10px] bg-primary/15 text-primary px-2 py-0.5 rounded font-mono font-medium">
                      {activeModelOption.tag}
                    </span>
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {activeModelOption.description}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 2B. OpenRouter Config */}
        {settings.provider === 'openrouter' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* API Key */}
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  OpenRouter API Key
                </label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    placeholder="sk-or-v1-..."
                    value={settings.openRouterApiKey}
                    onChange={(e) => onChange({ openRouterApiKey: e.target.value })}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs text-foreground font-mono"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                <span className="text-[11px] text-muted-foreground mt-1 block">
                  Unified key for Claude, DeepSeek, GPT-4o, and Llama models.
                </span>
              </div>

              {/* Model Dropdown */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-foreground">
                    Supported OpenRouter Model
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsCustomModel(!isCustomModel)}
                    className="text-[11px] text-primary hover:underline cursor-pointer"
                  >
                    {isCustomModel ? 'Select from list' : 'Custom Model'}
                  </button>
                </div>

                {!isCustomModel ? (
                  <select
                    value={settings.openRouterModel || 'anthropic/claude-3.7-sonnet'}
                    onChange={(e) => {
                      if (e.target.value === '__custom__') {
                        setIsCustomModel(true);
                      } else {
                        onChange({ openRouterModel: e.target.value });
                      }
                    }}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono cursor-pointer"
                  >
                    {SUPPORTED_OPENROUTER_MODELS.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name} — [{model.tag}]
                      </option>
                    ))}
                    <option value="__custom__">⚙️ Other / Custom Model ID...</option>
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="e.g. meta-llama/llama-3.3-70b-instruct"
                    value={settings.openRouterModel}
                    onChange={(e) => onChange({ openRouterModel: e.target.value })}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono focus:outline-hidden focus:border-primary"
                  />
                )}
              </div>
            </div>

            {/* Model Info Card */}
            {activeModelOption && (
              <div className="bg-secondary/30 border border-border/60 rounded-xl p-3.5 flex items-start gap-3 text-xs">
                <div className="bg-primary/10 text-primary p-2 rounded-lg shrink-0 mt-0.5">
                  <Cpu className="w-4 h-4" />
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">{activeModelOption.name}</span>
                    <span className="text-[10px] bg-primary/15 text-primary px-2 py-0.5 rounded font-mono font-medium">
                      {activeModelOption.tag}
                    </span>
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {activeModelOption.description}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 2C. Ollama Config */}
        {settings.provider === 'ollama' && (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-foreground block mb-1">
                  Ollama Base Server URL
                </label>
                <input
                  type="text"
                  value={settings.ollamaBaseUrl}
                  onChange={(e) => onChange({ ollamaBaseUrl: e.target.value })}
                  className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono"
                />
                <span className="text-[11px] text-muted-foreground mt-1 block">
                  Default local server port is 11434.
                </span>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-semibold text-foreground">
                    Installed Ollama Model
                  </label>
                  <button
                    type="button"
                    onClick={() => setIsCustomModel(!isCustomModel)}
                    className="text-[11px] text-primary hover:underline cursor-pointer"
                  >
                    {isCustomModel ? 'Select from list' : 'Custom Tag'}
                  </button>
                </div>

                {!isCustomModel ? (
                  <select
                    value={settings.ollamaModel || 'deepseek-r1:8b'}
                    onChange={(e) => {
                      if (e.target.value === '__custom__') {
                        setIsCustomModel(true);
                      } else {
                        onChange({ ollamaModel: e.target.value });
                      }
                    }}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden focus:border-primary font-mono cursor-pointer"
                  >
                    {SUPPORTED_OLLAMA_MODELS.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name} — [{model.tag}]
                      </option>
                    ))}
                    <option value="__custom__">⚙️ Other / Custom Local Tag...</option>
                  </select>
                ) : (
                  <input
                    type="text"
                    placeholder="e.g. qwen2.5-coder:14b"
                    value={settings.ollamaModel}
                    onChange={(e) => onChange({ ollamaModel: e.target.value })}
                    className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground font-mono focus:outline-hidden focus:border-primary"
                  />
                )}
              </div>
            </div>

            {/* Model Info Card */}
            {activeModelOption && (
              <div className="bg-secondary/30 border border-border/60 rounded-xl p-3.5 flex items-start gap-3 text-xs">
                <div className="bg-primary/10 text-primary p-2 rounded-lg shrink-0 mt-0.5">
                  <Cpu className="w-4 h-4" />
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-foreground">{activeModelOption.name}</span>
                    <span className="text-[10px] bg-primary/15 text-primary px-2 py-0.5 rounded font-mono font-medium">
                      {activeModelOption.tag}
                    </span>
                  </div>
                  <p className="text-muted-foreground text-[11px] leading-relaxed">
                    {activeModelOption.description}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 2D. Mock AI - zero config */}
        {settings.provider === 'mock_ai' && (
          <div className="bg-secondary/30 border border-border/60 rounded-xl p-4 flex items-start gap-3 text-xs">
            <div className="bg-primary/10 text-primary p-2 rounded-lg shrink-0"><Cpu className="w-4 h-4" /></div>
            <div>
              <p className="font-semibold text-foreground">Mock Analyst — Instant & Offline</p>
              <p className="text-muted-foreground text-[11px] mt-1">Deterministic rule engine, no API key needed. Switch to Gemini/OpenRouter for live LLM synthesis.</p>
            </div>
          </div>
        )}
      </div>

      {/* 3. Analyst Persona & Generation Controls */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
          <Sliders className="w-4 h-4 text-primary" />
          Analyst Persona & Generation Controls
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
          <div>
            <label className="font-semibold text-foreground block mb-1">
              AI Market Persona
            </label>
            <select
              value={settings.persona}
              onChange={(e) => onChange({ persona: e.target.value as any })}
              className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs text-foreground focus:outline-hidden"
            >
              <option value="INSTITUTIONAL">Institutional Derivatives Strategist (FII/DII Focus)</option>
              <option value="MOMENTUM">Breakout Momentum Trader (Trend Following)</option>
              <option value="OPTION_SELLER">Non-Directional Option Seller (Theta / IV Decay)</option>
            </select>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Sampling Temperature: {settings.temperature}
            </label>
            <input
              type="range"
              min="0.0"
              max="0.7"
              step="0.05"
              value={settings.temperature}
              onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
              className="w-full accent-primary mt-2 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
              <span>0.0 (Deterministic)</span>
              <span>0.7 (Creative)</span>
            </div>
          </div>

          <div>
            <label className="font-semibold text-foreground block mb-1">
              Analysis Cache TTL: {settings.cacheTtlSeconds}s
            </label>
            <input
              type="range"
              min="30"
              max="300"
              step="15"
              value={settings.cacheTtlSeconds}
              onChange={(e) => onChange({ cacheTtlSeconds: parseInt(e.target.value) })}
              className="w-full accent-primary mt-2 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
              <span>30s (Ultra Fresh)</span>
              <span>300s (Cost Saving)</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Live Provider Verification – Strict, No Mock Fallback */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" />
            Live Provider Verification
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-destructive/10 text-destructive border border-destructive/20 font-mono">NO MOCK FALLBACK</span>
          </h3>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Runs a <strong>real</strong> end-to-end test with live NIFTY market context (regime + futures + options). Measures latency, validates JSON schema, and <strong>fails honestly</strong> if Ollama is not installed, API key is missing/invalid, or model is not pulled. No deterministic mock data is used for gemini/openrouter/ollama.
          </p>
          {settings.provider === 'mock_ai' && (
            <p className="text-[11px] p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-600">
              Mock AI is offline & deterministic – it does not call any LLM. “Run Test” will only verify prompt building and schema (≈30ms). Switch to Gemini/OpenRouter/Ollama for a live test.
            </p>
          )}
          {settings.provider === 'ollama' && (settings.ollamaBaseUrl.includes('localhost') || settings.ollamaBaseUrl.includes('127.0.0.1')) && (
            <p className="text-[11px] p-2 rounded bg-blue-500/10 border border-blue-500/20 text-blue-600">
              Ollama is local – the test does a <strong>direct browser fetch</strong> to {settings.ollamaBaseUrl}/api/tags (Render cannot reach localhost). Ensure <code>ollama serve</code> is running and CORS is allowed.
            </p>
          )}
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 border-t border-border/50">
          <div className="flex items-center gap-2 text-[11px] font-mono">
            <span className="text-muted-foreground">Provider:</span>
            <span className="px-2 py-1 rounded bg-secondary border border-border text-foreground font-semibold">{settings.provider}</span>
            <span className="text-muted-foreground">Model:</span>
            <span className="px-2 py-1 rounded bg-secondary border border-border text-foreground">{activeModelOption?.name || settings.geminiModel || settings.openRouterModel || settings.ollamaModel || '—'}</span>
          </div>
          <button
            type="button"
            onClick={handleTestAI}
            disabled={testing}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shadow-xs self-start sm:self-auto"
          >
            <Play className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Testing…' : settings.provider === 'mock_ai' ? 'Run Mock Test' : 'Run Live Test'}</span>
          </button>
        </div>

        {/* Pre-flight warnings */}
        {!testing && !testResult && (
          <div className="space-y-1">
            {settings.provider === 'gemini' && !settings.geminiApiKey && (
              <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> Gemini API key missing – test will fail.</div>
            )}
            {settings.provider === 'openrouter' && !settings.openRouterApiKey && (
              <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> OpenRouter key missing – test will fail.</div>
            )}
            {settings.provider === 'ollama' && !settings.ollamaBaseUrl && (
              <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> Ollama URL missing.</div>
            )}
          </div>
        )}

        {testResult && (
          <div
            className={`p-3.5 rounded-lg text-xs space-y-3 border ${
              (testResult as any).success
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20'
                : 'bg-destructive/10 text-destructive border-destructive/20'
            }`}
          >
            <div className="flex items-start gap-2 font-semibold">
              {(testResult as any).success ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}
              <span className="leading-relaxed flex-1">{(testResult as any).message}</span>
            </div>

            {/* Diagnostics grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] font-mono">
              <div className="bg-card/60 p-2 rounded border border-border">
                <div className="text-muted-foreground">Latency</div>
                <div className="font-semibold text-foreground">{(testResult as any).latency ?? (testResult as any).latency_ms ?? '—'} ms</div>
                {(testResult as any).clientLatency && <div className="text-[10px] text-muted-foreground">client {(testResult as any).clientLatency}ms</div>}
              </div>
              <div className="bg-card/60 p-2 rounded border border-border">
                <div className="text-muted-foreground">Schema</div>
                <div className="font-semibold">{(testResult as any).schemaValid ? '✓ Valid' : (testResult as any).success ? '✓ Valid' : '✗ Failed'}</div>
              </div>
              <div className="bg-card/60 p-2 rounded border border-border">
                <div className="text-muted-foreground">Provider</div>
                <div className="font-semibold text-foreground truncate">{(testResult as any).model || settings.provider}</div>
              </div>
              <div className="bg-card/60 p-2 rounded border border-border">
                <div className="text-muted-foreground">Mock?</div>
                <div className="font-semibold">{(testResult as any).isMock ? 'Yes (offline)' : 'No – live'}</div>
              </div>
            </div>

            {(testResult as any).hint && (
              <div className="text-[11px] p-2 rounded bg-card/60 border border-border text-foreground leading-relaxed">
                <strong>Hint:</strong> {(testResult as any).hint}
              </div>
            )}

            {(testResult as any).data && (testResult as any).success && (
              <div className="bg-card/80 p-3 rounded border border-border text-foreground font-mono text-[11px] space-y-1">
                <div><strong>Bias:</strong> {(testResult as any).data.market_bias} ({(testResult as any).data.confidence}% confidence)</div>
                <div><strong>Executive Summary:</strong> {(testResult as any).data.executive_summary}</div>
                <div><strong>Framework:</strong> {(testResult as any).data.recommended_strategy_framework}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

