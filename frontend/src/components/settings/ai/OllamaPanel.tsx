'use client';
import React, { useState } from 'react';
import { Server, CheckCircle2, AlertCircle, Cpu } from 'lucide-react';
import type { AISettings } from '@/lib/settings';
import { SUPPORTED_OLLAMA_MODELS } from '@/lib/settings';
import { SettingSection } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
  errors?: { path: string; message: string }[];
}

export function OllamaPanel({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `ai.${field}`)?.message;
  const [showCustom, setShowCustom] = useState(false);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [ollamaStatus, setOllamaStatus] = useState<'idle' | 'checking' | 'ok' | 'fail'>('idle');
  const [ollamaError, setOllamaError] = useState<string | null>(null);

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
      const models: string[] = (j.models || []).map((m: { name: string }) => m.name);
      setOllamaModels(models);
      setOllamaStatus('ok');
    } catch (e: unknown) {
      setOllamaError(e instanceof Error ? e.message : 'Failed');
      setOllamaStatus('fail');
      setOllamaModels([]);
    }
  };

  return (
    <SettingSection
      title="Local Ollama"
      description="100% on-device private inference. No cloud API key required."
      icon={Server}
      action={
        <span className="text-[10px] px-2 py-0.5 rounded-md bg-secondary border border-border/60 font-mono text-muted-foreground">
          {settings.ollamaBaseUrl || 'http://localhost:11434'}
        </span>
      }
    >
      <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
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
          <div className="text-[11px] text-muted-foreground">Health: {ollamaStatus === 'ok' ? <span className="text-emerald-600">Installed & reachable</span> : ollamaStatus === 'fail' ? <span className="text-destructive">Unavailable — install from https://ollama.com</span> : 'Unknown'}</div>
        </div>
      </div>
      <div className="p-5 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium">Local Model</label>
            <button type="button" onClick={() => setShowCustom(!showCustom)} className="text-[11px] text-muted-foreground hover:text-foreground cursor-pointer">{showCustom ? 'Select from list' : 'Custom tag'}</button>
          </div>
          {!showCustom ? (
            <select value={settings.ollamaModel || 'deepseek-r1:8b'} onChange={(e) => onChange({ ollamaModel: e.target.value })} className="w-full bg-secondary/40 border border-border/70 rounded-md px-3 py-2 text-xs font-mono cursor-pointer">
              {SUPPORTED_OLLAMA_MODELS.map((m) => (<option key={m.id} value={m.id}>{m.name} — [{m.tag}]</option>))}
              <option value="__custom__">Other / Custom local tag…</option>
            </select>
          ) : (
            <input type="text" placeholder="e.g. qwen2.5:7b" value={settings.ollamaModel} onChange={(e) => onChange({ ollamaModel: e.target.value })} className="w-full bg-secondary/40 border border-border/70 rounded-md px-3 py-2 text-xs font-mono" />
          )}
          {getError('ollamaModel') && <span className="text-[11px] text-destructive block">{getError('ollamaModel')}</span>}
          <p className="text-[11px] text-muted-foreground mt-1">For RTX 4050/16GB start with 8B-class. Later 14B/32B/70B+ without code changes.</p>
        </div>
        <div className="bg-secondary/30 border border-border/40 rounded-lg p-3.5 flex items-start gap-3 text-xs">
          <div className="bg-secondary text-muted-foreground p-2 rounded-md shrink-0 mt-0.5"><Cpu className="w-4 h-4" /></div>
          <div className="space-y-1">
            <div className="font-medium text-foreground">Local health monitoring</div>
            <p className="text-muted-foreground text-[11px] leading-relaxed">Model is replaceable via config only. No cloud fallback unless fallback toggle is enabled.</p>
          </div>
        </div>
      </div>
    </SettingSection>
  );
}
