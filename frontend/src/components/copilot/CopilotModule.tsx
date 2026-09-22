'use client';

/* AI Copilot module: ds-commandbar + stat-chips + ds-filters + tabbar,
   mirroring the signals-desk layout. */

import { useState } from 'react';
import { Bot } from 'lucide-react';
import { useCopilot, useCopilotModels } from '@/hooks/useCopilot';
import { useNow } from '@/hooks/useNow';
import { ageLabel } from '@/lib/feedState';
import { dataFreshness } from '@/lib/signalsNormalize';
import { aiMockProvenance, MOCK_AI_SOURCE_LABEL } from '@/lib/api/ai';
import { ChatPanel } from './ChatPanel';
import { BriefingPanel } from './BriefingPanel';
import { AnalyzePanel } from './AnalyzePanel';
import { ValidatePanel } from './ValidatePanel';

type CopilotTab = 'chat' | 'briefing' | 'analyze' | 'validate';

const TABS: Array<{ id: CopilotTab; label: string }> = [
  { id: 'chat', label: 'Chat' },
  { id: 'briefing', label: 'Briefing' },
  { id: 'analyze', label: 'Analyze' },
  { id: 'validate', label: 'Validate' },
];

type ProviderStatus = { label: string; tone: string; title: string };

/**
 * Honest provider status from observable evidence only:
 * key present in Settings + a successful backend AI call. A failed or absent
 * call is OFFLINE / UNKNOWN, never a hardcoded "AI ONLINE".
 */
function resolveProviderStatus(params: {
  keyHint: string | null;
  provider: string;
  loading: boolean;
  error: string | null;
  updatedAt: number | null;
  stale: boolean;
  age: string | null;
}): ProviderStatus {
  const { keyHint, provider, loading, error, updatedAt, stale, age } = params;
  if (keyHint) {
    return { label: 'UNCONFIGURED', tone: 'b-warn', title: keyHint };
  }
  if (error) {
    return {
      label: 'OFFLINE',
      tone: 'b-bear',
      title: `Provider ${provider} is configured, but the backend AI call failed: ${error}`,
    };
  }
  if (updatedAt === null) {
    return {
      label: loading ? 'CHECKING…' : 'UNVERIFIED',
      tone: 'b-neut',
      title:
        'Provider key is present but no successful backend AI call has been observed yet — liveness is unconfirmed.',
    };
  }
  if (stale) {
    return {
      label: `STALE · ${age ?? 'age unknown'}`,
      tone: 'b-warn',
      title: `Last successful backend AI call was ${age ?? 'at an unknown time'} — provider liveness is stale.`,
    };
  }
  return {
    label: 'AI ONLINE',
    tone: 'b-info',
    title: `Provider ${provider} key present · last successful backend AI call ${age ?? 'just now'}.`,
  };
}

export function CopilotModule() {
  const [tab, setTab] = useState<CopilotTab>('chat');
  const desk = useCopilot();
  const models = useCopilotModels();
  const now = useNow(1000);

  // `useNow` starts at 0; dataFreshness falls back to a real clock internally.
  const freshness = dataFreshness(models.updatedAt, { nowMs: now });
  const callAge = now > 0 ? ageLabel(models.updatedAt, now) : null;
  const providerStatus = resolveProviderStatus({
    keyHint: desk.keyHint,
    provider: desk.provider,
    loading: models.loading,
    error: models.error,
    updatedAt: models.updatedAt,
    stale: freshness.stale,
    age: callAge,
  });
  const mockProvider = aiMockProvenance(desk.provider, null);

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>
            <Bot size={14} aria-hidden="true" /> AI Copilot
          </h2>
          <span className={`badge ${providerStatus.tone}`} title={providerStatus.title}>
            {providerStatus.label}
          </span>
          {mockProvider.isMock ? (
            <span className="badge b-warn" title={mockProvider.label ?? MOCK_AI_SOURCE_LABEL}>
              MOCK
            </span>
          ) : null}
          <span className="card-meta">{desk.instrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip" title="AI provider resolved from Settings → AI Engine">
            provider <b>{desk.provider}</b>
          </span>
          <span className="stat-chip" title="Model resolved from Settings → AI Engine">
            model <b>{desk.model}</b>
          </span>
          <span
            className="stat-chip"
            title="OpenRouter catalog: last successful backend call age and cache state"
          >
            models <b>{models.totalCount ?? '—'}</b>
            {callAge ? ` · ${callAge}` : models.loading ? ' · checking…' : ' · age unknown'}
            {models.cache?.usingCached ? ' · cached' : ''}
          </span>
          <span
            className="stat-chip"
            title={
              desk.keyHint
                ? desk.keyHint
                : 'A provider key is configured. Liveness still requires a successful call.'
            }
          >
            {desk.keyHint ? 'key missing' : 'key set'}
          </span>
        </div>
        <div className="ds-filters">
          <span className="seg" title="Active instrument">
            {desk.allInstruments.map((option) => (
              <button
                key={option}
                type="button"
                className="seg-btn"
                data-active={desk.instrument === option}
                onClick={() => desk.setInstrument(option)}
              >
                {option}
              </button>
            ))}
          </span>
          {desk.keyHint ? (
            <a className="btn" href="/settings" title={desk.keyHint}>
              Open Settings
            </a>
          ) : null}
        </div>
      </section>

      <section className="tabbar w-fit" role="tablist" aria-label="Copilot module sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'is-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </section>

      {desk.keyHint ? (
        <p className="sg-note">
          {desk.keyHint} <a href="/settings">Open Settings →</a>
        </p>
      ) : null}

      {tab === 'chat' ? (
        <ChatPanel models={models.options} modelsLoading={models.loading} settingsModel={models.defaultModelId ?? desk.model} />
      ) : null}
      {tab === 'briefing' ? <BriefingPanel /> : null}
      {tab === 'analyze' ? <AnalyzePanel /> : null}
      {tab === 'validate' ? (
        <ValidatePanel
          totalCount={models.totalCount}
          freeCount={models.freeCount}
          paidCount={models.paidCount}
          cache={models.cache}
          modelsRefreshing={models.refreshing}
          modelsError={models.error}
          onRefreshModels={() => void models.refresh()}
        />
      ) : null}
    </div>
  );
}
