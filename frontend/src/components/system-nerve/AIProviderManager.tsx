'use client';

import React, { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import { Card } from '../shared/Card';
import { Badge, type BadgeVariant } from '../shared/Badge';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import {
  PanelFreshness,
  PanelStateBanner,
  asString,
  toErrorMessage,
  usePanelResource,
} from './PanelState';

const POLL_MS = 15_000;

interface AiModel {
  key: string;
  provider: string;
  modelId: string;
  modelVersion: string;
  promptVersion: string;
  status: string;
  isLastKnownGood: boolean;
  canaryPct: string | null;
}

interface AiModelsSnapshot {
  models: AiModel[];
  timestamp: string | null;
}

interface Outcome {
  ok: boolean;
  text: string;
  at: number;
}

function normalizeModel(row: Record<string, unknown>): AiModel {
  return {
    key: asString(row.key) ?? 'unknown',
    provider: asString(row.provider) ?? 'unknown provider',
    modelId: asString(row.model_id) ?? asString(row.key) ?? 'unknown model',
    modelVersion: asString(row.model_version) ?? '—',
    promptVersion: asString(row.prompt_version) ?? '—',
    status: asString(row.status) ?? 'UNKNOWN',
    isLastKnownGood: row.is_last_known_good === true,
    canaryPct: asString(row.canary_pct),
  };
}

async function fetchAiModels(): Promise<AiModelsSnapshot> {
  const res = await api.request<{
    data: Record<string, unknown>[];
    error: string | null;
    meta?: { timestamp?: string };
  }>('/api/v1/algo/ai-models');
  if (res.error) throw new Error(res.error);
  const rows = Array.isArray(res.data) ? res.data : [];
  return {
    models: rows.map(normalizeModel),
    timestamp: asString(res.meta?.timestamp),
  };
}

function statusVariant(status: string): BadgeVariant {
  switch (status.toUpperCase()) {
    case 'CURRENT':
      return 'success';
    case 'CANARY':
      return 'info';
    case 'SHADOW':
      return 'purple';
    case 'CANDIDATE':
    case 'ROLLED_BACK':
      return 'warning';
    default:
      return 'neutral';
  }
}

export const AIProviderManager: React.FC = () => {
  const resource = usePanelResource(fetchAiModels, POLL_MS, (snap) => snap.timestamp);
  const models = resource.data?.models ?? null;

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<Outcome | null>(null);
  const [rollbackTarget, setRollbackTarget] = useState<AiModel | null>(null);
  const [rollbackBusy, setRollbackBusy] = useState(false);
  const [rollbackOutcome, setRollbackOutcome] = useState<Outcome | null>(null);

  const handleTestProvider = useCallback(async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await api.testAi();
      if (res.error) throw new Error(res.error);
      const data = res.data;
      if (!data) throw new Error('AI test returned no result payload.');
      if (data.success) {
        const bits = [
          data.provider,
          data.model ?? null,
          data.latency_ms != null ? `${data.latency_ms} ms` : null,
          data.schema_valid === true
            ? 'schema valid'
            : data.schema_valid === false
              ? 'schema invalid'
              : 'schema not reported',
        ].filter((bit): bit is string => bit !== null && bit !== '');
        setTestResult({
          ok: true,
          text: `Provider responded — ${bits.join(' · ')}`,
          at: Date.now(),
        });
      } else {
        setTestResult({
          ok: false,
          text: `Provider test failed — ${data.error ?? 'no error detail'}${
            data.hint ? ` (hint: ${data.hint})` : ''
          }`,
          at: Date.now(),
        });
      }
    } catch (err) {
      setTestResult({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setTesting(false);
    }
  }, []);

  const handleRollback = useCallback(async () => {
    if (!rollbackTarget) return;
    const key = rollbackTarget.key;
    setRollbackBusy(true);
    try {
      const res = await api.rollbackAlgoAiModel(key);
      const data = res.data ?? {};
      const restored = asString(data.restored);
      const rolledBack = asString(data.rolled_back) ?? key;
      setRollbackOutcome({
        ok: true,
        text: `Rollback recorded for ${rolledBack}${
          restored
            ? `; last-known-good restored: ${restored}`
            : '; no last-known-good model was available to restore'
        }.`,
        at: Date.now(),
      });
      resource.refresh();
    } catch (err) {
      setRollbackOutcome({ ok: false, text: toErrorMessage(err), at: Date.now() });
    } finally {
      setRollbackBusy(false);
      setRollbackTarget(null);
    }
  }, [resource, rollbackTarget]);

  return (
    <Card
      title="AI Provider Governance"
      subtitle="Registered provider models, canary posture and inference verification"
      headerAction={
        <button
          type="button"
          className="btn"
          onClick={handleTestProvider}
          disabled={testing}
          aria-label="Test AI provider inference"
        >
          {testing ? 'Testing…' : 'Test AI Inference'}
        </button>
      }
      footer={
        <PanelFreshness
          error={resource.error}
          hasData={resource.data !== null}
          updatedAt={resource.updatedAt}
          generatedAt={resource.generatedAt}
          intervalMs={POLL_MS}
        />
      }
    >
      <div className="space-y-4 font-mono text-xs">
        <PanelStateBanner
          label="AI model registry"
          error={resource.error}
          hasData={resource.data !== null}
          updatedAt={resource.updatedAt}
          onRetry={resource.refresh}
        />

        {testResult ? (
          <div
            className={`notice ${testResult.ok ? 'notice--up' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {testResult.ok ? 'Inference verified' : 'Inference test failed'}
              </strong>{' '}
              — {testResult.text}
            </span>
          </div>
        ) : null}

        {rollbackOutcome ? (
          <div
            className={`notice ${rollbackOutcome.ok ? 'notice--warn' : 'notice--down'}`}
            role="status"
            aria-live="polite"
          >
            <span>
              <strong className="font-semibold">
                {rollbackOutcome.ok ? 'Model rollback applied' : 'Model rollback failed'}
              </strong>{' '}
              — {rollbackOutcome.text}
            </span>
          </div>
        ) : null}

        {models === null ? null : models.length === 0 ? (
          <div className="notice notice--info">
            <span>No AI models are registered in governance on this backend.</span>
          </div>
        ) : (
          <div className="space-y-2">
            {models.map((model) => (
              <div
                key={model.key}
                className="p-3 rounded-md bg-card border border-border flex flex-wrap items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <div className="font-bold text-ink flex items-center gap-2 flex-wrap">
                    <span>{model.modelId}</span>
                    <Badge variant={statusVariant(model.status)} size="xs">
                      {model.status}
                    </Badge>
                    {model.isLastKnownGood ? (
                      <Badge variant="outline" size="xs">
                        LKG
                      </Badge>
                    ) : null}
                  </div>
                  <div className="text-[11px] text-ink-3 mt-0.5 break-words">
                    {model.provider} · model {model.modelVersion} · prompt {model.promptVersion}
                    {model.canaryPct !== null ? ` · canary ${model.canaryPct}%` : ''}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setRollbackTarget(model)}
                  disabled={rollbackBusy}
                  aria-label={`Rollback ${model.modelId} to last known good`}
                  className="btn"
                >
                  Rollback
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="text-[10px] text-ink-3">
          Rollback restores the last-known-good model registered in AI governance. Model latency is
          not stored by the registry — run Test AI Inference for a measured round trip.
        </div>
      </div>

      <ConfirmDialog
        isOpen={rollbackTarget !== null}
        onClose={() => setRollbackTarget(null)}
        onConfirm={handleRollback}
        title={`Roll back ${rollbackTarget?.modelId ?? 'AI model'}`}
        message={
          <span>
            This marks <strong>{rollbackTarget?.key ?? 'the model'}</strong> as ROLLED_BACK and
            restores the registered last-known-good model for routing. Confirm this is intended
            before continuing.
          </span>
        }
        confirmLabel="Roll back model"
        destructive
      />
    </Card>
  );
};
