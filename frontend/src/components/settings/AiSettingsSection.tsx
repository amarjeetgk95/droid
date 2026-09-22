'use client';

import type { AISettings, AIConnectionMode, DirectProviderId, AIRoutingMode } from '@/lib/settingsTypes';
import { getFieldError, type ValidationError } from '@/lib/settingsSchema';
import { SelectField, TextField, ToggleField } from './fields';
import { AiModelPicker } from './AiModelPicker';

const CONNECTION_MODES: AIConnectionMode[] = ['OpenRouter', 'Direct Provider', 'Local Ollama'];
const DIRECT_PROVIDERS: DirectProviderId[] = [
  'OpenAI',
  'Novita AI',
  'NVIDIA',
  'Google Gemini',
  'Custom OpenAI-Compatible',
];
const ROUTING_MODES: AIRoutingMode[] = ['Manual', 'Task Optimized', 'Best Available', 'Cost Optimized'];
const PROVIDERS: AISettings['provider'][] = ['openrouter', 'gemini', 'openai', 'novita', 'nvidia', 'ollama', 'custom'];
const PERSONAS: AISettings['persona'][] = ['INSTITUTIONAL', 'MOMENTUM', 'OPTION_SELLER'];

export function AiSettingsSection({
  value,
  onChange,
  errors,
}: {
  value: AISettings;
  onChange: (patch: Partial<AISettings>) => void;
  errors: ValidationError[];
}) {
  const mode = value.connectionMode ?? 'OpenRouter';

  return (
    <div className="grid gap-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <SelectField
          label="Connection mode"
          value={mode}
          options={CONNECTION_MODES}
          onChange={(next) => onChange({ connectionMode: next })}
        />
        <SelectField
          label="Provider"
          value={value.provider}
          options={PROVIDERS}
          onChange={(next) => onChange({ provider: next, connectionMode: next === 'ollama' ? 'Local Ollama' : mode })}
        />
        <SelectField
          label="Routing mode"
          value={value.routingMode ?? 'Task Optimized'}
          options={ROUTING_MODES}
          onChange={(next) => onChange({ routingMode: next })}
        />
      </div>

      {mode === 'OpenRouter' ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <TextField
              label="OpenRouter API key"
              type="password"
              value={value.openRouterApiKey}
              placeholder="sk-or-…"
              hint="Stored locally and in your settings blob; empty keeps the existing key."
              error={getFieldError(errors, 'ai.openRouterApiKey')}
              onChange={(next) => onChange({ openRouterApiKey: next })}
            />
            <ToggleField
              label="Allow paid models"
              checked={value.openRouterAllowPaid ?? false}
              onChange={(next) =>
                onChange({
                  openRouterAllowPaid: next,
                  openRouterFreeOnly: !next,
                  openRouterPricingFilter: next ? 'ALL' : 'FREE',
                })
              }
              hint="When off, only zero-cost models are routed. Picking a paid model turns this on."
            />
          </div>
          <AiModelPicker
            apiKey={value.openRouterApiKey ?? ''}
            selectedModel={(value.openRouterSelectedModel || value.openRouterModel || 'auto').trim() || 'auto'}
            allowPaid={value.openRouterAllowPaid ?? false}
            onPick={(pick) =>
              onChange({
                openRouterSelectedModel: pick.model,
                openRouterModel: pick.model,
                ...(pick.isFree === false
                  ? { openRouterAllowPaid: true, openRouterFreeOnly: false, openRouterPricingFilter: 'ALL' as const }
                  : null),
              })
            }
          />
        </div>
      ) : null}

      {mode === 'Direct Provider' ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <SelectField
              label="Direct provider"
              value={value.directProvider ?? 'OpenAI'}
              options={DIRECT_PROVIDERS}
              onChange={(next) => onChange({ directProvider: next })}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {(value.directProvider ?? 'OpenAI') === 'OpenAI' ? (
              <>
                <TextField
                  label="OpenAI API key"
                  type="password"
                  value={value.openaiApiKey ?? ''}
                  onChange={(next) => onChange({ openaiApiKey: next })}
                />
                <TextField
                  label="OpenAI model"
                  value={value.openaiModel ?? ''}
                  onChange={(next) => onChange({ openaiModel: next })}
                />
                <TextField
                  label="OpenAI base URL"
                  value={value.openaiBaseUrl ?? ''}
                  onChange={(next) => onChange({ openaiBaseUrl: next })}
                />
              </>
            ) : null}
            {(value.directProvider ?? 'OpenAI') === 'Novita AI' ? (
              <>
                <TextField
                  label="Novita API key"
                  type="password"
                  value={value.novitaApiKey ?? ''}
                  onChange={(next) => onChange({ novitaApiKey: next })}
                />
                <TextField
                  label="Novita model"
                  value={value.novitaModel ?? ''}
                  onChange={(next) => onChange({ novitaModel: next })}
                />
                <TextField
                  label="Novita base URL"
                  value={value.novitaBaseUrl ?? ''}
                  onChange={(next) => onChange({ novitaBaseUrl: next })}
                />
              </>
            ) : null}
            {(value.directProvider ?? 'OpenAI') === 'NVIDIA' ? (
              <>
                <TextField
                  label="NVIDIA API key"
                  type="password"
                  value={value.nvidiaApiKey ?? ''}
                  onChange={(next) => onChange({ nvidiaApiKey: next })}
                />
                <TextField
                  label="NVIDIA model"
                  value={value.nvidiaModel ?? ''}
                  onChange={(next) => onChange({ nvidiaModel: next })}
                />
                <TextField
                  label="NVIDIA base URL"
                  value={value.nvidiaBaseUrl ?? ''}
                  onChange={(next) => onChange({ nvidiaBaseUrl: next })}
                />
              </>
            ) : null}
            {(value.directProvider ?? 'OpenAI') === 'Google Gemini' ? (
              <>
                <TextField
                  label="Gemini API key"
                  type="password"
                  value={value.geminiApiKey}
                  onChange={(next) => onChange({ geminiApiKey: next })}
                />
                <TextField
                  label="Gemini model"
                  value={value.geminiModel}
                  error={getFieldError(errors, 'ai.geminiModel')}
                  onChange={(next) => onChange({ geminiModel: next })}
                />
                <TextField
                  label="Gemini base URL"
                  value={value.geminiBaseUrl ?? ''}
                  onChange={(next) => onChange({ geminiBaseUrl: next })}
                />
              </>
            ) : null}
            {(value.directProvider ?? 'OpenAI') === 'Custom OpenAI-Compatible' ? (
              <>
                <TextField
                  label="Custom API key"
                  type="password"
                  value={value.customOpenaiApiKey ?? ''}
                  onChange={(next) => onChange({ customOpenaiApiKey: next })}
                />
                <TextField
                  label="Custom model"
                  value={value.customOpenaiModel ?? ''}
                  onChange={(next) => onChange({ customOpenaiModel: next })}
                />
                <TextField
                  label="Custom base URL"
                  value={value.customOpenaiBaseUrl ?? ''}
                  placeholder="https://host/v1"
                  error={getFieldError(errors, 'ai.customOpenaiBaseUrl')}
                  onChange={(next) => onChange({ customOpenaiBaseUrl: next })}
                />
              </>
            ) : null}
          </div>
        </>
      ) : null}

      {mode === 'Local Ollama' ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <TextField
            label="Ollama base URL"
            value={value.ollamaBaseUrl}
            placeholder="http://127.0.0.1:11434"
            error={getFieldError(errors, 'ai.ollamaBaseUrl')}
            onChange={(next) => onChange({ ollamaBaseUrl: next })}
          />
          <TextField
            label="Ollama model"
            value={value.ollamaModel}
            error={getFieldError(errors, 'ai.ollamaModel')}
            onChange={(next) => onChange({ ollamaModel: next })}
          />
          <ToggleField
            label="Fallback to Ollama"
            checked={value.fallbackEnabled ?? false}
            onChange={(next) => onChange({ fallbackEnabled: next })}
            hint={`Fallback model: ${value.fallbackOllamaModel ?? 'deepseek-r1:8b'}`}
          />
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <SelectField
          label="Persona"
          value={value.persona}
          options={PERSONAS}
          onChange={(next) => onChange({ persona: next })}
        />
        <TextField
          label="Temperature"
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={value.temperature}
          error={getFieldError(errors, 'ai.temperature')}
          onChange={(next) => onChange({ temperature: Number(next) })}
        />
        <TextField
          label="Cache TTL (seconds)"
          type="number"
          min={0}
          max={3600}
          step={1}
          value={value.cacheTtlSeconds}
          error={getFieldError(errors, 'ai.cacheTtlSeconds')}
          onChange={(next) => onChange({ cacheTtlSeconds: Number(next) })}
        />
      </div>
    </div>
  );
}
