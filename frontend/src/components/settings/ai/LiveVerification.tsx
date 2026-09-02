'use client';
import React, { useState } from 'react';
import { Sparkles, Play, CheckCircle2, AlertCircle } from 'lucide-react';
import type { AISettings, AIConnectionMode, DirectProviderId } from '@/lib/settings';
import { api } from '@/lib/api';

interface Props {
  settings: AISettings;
}

export function LiveVerification({ settings }: Props) {
  const connectionMode: AIConnectionMode =
    (settings as unknown as { connectionMode: AIConnectionMode }).connectionMode ||
    (settings.provider === 'openrouter' ? 'OpenRouter' : settings.provider === 'ollama' ? 'Local Ollama' : 'OpenRouter');
  const directProvider: DirectProviderId = (settings as unknown as { directProvider: DirectProviderId }).directProvider || 'OpenAI';
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean; message: string; data?: { market_bias: string; confidence: number; executive_summary: string; recommended_strategy_framework: string }; latency?: number; clientLatency?: number; schemaValid?: boolean; isMock?: boolean; hint?: string; model?: string;
  } | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    if (connectionMode === 'Direct Provider') {
      const keyMap: Record<DirectProviderId, string> = {
        OpenAI: (settings as unknown as { openaiApiKey: string }).openaiApiKey,
        'Novita AI': (settings as unknown as { novitaApiKey: string }).novitaApiKey,
        NVIDIA: (settings as unknown as { nvidiaApiKey: string }).nvidiaApiKey,
        'Google Gemini': settings.geminiApiKey,
        'Custom OpenAI-Compatible': (settings as unknown as { customOpenaiApiKey: string }).customOpenaiApiKey,
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
    if (connectionMode === 'Local Ollama' && (settings.ollamaBaseUrl.includes('localhost') || settings.ollamaBaseUrl.includes('127.0.0.1'))) {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 4000);
        const start = performance.now();
        const r = await fetch(`${settings.ollamaBaseUrl.replace(/\/$/, '')}/api/tags`, { signal: ctrl.signal });
        clearTimeout(t);
        const latency = Math.round(performance.now() - start);
        if (!r.ok) {
          setTestResult({ success: false, message: `Ollama not reachable at ${settings.ollamaBaseUrl} – HTTP ${r.status}. Run ollama serve.`, latency });
          setTesting(false);
          return;
        }
        const j = await r.json();
        const models: string[] = (j.models || []).map((m: { name: string }) => m.name);
        if (models.length > 0 && !models.some((m) => m.includes(settings.ollamaModel) || settings.ollamaModel.includes(m))) {
          setTestResult({ success: false, message: `Ollama OK (${latency}ms) but model '${settings.ollamaModel}' not found. Available: ${models.slice(0, 3).join(', ') || 'none'}. Run ollama pull ${settings.ollamaModel}.`, latency });
          setTesting(false);
          return;
        }
      } catch (e: unknown) {
        const msg = e instanceof Error && e.name === 'AbortError' ? 'Timeout (4s)' : e instanceof Error ? e.message : 'Failed';
        setTestResult({ success: false, message: `Ollama not reachable at ${settings.ollamaBaseUrl} – ${msg}. Install from https://ollama.com, then ollama serve and ollama pull ${settings.ollamaModel}.` });
        setTesting(false);
        return;
      }
    }

    try {
      let payload: Record<string, unknown> = { symbol: 'NIFTY' };
      if (connectionMode === 'OpenRouter') {
        const sel = ((settings as unknown as { openRouterSelectedModel: string }).openRouterSelectedModel || 'auto').trim();
        const effective = !sel || sel.toLowerCase() === 'auto' || sel.toLowerCase().includes('best free') ? 'auto' : sel;
        payload = { provider: 'openrouter', symbol: 'NIFTY', openRouterApiKey: settings.openRouterApiKey, openRouterModel: effective };
      } else if (connectionMode === 'Direct Provider') {
        const providerMap: Record<DirectProviderId, string> = { OpenAI: 'openai', 'Novita AI': 'novita', NVIDIA: 'nvidia', 'Google Gemini': 'gemini', 'Custom OpenAI-Compatible': 'custom_openai' };
        const p = providerMap[directProvider];
        payload = { provider: p, symbol: 'NIFTY' } as Record<string, unknown>;
        if (p === 'openai') { payload.openaiApiKey = (settings as unknown as { openaiApiKey: string }).openaiApiKey; payload.model = (settings as unknown as { openaiModel: string }).openaiModel; }
        else if (p === 'novita') { payload.novitaApiKey = (settings as unknown as { novitaApiKey: string }).novitaApiKey; payload.model = (settings as unknown as { novitaModel: string }).novitaModel; }
        else if (p === 'nvidia') { payload.nvidiaApiKey = (settings as unknown as { nvidiaApiKey: string }).nvidiaApiKey; payload.model = (settings as unknown as { nvidiaModel: string }).nvidiaModel; }
        else if (p === 'gemini') { payload.geminiApiKey = settings.geminiApiKey; payload.geminiModel = settings.geminiModel; }
        else if (p === 'custom_openai') { payload.apiKey = (settings as unknown as { customOpenaiApiKey: string }).customOpenaiApiKey; payload.model = (settings as unknown as { customOpenaiModel: string }).customOpenaiModel; payload.base_url = (settings as unknown as { customOpenaiBaseUrl: string }).customOpenaiBaseUrl; }
      } else if (connectionMode === 'Local Ollama') {
        payload = { provider: 'ollama', symbol: 'NIFTY', ollamaBaseUrl: settings.ollamaBaseUrl, ollamaModel: settings.ollamaModel };
      }
      const start = performance.now();
      const res: unknown = await api.testAIProvider(payload as { provider: string; symbol?: string });
      const clientLatency = Math.round(performance.now() - start);
      const d = (res as { data: { success: boolean; provider: string; model: string; latency_ms: number; schema_valid: boolean; is_mock?: boolean; message?: string; error?: string; hint?: string; insight?: { market_bias: string; confidence: number; executive_summary: string; recommended_strategy_framework: string } } }).data;
      setTestResult({
        success: d.success,
        message: d.success ? d.message || `Success via ${d.provider}:${d.model} in ${d.latency_ms}ms (client ${clientLatency}ms). Schema valid.` : d.error || 'Test failed',
        data: d.insight as unknown as typeof testResult extends { data?: infer U } ? U : never,
        latency: d.latency_ms,
        clientLatency,
        schemaValid: d.schema_valid,
        isMock: d.is_mock,
        hint: d.hint,
        model: d.model,
      });
    } catch (err: unknown) {
      setTestResult({ success: false, message: err instanceof Error ? err.message : 'Test failed – see hint' });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-4 shadow-xs overflow-hidden">
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold flex flex-wrap items-center gap-2">
          <span className="flex items-center gap-2"><Sparkles className="w-4 h-4 text-amber-400" /> Live Provider Verification</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-destructive/10 text-destructive border border-destructive/20 font-mono whitespace-nowrap">NO MOCK FALLBACK</span>
        </h3>
        <p className="text-xs text-muted-foreground leading-relaxed">Resolves <span className="font-mono">Auto</span> to current eligible free model, uses <strong>real live NIFTY context</strong>, measures latency, validates JSON schema. Fails honestly if key missing/invalid.</p>
      </div>
      <div className="flex flex-col gap-3 pt-3 border-t border-border/50">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_auto] gap-3 items-start">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono min-w-0">
            <div className="flex items-center gap-1.5 shrink-0"><span className="text-muted-foreground whitespace-nowrap">Provider:</span><span className="px-2 py-1 rounded bg-secondary border text-foreground font-semibold whitespace-nowrap">{connectionMode === 'OpenRouter' ? 'OpenRouter' : connectionMode === 'Direct Provider' ? directProvider : 'Ollama'}</span></div>
            <div className="flex items-center gap-1.5 min-w-0 flex-1"><span className="text-muted-foreground whitespace-nowrap shrink-0">Model:</span>
              <span className="px-2 py-1 rounded bg-secondary border text-foreground truncate max-w-[380px]" title={connectionMode === 'OpenRouter' ? ((settings as unknown as { openRouterSelectedModel: string }).openRouterSelectedModel === 'auto' ? 'Auto — Best Free' : (settings as unknown as { openRouterSelectedModel: string }).openRouterSelectedModel) : connectionMode === 'Direct Provider' ? ((directProvider === 'OpenAI' ? (settings as unknown as { openaiModel: string }).openaiModel : directProvider === 'Novita AI' ? (settings as unknown as { novitaModel: string }).novitaModel : directProvider === 'NVIDIA' ? (settings as unknown as { nvidiaModel: string }).nvidiaModel : directProvider === 'Google Gemini' ? settings.geminiModel : (settings as unknown as { customOpenaiModel: string }).customOpenaiModel) ) : settings.ollamaModel}>
                {connectionMode === 'OpenRouter' ? (((settings as unknown as { openRouterSelectedModel: string }).openRouterSelectedModel || 'auto') === 'auto' ? 'Auto — Best Free' : (settings as unknown as { openRouterSelectedModel: string }).openRouterSelectedModel) : connectionMode === 'Direct Provider' ? (directProvider === 'OpenAI' ? (settings as unknown as { openaiModel: string }).openaiModel : directProvider === 'Novita AI' ? (settings as unknown as { novitaModel: string }).novitaModel : directProvider === 'NVIDIA' ? (settings as unknown as { nvidiaModel: string }).nvidiaModel : directProvider === 'Google Gemini' ? settings.geminiModel : (settings as unknown as { customOpenaiModel: string }).customOpenaiModel) : settings.ollamaModel}
              </span>
            </div>
          </div>
          <button type="button" onClick={handleTest} disabled={testing} className="flex items-center justify-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer disabled:opacity-50 shadow-xs w-full lg:w-auto shrink-0">
            <Play className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Testing…' : 'Run Live Test'}</span>
          </button>
        </div>
      </div>
      {!testing && !testResult && (
        <div className="space-y-1">
          {connectionMode === 'OpenRouter' && !settings.openRouterApiKey && <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />OpenRouter key missing — enter sk-or-v1-... above and Save.</div>}
          {connectionMode === 'Direct Provider' && (() => {
            const keyMap: Record<string, string> = { OpenAI: (settings as unknown as { openaiApiKey: string }).openaiApiKey, 'Novita AI': (settings as unknown as { novitaApiKey: string }).novitaApiKey, NVIDIA: (settings as unknown as { nvidiaApiKey: string }).nvidiaApiKey, 'Google Gemini': settings.geminiApiKey, 'Custom OpenAI-Compatible': (settings as unknown as { customOpenaiApiKey: string }).customOpenaiApiKey };
            return !keyMap[directProvider] ? <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />{directProvider} key missing.</div> : <div className="text-[11px] text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Key present — Save then Test.</div>;
          })()}
          {connectionMode === 'Local Ollama' && !settings.ollamaBaseUrl && <div className="text-[11px] text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />Ollama URL missing.</div>}
        </div>
      )}
      {testResult && (
        <div className={`p-3.5 rounded-lg text-xs space-y-3 border ${testResult.success ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20' : 'bg-destructive/10 text-destructive border-destructive/20'}`}>
          <div className="flex items-start gap-2 font-semibold">{testResult.success ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" /> : <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />}<span className="leading-relaxed flex-1">{testResult.message}</span></div>
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
  );
}
