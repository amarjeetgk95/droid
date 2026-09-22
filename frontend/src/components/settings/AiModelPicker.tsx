'use client';

/* OpenRouter model picker + live test for Settings > AI Providers.
   Dropdown is fed by GET /api/v1/ai/models (free first, paid badged);
   Test runs POST /api/v1/ai/test against the selected model and shows
   PASS/FAIL + latency inline. No timers, no polling — fetch on mount only. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { copilotErrorHint, normalizeModelOptions, sortModelOptions, type ModelOption } from '@/lib/copilot';
import { errorMessage } from '@/lib/errors';

export interface ModelPick {
  model: string;
  /** null when 'auto' or catalog unavailable (free/paid unknown). */
  isFree: boolean | null;
}

interface TestOutcome {
  success: boolean;
  provider: string;
  model: string | null;
  latencyMs: number | null;
  detail: string | null;
}

export function AiModelPicker({
  apiKey,
  selectedModel,
  allowPaid,
  onPick,
}: {
  /** Current OpenRouter key field value (may be '' meaning "keep existing"). */
  apiKey: string;
  /** Effective selection: 'auto' or a model id. */
  selectedModel: string;
  allowPaid: boolean;
  onPick: (pick: ModelPick) => void;
}) {
  const [options, setOptions] = useState<ModelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [outcome, setOutcome] = useState<TestOutcome | null>(null);
  const requestIdRef = useRef(0);

  const load = useCallback(async (refresh: boolean) => {
    const requestId = ++requestIdRef.current;
    if (refresh) setRefreshing(true);
    else setLoading(true);
    try {
      const result = refresh ? await api.refreshAIModels() : await api.getAIModels({ free_only: false, pricing: 'ALL' });
      if (requestIdRef.current !== requestId) return;
      const data = (result as { data?: { models?: unknown } }).data;
      setOptions(sortModelOptions(normalizeModelOptions(data?.models)));
      setLoadError(null);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setOptions([]);
      setLoadError(errorMessage(err, 'Model catalog unavailable'));
    } finally {
      if (requestIdRef.current === requestId) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const handleSelect = useCallback(
    (id: string) => {
      if (id === 'auto') {
        onPick({ model: 'auto', isFree: null });
        return;
      }
      const found = options.find((o) => o.id === id);
      onPick({ model: id, isFree: found ? found.isFree : null });
    },
    [onPick, options],
  );

  const handleTest = useCallback(async () => {
    const model = (selectedModel || 'auto').trim() || 'auto';
    setTesting(true);
    setOutcome(null);
    try {
      const result = await api.testAi({
        provider: 'openrouter',
        symbol: 'NIFTY',
        model,
        openRouterApiKey: apiKey.trim() ? apiKey.trim() : undefined,
        openRouterModel: model,
        allow_paid: allowPaid,
      } as Parameters<typeof api.testAi>[0]);
      const data = (result as { data?: Record<string, unknown> }).data ?? {};
      const success = data.success === true;
      const rawDetail =
        typeof data.error === 'string' && data.error
          ? data.error
          : typeof data.hint === 'string' && data.hint
            ? data.hint
            : null;
      setOutcome({
        success,
        provider: typeof data.provider === 'string' ? data.provider : 'openrouter',
        model: typeof data.model === 'string' ? data.model : model,
        latencyMs: typeof data.latency_ms === 'number' ? data.latency_ms : null,
        detail: success ? null : rawDetail ? copilotErrorHint(rawDetail).hint : 'Backend check failed.',
      });
    } catch (err) {
      setOutcome({
        success: false,
        provider: 'openrouter',
        model,
        latencyMs: null,
        detail: errorMessage(err, 'Backend check failed'),
      });
    } finally {
      setTesting(false);
    }
  }, [allowPaid, apiKey, selectedModel]);

  const current = (selectedModel || 'auto').trim() || 'auto';
  const knownIds = new Set(options.map((o) => o.id));
  const showCustom = current !== 'auto' && !knownIds.has(current);
  const freeCount = options.filter((o) => o.isFree).length;

  return (
    <div className="flex flex-col gap-2">
      <label className="field">
        <span className="field-l">OpenRouter model</span>
        <select
          className="input"
          value={showCustom ? '__custom__' : current}
          disabled={loading || refreshing}
          onChange={(e) => {
            if (e.target.value !== '__custom__') handleSelect(e.target.value);
          }}
          title="Live catalog from GET /api/v1/ai/models — free models first"
        >
          <option value="auto">auto — best free for trading</option>
          {options.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
              {m.isFree ? ' (free)' : ' (paid)'}
            </option>
          ))}
          {showCustom ? <option value="__custom__">{current} (custom)</option> : null}
        </select>
        <span className="text-[11px] text-ink-2">
          {loading ? (
            'Loading live catalog…'
          ) : loadError ? (
            <>Catalog offline — type any model id, or retry.</>
          ) : (
            <>
              {options.length} models ({freeCount} free)
              {!allowPaid ? ' · paid hidden from routing until Allow paid is on' : ''}
            </>
          )}
        </span>
      </label>
      {loadError ? (
        <div className="ds-filters">
          <p className="sg-err">{loadError}</p>
          <button type="button" className="btn" disabled={refreshing} onClick={() => void load(true)}>
            {refreshing ? 'Refreshing…' : 'Retry'}
          </button>
        </div>
      ) : null}

      <div className="ds-filters">
        <button
          type="button"
          className="btn btn-primary"
          disabled={testing}
          onClick={() => void handleTest()}
          title="POST /api/v1/ai/test against the selected model"
        >
          {testing ? 'Testing… (up to 180s)' : 'Test selected model'}
        </button>
        <button type="button" className="btn" disabled={refreshing || loading} onClick={() => void load(true)}>
          {refreshing ? 'Refreshing…' : 'Refresh models'}
        </button>
        {outcome ? (
          <span className="stat-chips">
            <span className="stat-chip">
              <b>{outcome.success ? 'PASS' : 'FAIL'}</b>
            </span>
            <span className="stat-chip">
              {outcome.provider}
              {outcome.model ? ` · ${outcome.model}` : ''}
              {outcome.latencyMs !== null ? ` · ${outcome.latencyMs}ms` : ''}
            </span>
          </span>
        ) : null}
      </div>
      {outcome?.detail ? <p className={outcome.success ? 'sg-note' : 'sg-err'}>{outcome.detail}</p> : null}
    </div>
  );
}
