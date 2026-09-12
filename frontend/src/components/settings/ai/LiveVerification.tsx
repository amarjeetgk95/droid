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
    <div className="card">
      <div className="card-hd">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 muted" />
          <h3 className="card-title">Inference Engine Diagnostics</h3>
        </div>
        <span className="badge b-info" style={{ fontSize: '10px' }}>
          {connectionMode === 'OpenRouter' ? 'OpenRouter' : connectionMode === 'Direct Provider' ? directProvider : 'Local Ollama'}
        </span>
      </div>

      <div className="card-bd space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="text-xs muted leading-normal max-w-xl">
            Verify active model credentials, measure network round-trip latency, and validate structured JSON output schema without mock fallbacks.
          </div>
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="btn btn-sm btn-primary flex items-center gap-1.5 shrink-0"
          >
            <Play className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} />
            <span>{testing ? 'Testing…' : 'Run Diagnostics'}</span>
          </button>
        </div>

        {!testing && !testResult && (
          <div className="pt-1">
            {connectionMode === 'OpenRouter' && !settings.openRouterApiKey && (
              <div className="badge b-bear" style={{ fontSize: '11px' }}>
                <AlertCircle className="w-3 h-3" />
                <span>OpenRouter API key missing — enter key and Save</span>
              </div>
            )}
            {connectionMode === 'Local Ollama' && !settings.ollamaBaseUrl && (
              <div className="badge b-bear" style={{ fontSize: '11px' }}>
                <AlertCircle className="w-3 h-3" />
                <span>Ollama host URL missing</span>
              </div>
            )}
          </div>
        )}

        {testResult && (
          <div
            className={`card card-pad text-xs space-y-2.5 ${
              testResult.success
                ? 'border-[var(--ds-bull)]/30 bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)]'
                : 'border-[var(--ds-bear)]/30 bg-[var(--ds-bear-wash)] text-[var(--ds-bear-strong)]'
            }`}
          >
            <div className="flex items-start gap-2 font-semibold">
              {testResult.success ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span className="leading-relaxed flex-1">{testResult.message}</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px] mono">
              <div className="stat" style={{ padding: '6px 10px' }}>
                <div className="stat-l">Latency</div>
                <div className="stat-v" style={{ fontSize: '13px' }}>{testResult.latency ?? '—'} ms</div>
              </div>
              <div className="stat" style={{ padding: '6px 10px' }}>
                <div className="stat-l">Schema</div>
                <div className="stat-v" style={{ fontSize: '13px' }}>{testResult.schemaValid ? '✓ Valid' : testResult.success ? '✓ Valid' : '✗ Failed'}</div>
              </div>
              <div className="stat" style={{ padding: '6px 10px' }}>
                <div className="stat-l">Model</div>
                <div className="stat-v truncate" style={{ fontSize: '13px' }}>{testResult.model || '-'}</div>
              </div>
              <div className="stat" style={{ padding: '6px 10px' }}>
                <div className="stat-l">Execution</div>
                <div className="stat-v" style={{ fontSize: '13px' }}>{testResult.isMock ? 'Mock' : 'Live Gateway'}</div>
              </div>
            </div>

            {testResult.data && testResult.success && (
              <div className="p-2.5 rounded bg-[var(--ds-surface)] border border-[var(--ds-border-subtle)] text-[var(--ds-ink)] mono text-[11px] space-y-1">
                <div><strong>Market Bias:</strong> {testResult.data.market_bias} ({testResult.data.confidence}% confidence)</div>
                <div><strong>Summary:</strong> {testResult.data.executive_summary}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
