'use client';

// Single source of truth mapping AI Settings (localStorage) -> backend AI payloads.
// Mirrors the provider/key resolution used by Settings > LiveVerification so every
// trading surface sends the same keys/model the user configured.

import { useEffect, useState } from 'react';
import type { AISettings, DirectProviderId } from './settingsTypes';
import { getStoredSettings } from './settingsStorage';

export interface ResolvedAI {
  provider: string;
  model: string;
  allow_paid: boolean;
  openRouterApiKey?: string;
  openRouterModel?: string;
  geminiApiKey?: string;
  geminiModel?: string;
  ollamaBaseUrl?: string;
  ollamaModel?: string;
  openaiApiKey?: string;
  openaiModel?: string;
  openaiBaseUrl?: string;
  novitaApiKey?: string;
  novitaModel?: string;
  novitaBaseUrl?: string;
  nvidiaApiKey?: string;
  nvidiaModel?: string;
  nvidiaBaseUrl?: string;
  customOpenaiApiKey?: string;
  customOpenaiModel?: string;
  customOpenaiBaseUrl?: string;
  apiKey?: string;
  base_url?: string;
}

const DIRECT_MAP: Record<DirectProviderId, string> = {
  OpenAI: 'openai',
  'Novita AI': 'novita',
  NVIDIA: 'nvidia',
  'Google Gemini': 'gemini',
  'Custom OpenAI-Compatible': 'custom_openai',
};

export function getStoredAISettings(): AISettings | null {
  try {
    return getStoredSettings().ai;
  } catch {
    return null;
  }
}

/** Reactive hook — re-reads AI settings on mount + cross-tab storage updates. */
export function useAISettings(): AISettings | null {
  const [ai, setAi] = useState<AISettings | null>(null);
  /* eslint-disable react-hooks/set-state-in-effect -- hydration from localStorage */
  useEffect(() => {
    setAi(getStoredAISettings());
    const onStorage = (e: StorageEvent) => {
      if (e.key && e.key.includes('droid_app_settings')) setAi(getStoredAISettings());
    };
    const onFocus = () => setAi(getStoredAISettings());
    window.addEventListener('storage', onStorage);
    window.addEventListener('focus', onFocus);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener('focus', onFocus);
    };
  }, []);
  return ai;
}

function normModel(sel: string | undefined | null): string {
  const s = (sel || '').trim();
  if (!s || s.toLowerCase() === 'auto' || s.toLowerCase().includes('best free')) return 'auto';
  return s;
}

export function resolveAISettings(ai: AISettings | null | undefined): ResolvedAI {
  const fallback: ResolvedAI = { provider: 'openrouter', model: 'auto', allow_paid: false };
  if (!ai) return fallback;
  const mode = (ai as unknown as { connectionMode?: string }).connectionMode || 'OpenRouter';
  const allow_paid = Boolean(
    (ai as unknown as { openRouterAllowPaid?: boolean }).openRouterAllowPaid ?? !ai.openRouterFreeOnly,
  );

  if (mode === 'Direct Provider') {
    const direct = ((ai as unknown as { directProvider?: DirectProviderId }).directProvider || 'OpenAI') as DirectProviderId;
    const p = DIRECT_MAP[direct] || 'openai';
    const base: ResolvedAI = { provider: p, model: '', allow_paid };
    const anyAi = ai as unknown as Record<string, string>;
    if (p === 'openai') {
      base.openaiApiKey = anyAi.openaiApiKey || '';
      base.openaiModel = anyAi.openaiModel || 'gpt-4o-mini';
      base.openaiBaseUrl = anyAi.openaiBaseUrl || undefined;
      base.model = base.openaiModel;
    } else if (p === 'novita') {
      base.novitaApiKey = anyAi.novitaApiKey || '';
      base.novitaModel = anyAi.novitaModel || '';
      base.novitaBaseUrl = anyAi.novitaBaseUrl || undefined;
      base.model = base.novitaModel;
    } else if (p === 'nvidia') {
      base.nvidiaApiKey = anyAi.nvidiaApiKey || '';
      base.nvidiaModel = anyAi.nvidiaModel || '';
      base.nvidiaBaseUrl = anyAi.nvidiaBaseUrl || undefined;
      base.model = base.nvidiaModel;
    } else if (p === 'gemini') {
      base.geminiApiKey = ai.geminiApiKey || '';
      base.geminiModel = ai.geminiModel || 'gemini-2.5-flash';
      base.model = base.geminiModel;
    } else {
      base.apiKey = anyAi.customOpenaiApiKey || '';
      base.customOpenaiApiKey = anyAi.customOpenaiApiKey || '';
      base.customOpenaiModel = anyAi.customOpenaiModel || 'custom-model';
      base.customOpenaiBaseUrl = anyAi.customOpenaiBaseUrl || '';
      base.base_url = base.customOpenaiBaseUrl;
      base.model = base.customOpenaiModel;
    }
    return base;
  }

  if (mode === 'Local Ollama') {
    return {
      provider: 'ollama',
      model: ai.ollamaModel || 'deepseek-r1:8b',
      allow_paid,
      ollamaBaseUrl: ai.ollamaBaseUrl || 'http://localhost:11434',
      ollamaModel: ai.ollamaModel || 'deepseek-r1:8b',
    };
  }

  // OpenRouter (default)
  const sel = (ai as unknown as { openRouterSelectedModel?: string }).openRouterSelectedModel || 'auto';
  return {
    provider: 'openrouter',
    model: normModel(sel),
    allow_paid,
    openRouterApiKey: ai.openRouterApiKey || '',
    openRouterModel: normModel(sel),
    geminiApiKey: ai.geminiApiKey || undefined,
    geminiModel: ai.geminiModel || undefined,
  };
}

/** Payload for POST /api/v1/ai/analyze (unified model-aware endpoint). */
export function buildAnalyzePayload(symbol: string, ai: AISettings | null | undefined): Record<string, unknown> {
  const r = resolveAISettings(ai);
  return {
    symbol,
    provider: r.provider,
    model: r.model,
    allow_paid: r.allow_paid,
    openRouterApiKey: r.openRouterApiKey,
    openRouterModel: r.openRouterModel,
    geminiApiKey: r.geminiApiKey,
    geminiModel: r.geminiModel,
    ollamaBaseUrl: r.ollamaBaseUrl,
    ollamaModel: r.ollamaModel,
    openaiApiKey: r.openaiApiKey,
    openaiModel: r.openaiModel,
    openaiBaseUrl: r.openaiBaseUrl,
    novitaApiKey: r.novitaApiKey,
    novitaModel: r.novitaModel,
    novitaBaseUrl: r.novitaBaseUrl,
    nvidiaApiKey: r.nvidiaApiKey,
    nvidiaModel: r.nvidiaModel,
    nvidiaBaseUrl: r.nvidiaBaseUrl,
    customOpenaiApiKey: r.customOpenaiApiKey,
    customOpenaiModel: r.customOpenaiModel,
    customOpenaiBaseUrl: r.customOpenaiBaseUrl,
    apiKey: r.apiKey,
    base_url: r.base_url,
  };
}

/** Base fields for chat / strategy / validate requests. */
export function buildChatBase(ai: AISettings | null | undefined, symbol: string, contextPage?: string) {
  const r = resolveAISettings(ai);
  return {
    symbol,
    provider: r.provider,
    model: r.model || null,
    allow_paid: r.allow_paid,
    context_page: contextPage || null,
    enable_tools: true,
    openrouter_api_key: r.openRouterApiKey || null,
    gemini_api_key: r.geminiApiKey || null,
    openai_api_key: r.openaiApiKey || null,
    ollama_base_url: r.ollamaBaseUrl || null,
    ollama_model: r.ollamaModel || null,
  };
}

export function missingKeyHint(ai: AISettings | null | undefined): string | null {
  if (!ai) return 'AI settings not found — open Settings to configure a provider.';
  const mode = (ai as unknown as { connectionMode?: string }).connectionMode || 'OpenRouter';
  const anyAi = ai as unknown as Record<string, string>;
  if (mode === 'OpenRouter' && !ai.openRouterApiKey?.trim()) {
    return 'OpenRouter key missing — add sk-or-v1-… in Settings → AI Engine, then Save.';
  }
  if (mode === 'Direct Provider') {
    const direct = ((ai as unknown as { directProvider?: DirectProviderId }).directProvider || 'OpenAI') as DirectProviderId;
    const keyMap: Record<DirectProviderId, string> = {
      OpenAI: anyAi.openaiApiKey,
      'Novita AI': anyAi.novitaApiKey,
      NVIDIA: anyAi.nvidiaApiKey,
      'Google Gemini': ai.geminiApiKey,
      'Custom OpenAI-Compatible': anyAi.customOpenaiApiKey,
    };
    if (!keyMap[direct]?.trim()) return `${direct} key missing — add it in Settings → AI Engine, then Save.`;
  }
  if (mode === 'Local Ollama' && !ai.ollamaBaseUrl?.trim()) return 'Ollama URL missing — set it in Settings → AI Engine.';
  return null;
}

/** Normalize UI symbol ("NIFTY 50") to backend symbol ("NIFTY"). */
export function toBackendSymbol(symbol: string): string {
  return (symbol || 'NIFTY').toUpperCase().replace(' 50', '').trim() || 'NIFTY';
}
