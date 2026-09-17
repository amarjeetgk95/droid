'use client';
import React, { useState } from 'react';
import { Network, Shield, Eye, EyeOff } from 'lucide-react';
import type { AISettings, DirectProviderId } from '@/lib/settings';
import { SUPPORTED_GEMINI_MODELS } from '@/lib/settings';
import { DIRECT_PROVIDER_OPTIONS } from './constants';
import { SettingSection } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function DirectProviderPanel({ settings, onChange }: Props) {
  const directProvider: DirectProviderId = (settings as unknown as { directProvider: DirectProviderId }).directProvider || 'OpenAI';
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const toggleShow = (k: string) => setShowKeys((p) => ({ ...p, [k]: !p[k] }));
  const [isCustomModel, setIsCustomModel] = useState(false);
  const eyeButton = (k: string) => (
    <button
      type="button"
      onClick={() => toggleShow(k)}
      aria-label={showKeys[k] ? 'Hide API key' : 'Show API key'}
      className="absolute right-2 top-2 text-muted-foreground hover:text-foreground cursor-pointer"
    >
      {showKeys[k] ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
    </button>
  );

  return (
    <SettingSection
      title="Direct Provider"
      description="Direct API endpoints for OpenAI, Novita, NVIDIA, Gemini, or custom proxy."
      icon={Network}
      action={
        <span className="text-[10px] px-2 py-0.5 rounded-md bg-secondary border border-border/60 font-mono text-muted-foreground">
          5 adapters
        </span>
      }
    >
      <div className="p-5">
        <span className="text-xs font-medium text-foreground block mb-2">Provider</span>
        <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-5 gap-2" role="group" aria-label="Direct provider">
          {DIRECT_PROVIDER_OPTIONS.map((p) => (
            <button key={p.id} type="button" aria-pressed={directProvider === p.id} onClick={() => onChange({ directProvider: p.id } as unknown as Partial<AISettings>)} className={`p-2.5 rounded-lg border text-left cursor-pointer transition-colors ${directProvider === p.id ? 'border-foreground/30 bg-secondary/50' : 'border-border/60 bg-card hover:bg-secondary/30'}`}>
              <div className="text-xs font-medium text-foreground">{p.name}</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">{p.desc}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="p-5 border-t border-border/40">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          {directProvider === 'OpenAI' && (
            <>
              <div>
                <label htmlFor="dp-openai-key" className="text-xs font-semibold block mb-1">OpenAI API Key</label>
                <div className="relative">
                  <input id="dp-openai-key" type={showKeys['openai'] ? 'text' : 'password'} placeholder="sk-proj-..." value={(settings as unknown as { openaiApiKey: string }).openaiApiKey || ''} onChange={(e) => onChange({ openaiApiKey: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />
                  {eyeButton('openai')}
                </div>
              </div>
              <div><label htmlFor="dp-openai-model" className="text-xs font-semibold block mb-1">Model</label><input id="dp-openai-model" type="text" value={(settings as unknown as { openaiModel: string }).openaiModel || 'gpt-4o-mini'} onChange={(e) => onChange({ openaiModel: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" placeholder="gpt-4o-mini" /></div>
              <div><label htmlFor="dp-openai-base-url" className="text-xs font-semibold block mb-1">API Base URL</label><input id="dp-openai-base-url" type="text" value={(settings as unknown as { openaiBaseUrl: string }).openaiBaseUrl || 'https://api.openai.com/v1'} onChange={(e) => onChange({ openaiBaseUrl: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /><p className="text-[11px] text-muted-foreground mt-1">Leave default unless using proxy.</p></div>
            </>
          )}
          {directProvider === 'Novita AI' && (
            <>
              <div><label htmlFor="dp-novita-key" className="text-xs font-semibold block mb-1">Novita AI API Key</label><div className="relative"><input id="dp-novita-key" type={showKeys['novita'] ? 'text' : 'password'} placeholder="sk_..." value={(settings as unknown as { novitaApiKey: string }).novitaApiKey || ''} onChange={(e) => onChange({ novitaApiKey: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />{eyeButton('novita')}</div></div>
              <div><label htmlFor="dp-novita-model" className="text-xs font-semibold block mb-1">Model</label><input id="dp-novita-model" type="text" value={(settings as unknown as { novitaModel: string }).novitaModel || 'meta-llama/llama-3.3-70b-instruct'} onChange={(e) => onChange({ novitaModel: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /></div>
              <div><label htmlFor="dp-novita-base-url" className="text-xs font-semibold block mb-1">API Base URL</label><input id="dp-novita-base-url" type="text" value={(settings as unknown as { novitaBaseUrl: string }).novitaBaseUrl || 'https://api.novita.ai/v3/openai'} onChange={(e) => onChange({ novitaBaseUrl: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /></div>
            </>
          )}
          {directProvider === 'NVIDIA' && (
            <>
              <div><label htmlFor="dp-nvidia-key" className="text-xs font-semibold block mb-1">NVIDIA API Key</label><div className="relative"><input id="dp-nvidia-key" type={showKeys['nvidia'] ? 'text' : 'password'} placeholder="nvapi-..." value={(settings as unknown as { nvidiaApiKey: string }).nvidiaApiKey || ''} onChange={(e) => onChange({ nvidiaApiKey: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />{eyeButton('nvidia')}</div></div>
              <div><label htmlFor="dp-nvidia-model" className="text-xs font-semibold block mb-1">Model</label><input id="dp-nvidia-model" type="text" value={(settings as unknown as { nvidiaModel: string }).nvidiaModel || 'meta/llama-3.1-70b-instruct'} onChange={(e) => onChange({ nvidiaModel: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /></div>
              <div><label htmlFor="dp-nvidia-base-url" className="text-xs font-semibold block mb-1">API Base URL</label><input id="dp-nvidia-base-url" type="text" value={(settings as unknown as { nvidiaBaseUrl: string }).nvidiaBaseUrl || 'https://integrate.api.nvidia.com/v1'} onChange={(e) => onChange({ nvidiaBaseUrl: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /></div>
            </>
          )}
          {directProvider === 'Google Gemini' && (
            <>
              <div><label htmlFor="dp-gemini-key" className="text-xs font-semibold block mb-1">Google Gemini API Key</label><div className="relative"><input id="dp-gemini-key" type={showKeys['gemini'] ? 'text' : 'password'} placeholder="AIza..." value={settings.geminiApiKey} onChange={(e) => onChange({ geminiApiKey: e.target.value })} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />{eyeButton('gemini')}</div><a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" className="text-[11px] text-primary hover:underline">Get free key</a></div>
              <div><label htmlFor="dp-gemini-model" className="text-xs font-semibold block mb-1">Supported Gemini Model</label><div className="flex gap-2">{!isCustomModel && (<select id="dp-gemini-model" value={settings.geminiModel || 'gemini-2.5-flash'} onChange={(e) => onChange({ geminiModel: e.target.value })} className="flex-1 bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono cursor-pointer">{SUPPORTED_GEMINI_MODELS.map((m) => (<option key={m.id} value={m.id}>{m.name} — [{m.tag}]</option>))}</select>)}<button type="button" aria-pressed={isCustomModel} onClick={() => setIsCustomModel(!isCustomModel)} className="text-[11px] px-2 py-1 border border-border rounded-lg hover:bg-secondary cursor-pointer bg-card">{isCustomModel ? 'List' : 'Custom'}</button></div>{isCustomModel && <input id="dp-gemini-model" type="text" value={settings.geminiModel} onChange={(e) => onChange({ geminiModel: e.target.value })} placeholder="gemini-2.5-pro" className="w-full mt-1 bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" />}</div>
            </>
          )}
          {directProvider === 'Custom OpenAI-Compatible' && (
            <>
              <div><label htmlFor="dp-custom-key" className="text-xs font-semibold block mb-1">API Key (if required)</label><div className="relative"><input id="dp-custom-key" type={showKeys['custom'] ? 'text' : 'password'} placeholder="sk-... or empty for local" value={(settings as unknown as { customOpenaiApiKey: string }).customOpenaiApiKey || ''} onChange={(e) => onChange({ customOpenaiApiKey: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 pr-10 text-xs font-mono" />{eyeButton('custom')}</div></div>
              <div><label htmlFor="dp-custom-base-url" className="text-xs font-semibold block mb-1">API Base URL *</label><input id="dp-custom-base-url" type="text" placeholder="https://your-host/v1" value={(settings as unknown as { customOpenaiBaseUrl: string }).customOpenaiBaseUrl || ''} onChange={(e) => onChange({ customOpenaiBaseUrl: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /><p className="text-[11px] text-muted-foreground">Required. Must be OpenAI-compatible /chat/completions.</p></div>
              <div><label htmlFor="dp-custom-model" className="text-xs font-semibold block mb-1">Model</label><input id="dp-custom-model" type="text" value={(settings as unknown as { customOpenaiModel: string }).customOpenaiModel || 'custom-model'} onChange={(e) => onChange({ customOpenaiModel: e.target.value } as unknown as Partial<AISettings>)} className="w-full bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-mono" /></div>
            </>
          )}
        </div>
        <div className="bg-secondary/20 border border-border/40 rounded-lg p-3.5 space-y-2 text-xs">
          <div className="flex items-center gap-2 font-medium text-foreground"><Shield className="w-3.5 h-3.5 text-muted-foreground" /> Provider capabilities</div>
          <p className="text-[11px] text-muted-foreground leading-relaxed">Each adapter detects capabilities (tools, vision, structured outputs) and never sends unsupported params. For example, Ling 3.0 Flash Fin via OpenRouter will <span className="font-medium">not</span> receive <code className="font-mono">response_format=json_object</code> — instead it gets prompted JSON and is locally validated via Pydantic.</p>
          <div className="text-[11px] p-2 rounded-md bg-card border border-border/40"><div>Selected: <span className="font-mono font-medium">{directProvider}</span></div><div className="text-muted-foreground">No shared inference code in trading engine — all via <code className="font-mono">AIProvider</code>.</div></div>
        </div>
      </div>
      </div>
    </SettingSection>
  );
}
