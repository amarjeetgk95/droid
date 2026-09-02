'use client';
import React, { useState } from 'react';
import { Key, CheckCircle2, AlertCircle, Eye, EyeOff } from 'lucide-react';
import type { AISettings } from '@/lib/settings';
import { OpenRouterModelSelector } from '../OpenRouterModelSelector';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
  errors?: { path: string; message: string }[];
}

export function OpenRouterPanel({ settings, onChange, errors = [] }: Props) {
  const getError = (field: string) => errors.find((e) => e.path === `ai.${field}`)?.message;
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const toggleShow = (k: string) => setShowKeys((p) => ({ ...p, [k]: !p[k] }));

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-sm">
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
          <input type={showKeys['openrouter'] ? 'text' : 'password'} placeholder="sk-or-v1-..." value={settings.openRouterApiKey} onChange={(e) => onChange({ openRouterApiKey: e.target.value })} className="w-full bg-card border border-border rounded-lg px-3 py-2.5 pr-10 text-xs font-mono focus:border-primary focus:outline-none" />
          <button type="button" onClick={() => toggleShow('openrouter')} className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground cursor-pointer">
            {showKeys['openrouter'] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>
        {getError('openRouterApiKey') && <span className="text-[11px] text-destructive block">{getError('openRouterApiKey')}</span>}
        <div className="text-[11px] flex items-center gap-1">
          {settings.openRouterApiKey ? <span className="text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" />Key set • Save then Run Live Test</span> : <span className="text-amber-600 flex items-center gap-1"><AlertCircle className="w-3 h-3" />No key — add and Save</span>}
        </div>
      </div>
      <OpenRouterModelSelector settings={settings} onChange={onChange} />
    </div>
  );
}
