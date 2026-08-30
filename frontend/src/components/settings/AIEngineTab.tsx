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
    try {
      const res = await api.generateAIAnalysis('NIFTY', settings.provider);
      setTestResult({
        success: true,
        message: `Successfully generated structured market intelligence using ${
          res.data.provider_used || settings.provider
        }!`,
        data: res.data,
      });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err?.message || 'Failed to connect to AI provider',
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

      {/* 4. Connectivity & Model Prompt Test Card */}
      <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              Test AI Model & Prompt Pipeline
            </h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Execute an end-to-end prompt test against NIFTY to verify latency and schema validation.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-muted-foreground bg-secondary px-2.5 py-1 rounded-lg border border-border">
              Model: <span className="text-foreground font-semibold">{activeModelOption?.name || settings.geminiModel || settings.openRouterModel || settings.ollamaModel}</span>
            </span>

            <button
              type="button"
              onClick={handleTestAI}
              disabled={testing}
              className="flex items-center gap-1.5 px-3.5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shadow-xs"
            >
              <Play className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
              <span>{testing ? 'Analyzing NIFTY...' : 'Run Test Analysis'}</span>
            </button>
          </div>
        </div>

        {testResult && (
          <div
            className={`p-3.5 rounded-lg text-xs space-y-2 ${
              testResult.success
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-destructive/10 text-destructive border border-destructive/20'
            }`}
          >
            <div className="flex items-center gap-2 font-semibold">
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0" />
              )}
              <span>{testResult.message}</span>
            </div>
            {testResult.data && (
              <div className="bg-card/80 p-3 rounded border border-border text-foreground font-mono text-[11px] space-y-1">
                <div>
                  <strong>Bias:</strong> {testResult.data.market_bias} ({testResult.data.confidence}% confidence)
                </div>
                <div>
                  <strong>Executive Summary:</strong> {testResult.data.executive_summary}
                </div>
                <div>
                  <strong>Recommended Framework:</strong>{' '}
                  {testResult.data.recommended_strategy_framework}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

