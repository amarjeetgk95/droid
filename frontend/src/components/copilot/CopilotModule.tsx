'use client';

/* AI Copilot module: ds-commandbar + stat-chips + ds-filters + tabbar,
   mirroring the signals-desk layout. */

import { useState } from 'react';
import { Bot } from 'lucide-react';
import { useCopilot, useCopilotModels } from '@/hooks/useCopilot';
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

export function CopilotModule() {
  const [tab, setTab] = useState<CopilotTab>('chat');
  const desk = useCopilot();
  const models = useCopilotModels();

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>
            <Bot size={14} aria-hidden="true" /> AI Copilot
          </h2>
          <span className="badge b-info" title="Streaming copilot, briefings, analysis and trade audit">
            AI ONLINE
          </span>
          <span className="card-meta">{desk.instrument}</span>
        </div>
        <div className="stat-chips">
          <span className="stat-chip">
            provider <b>{desk.provider}</b>
          </span>
          <span className="stat-chip">
            model <b>{desk.model}</b>
          </span>
          <span className="stat-chip" title="Models in the OpenRouter catalog">
            models <b>{models.totalCount ?? '—'}</b>
          </span>
          <span className="stat-chip">
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
