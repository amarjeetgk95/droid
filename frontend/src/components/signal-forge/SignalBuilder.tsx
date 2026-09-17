'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import {
  classifyDirection,
  type AutoDetectCandidate,
  type SignalEngineStrategy,
} from '@/lib/api/signals';
import { AutoDetectButton } from './AutoDetectButton';
import {
  EMPTY_LEVELS,
  candidateToLevelDrafts,
  directionToLong,
  errorMessage,
  finiteNumber,
  normalizeStrategyOptions,
  validateForgeLevels,
  validateLots,
  type LevelDraft,
  type LevelKey,
} from './forgeLogic';

interface SignalBuilderProps {
  underlying: string;
  onSignalGenerated?: (sig: unknown) => void;
  onFormChange?: (formData: Record<string, unknown>) => void;
  onCandidate?: (candidate: AutoDetectCandidate | null, detected: boolean) => void;
}

const LEVEL_PAYLOAD_KEY: Record<LevelKey, 'trigger' | 'stop_loss' | 'target_1' | 'target_2'> = {
  trigger: 'trigger',
  stopLoss: 'stop_loss',
  target1: 'target_1',
  target2: 'target_2',
};

const LEVEL_LABEL: Record<LevelKey, string> = {
  trigger: 'TRIGGER ENTRY (₹)',
  stopLoss: 'STOP LOSS (₹)',
  target1: 'TARGET 1 (₹)',
  target2: 'TARGET 2 (₹)',
};

type Outcome = {
  ok: boolean;
  message: string;
  signalId?: string;
  fsmState?: string;
  telegram?: string;
  paper?: string;
  deduplicated?: boolean;
};

function createIdempotencyKey(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through to the non-crypto fallback
  }
  return `sf-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export const SignalBuilder: React.FC<SignalBuilderProps> = ({
  underlying,
  onSignalGenerated,
  onFormChange,
  onCandidate,
}) => {
  const [direction, setDirection] = useState<'CALL' | 'PUT'>('CALL');
  const [strategy, setStrategy] = useState('');
  const [timeframe, setTimeframe] = useState('5m');
  const [levels, setLevels] = useState<LevelDraft>(EMPTY_LEVELS);
  const [lots, setLots] = useState('1');
  const [notifyTelegram, setNotifyTelegram] = useState(true);
  const [engines, setEngines] = useState<SignalEngineStrategy[]>([]);
  const [enginesStatus, setEnginesStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [enginesError, setEnginesError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<LevelKey | 'lots', string>>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [autoStatus, setAutoStatus] = useState<{
    kind: 'detected' | 'baseline' | 'error';
    message: string;
  } | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  const submitLockRef = useRef(false);
  const idempotencyKeyRef = useRef<string | null>(null);

  // Latest form snapshot for parent notifications without re-creating callbacks.
  const formRef = useRef<Record<string, unknown>>({});
  formRef.current = {
    underlying,
    direction,
    strategy,
    timeframe,
    trigger: finiteNumber(levels.trigger) ?? levels.trigger,
    stop_loss: finiteNumber(levels.stopLoss) ?? levels.stopLoss,
    target_1: finiteNumber(levels.target1) ?? levels.target1,
    target_2: finiteNumber(levels.target2) ?? levels.target2,
    lots: finiteNumber(lots) ?? lots,
    notify_telegram: notifyTelegram,
  };

  const emitChange = useCallback(
    (patch?: Record<string, unknown>) => {
      if (onFormChange) onFormChange({ ...formRef.current, ...patch });
    },
    [onFormChange],
  );

  /** Any edit invalidates the previous outcome and confirmation. */
  const markDirty = useCallback(() => {
    setOutcome(null);
    setConfirmOpen(false);
    setFieldErrors({});
    setFormError(null);
    idempotencyKeyRef.current = null;
  }, []);

  // Engine registry is the only source of valid strategy ids. An unavailable
  // registry blocks submit instead of falling back to a hardcoded name.
  useEffect(() => {
    let cancelled = false;
    setEnginesStatus('loading');
    void (async () => {
      try {
        const res = await api.getSignalEngines();
        const list = normalizeStrategyOptions(res?.strategies);
        if (cancelled) return;
        setEngines(list);
        if (list.length === 0) {
          setEnginesError('Engine registry returned no strategies.');
          setEnginesStatus('error');
        } else {
          setEnginesError(null);
          setEnginesStatus('ready');
        }
      } catch (e) {
        if (cancelled) return;
        setEngines([]);
        setEnginesError(errorMessage(e, 'Engine registry unavailable.'));
        setEnginesStatus('error');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Adopt the first real engine when the current selection is not in the registry.
  useEffect(() => {
    if (enginesStatus !== 'ready' || engines.length === 0) return;
    if (engines.some((e) => e.id === strategy)) return;
    const next = engines[0].id;
    setStrategy(next);
    emitChange({ strategy: next });
  }, [engines, enginesStatus, strategy, emitChange]);

  const updateLevel = (key: LevelKey, value: string) => {
    markDirty();
    setLevels((prev) => ({ ...prev, [key]: value }));
    emitChange({ [LEVEL_PAYLOAD_KEY[key]]: finiteNumber(value) ?? value });
  };

  const handleAutoDetected = (candidate: AutoDetectCandidate, detected: boolean, message: string) => {
    markDirty();
    const mapped = candidateToLevelDrafts(candidate, underlying);
    const dirToken = typeof candidate.direction === 'string' ? candidate.direction : '';
    const nextDirection: 'CALL' | 'PUT' = dirToken
      ? classifyDirection(dirToken) === 'PUT'
        ? 'PUT'
        : 'CALL'
      : direction;
    const nextLevels: LevelDraft = { ...levels };
    for (const key of Object.keys(mapped.drafts) as LevelKey[]) {
      const draft = mapped.drafts[key];
      if (draft !== undefined) nextLevels[key] = draft;
    }
    setDirection(nextDirection);
    setLevels(nextLevels);
    onCandidate?.(candidate, detected);
    const patch: Record<string, unknown> = {
      direction: nextDirection,
      trigger: finiteNumber(nextLevels.trigger) ?? nextLevels.trigger,
      stop_loss: finiteNumber(nextLevels.stopLoss) ?? nextLevels.stopLoss,
      target_1: finiteNumber(nextLevels.target1) ?? nextLevels.target1,
      target_2: finiteNumber(nextLevels.target2) ?? nextLevels.target2,
    };
    emitChange(patch);
    if (mapped.applied.length === 0) {
      setAutoStatus({
        kind: 'error',
        message: `Auto-detect returned no usable levels — inputs left unchanged. ${mapped.skipped.join('; ')}`,
      });
      return;
    }
    const base = message?.trim() || (detected ? `Candidate detected on ${underlying}.` : `No active setup on ${underlying} — baseline levels from live spot.`);
    const skippedNote = mapped.skipped.length > 0 ? ` Not applied: ${mapped.skipped.join('; ')}.` : '';
    setAutoStatus({ kind: detected ? 'detected' : 'baseline', message: `${base}${skippedNote}` });
  };

  const handleAutoUnavailable = (message: string) => {
    const detail = message.replace(/\.\s*$/, '');
    setAutoStatus({ kind: 'error', message: `Auto-detect unavailable — ${detail}. Inputs left unchanged.` });
  };

  const prepare = (): Record<string, unknown> | null => {
    const levelCheck = validateForgeLevels({
      underlying,
      direction,
      trigger: levels.trigger,
      stopLoss: levels.stopLoss,
      target1: levels.target1,
      target2: levels.target2,
    });
    const lotsError = validateLots(lots);
    const strategyValid = engines.some((e) => e.id === strategy);
    const errors: Partial<Record<LevelKey | 'lots', string>> = { ...levelCheck.errors };
    if (lotsError) errors.lots = lotsError;
    if (!levelCheck.ok || lotsError || !strategyValid) {
      setFieldErrors(errors);
      const reason = !strategyValid
        ? enginesError ?? 'Select a strategy from the engine registry.'
        : levelCheck.reason ?? (lotsError ? `Lots: ${lotsError}` : 'Fix the invalid fields before generating.');
      setFormError(reason);
      return null;
    }
    setFieldErrors({});
    setFormError(null);
    return {
      underlying,
      direction: directionToLong(direction),
      strategy,
      timeframe,
      trigger_level: finiteNumber(levels.trigger),
      stop_loss: finiteNumber(levels.stopLoss),
      target_1: finiteNumber(levels.target1),
      target_2: finiteNumber(levels.target2),
      lots: finiteNumber(lots),
      notify_telegram: notifyTelegram,
    };
  };

  const handleReview = (e: React.FormEvent) => {
    e.preventDefault();
    if (generating) return;
    const payload = prepare();
    if (!payload) return;
    markDirty();
    setConfirmOpen(true);
  };

  const handleConfirm = async () => {
    if (submitLockRef.current || generating) return;
    const payload = prepare();
    if (!payload) return;
    submitLockRef.current = true;
    setGenerating(true);
    try {
      // Stable key across retries of the same payload: the backend returns the
      // original signal instead of registering a duplicate.
      if (!idempotencyKeyRef.current) idempotencyKeyRef.current = createIdempotencyKey();
      const idempotencyKey = idempotencyKeyRef.current;
      const res = await api.generateSignal(
        { ...payload, idempotency_key: idempotencyKey },
        { idempotencyKey },
      );
      const signal = (res?.signal ?? null) as Record<string, unknown> | null;
      const signalId =
        signal && typeof signal.signal_id === 'string' && signal.signal_id ? signal.signal_id : 'unknown';
      const fsmState = signal && typeof signal.fsm_state === 'string' ? signal.fsm_state : undefined;
      const telegramEnqueued =
        typeof res?.telegram?.enqueued === 'number' ? res.telegram.enqueued : null;
      const telegramStatus =
        res?.telegram?.status ??
        (telegramEnqueued !== null ? `enqueued ${telegramEnqueued}` : 'unknown');
      setOutcome({
        ok: true,
        signalId,
        fsmState,
        telegram: `${telegramStatus}${telegramEnqueued !== null ? ` (${telegramEnqueued})` : ''}`,
        paper: res?.paper_status,
        deduplicated: res?.deduplicated === true,
        message: res?.deduplicated
          ? 'Retry deduplicated by the backend — original signal returned.'
          : 'Signal generated and registered.',
      });
      setConfirmOpen(false);
      idempotencyKeyRef.current = null;
      onSignalGenerated?.(res?.signal);
    } catch (e) {
      // Keep the confirm step open: a retry must reuse the same idempotency
      // key rather than registering a second signal.
      setOutcome({ ok: false, message: errorMessage(e, 'Signal generation failed.') });
    } finally {
      submitLockRef.current = false;
      setGenerating(false);
    }
  };

  const strategyLabel =
    engines.find((e) => e.id === strategy)?.label ?? strategy ?? '';
  const canSubmitLevels = Object.keys(fieldErrors).length === 0;

  return (
    <form
      onSubmit={handleReview}
      className="p-4 rounded-lg border border-border bg-surface shadow-xs space-y-4 font-mono text-xs"
    >
      <div className="flex items-center justify-between gap-3 border-b border-border-subtle pb-3">
        <div>
          <div className="text-sm font-bold text-ink">SIGNAL BUILDER &amp; FORGE</div>
          <div className="text-[11px] text-ink-3 font-sans">Authoritative signal generator</div>
        </div>
        <AutoDetectButton
          underlying={underlying}
          strategy={strategy || undefined}
          timeframe={timeframe}
          onDetected={handleAutoDetected}
          onUnavailable={handleAutoUnavailable}
        />
      </div>

      {autoStatus ? (
        <div
          role="status"
          aria-live="polite"
          className={`p-2.5 rounded border text-[11px] leading-relaxed ${
            autoStatus.kind === 'detected'
              ? 'bg-up-wash border-up-line text-up-strong'
              : autoStatus.kind === 'baseline'
                ? 'bg-accent-wash border-accent-line text-primary'
                : 'bg-warn-wash border-warn-line text-warn-ink'
          }`}
        >
          <span className="font-bold">
            {autoStatus.kind === 'detected'
              ? 'SETUP DETECTED'
              : autoStatus.kind === 'baseline'
                ? 'BASELINE FROM LIVE SPOT'
                : 'NOT APPLIED'}
          </span>
          {' — '}
          {autoStatus.message}
        </div>
      ) : null}

      {/* Direction & Strategy Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div role="group" aria-labelledby="forge-direction-label">
          <span id="forge-direction-label" className="text-ink-2 block mb-1">
            DIRECTION
          </span>
          <div className="flex rounded-lg overflow-hidden border border-border bg-muted p-0.5">
            <button
              type="button"
              aria-pressed={direction === 'CALL'}
              onClick={() => {
                markDirty();
                setDirection('CALL');
                emitChange({ direction: 'CALL' });
              }}
              className={`flex-1 py-1.5 font-bold text-center rounded transition-all ${
                direction === 'CALL' ? 'bg-up text-white shadow-sm' : 'text-ink-2 hover:text-ink'
              }`}
            >
              LONG CALL (BULL)
            </button>
            <button
              type="button"
              aria-pressed={direction === 'PUT'}
              onClick={() => {
                markDirty();
                setDirection('PUT');
                emitChange({ direction: 'PUT' });
              }}
              className={`flex-1 py-1.5 font-bold text-center rounded transition-all ${
                direction === 'PUT' ? 'bg-down text-white shadow-sm' : 'text-ink-2 hover:text-ink'
              }`}
            >
              LONG PUT (BEAR)
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="forge-strategy" className="text-ink-2 block mb-1">
            STRATEGY
          </label>
          <select
            id="forge-strategy"
            value={strategy}
            disabled={enginesStatus !== 'ready' || engines.length === 0}
            aria-invalid={enginesStatus === 'error' || undefined}
            aria-describedby="forge-strategy-status"
            onChange={(e) => {
              markDirty();
              setStrategy(e.target.value);
              emitChange({ strategy: e.target.value });
            }}
            className="w-full px-3 py-2 bg-surface border border-border rounded-md text-ink focus:outline-none focus:border-primary disabled:opacity-60"
          >
            {enginesStatus === 'loading' ? <option value="">Loading engine registry…</option> : null}
            {enginesStatus === 'ready' && engines.length === 0 ? (
              <option value="">No strategies available</option>
            ) : null}
            {enginesStatus === 'error' && engines.length === 0 ? (
              <option value="">Engine registry unavailable</option>
            ) : null}
            {engines.map((engine) => (
              <option key={engine.id} value={engine.id}>
                {engine.label ?? engine.id}
              </option>
            ))}
          </select>
          <div id="forge-strategy-status" className="text-[10px] mt-1 leading-relaxed">
            {enginesStatus === 'loading' ? (
              <span className="text-ink-3">Loading the engine registry…</span>
            ) : enginesStatus === 'error' ? (
              <span role="alert" className="text-warn-ink">
                Strategy registry unavailable — {enginesError} Generation is blocked.
              </span>
            ) : strategyLabel ? (
              <span className="text-ink-3">Engine: {strategyLabel}</span>
            ) : null}
          </div>
        </div>

        <div>
          <label htmlFor="forge-timeframe" className="text-ink-2 block mb-1">
            TIMEFRAME
          </label>
          <select
            id="forge-timeframe"
            value={timeframe}
            onChange={(e) => {
              markDirty();
              setTimeframe(e.target.value);
              emitChange({ timeframe: e.target.value });
            }}
            className="w-full px-3 py-2 bg-surface border border-border rounded-md text-ink focus:outline-none focus:border-primary"
          >
            <option value="1m">1m (Scalp)</option>
            <option value="3m">3m (Fast)</option>
            <option value="5m">5m (Primary Intraday)</option>
            <option value="15m">15m (Anchor)</option>
          </select>
        </div>
      </div>

      {/* Levels Matrix (Trigger, SL, T1, T2) */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
        {(Object.keys(LEVEL_LABEL) as LevelKey[]).map((key) => {
          const inputId = `forge-level-${key}`;
          const errorId = `${inputId}-error`;
          const tone =
            key === 'trigger'
              ? 'text-primary'
              : key === 'stopLoss'
                ? 'text-down-strong'
                : 'text-up-strong';
          return (
            <div key={key}>
              <label htmlFor={inputId} className="text-ink-2 block mb-1">
                {LEVEL_LABEL[key]}
              </label>
              <input
                id={inputId}
                type="number"
                inputMode="decimal"
                step="0.05"
                value={levels[key]}
                placeholder="—"
                aria-invalid={fieldErrors[key] ? true : undefined}
                aria-describedby={fieldErrors[key] ? errorId : undefined}
                onChange={(e) => updateLevel(key, e.target.value)}
                className={`w-full px-3 py-2 bg-surface border rounded-md font-bold focus:outline-none ${tone} ${
                  fieldErrors[key] ? 'border-down-line' : 'border-border focus:border-primary'
                }`}
              />
              {fieldErrors[key] ? (
                <span id={errorId} role="alert" className="text-[10px] text-down-strong block mt-1">
                  {fieldErrors[key]}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Level coherence + validation errors */}
      {formError ? (
        <div
          role="alert"
          className="p-2.5 rounded bg-down-wash border border-down-line text-down-strong text-[11px] flex items-start gap-2"
        >
          <span aria-hidden="true">!</span>
          <span>{formError}</span>
        </div>
      ) : null}

      {/* Sizing */}
      <div className="grid grid-cols-2 gap-3 pt-2">
        <div>
          <label htmlFor="forge-lots" className="text-ink-2 block mb-1">
            POSITION LOTS
          </label>
          <input
            id="forge-lots"
            type="number"
            inputMode="numeric"
            min={1}
            max={50}
            value={lots}
            aria-invalid={fieldErrors.lots ? true : undefined}
            aria-describedby={fieldErrors.lots ? 'forge-lots-error' : undefined}
            onChange={(e) => {
              markDirty();
              setLots(e.target.value);
              emitChange({ lots: finiteNumber(e.target.value) ?? e.target.value });
            }}
            className={`w-full px-3 py-2 bg-surface border rounded-md text-ink focus:outline-none ${
              fieldErrors.lots ? 'border-down-line' : 'border-border focus:border-primary'
            }`}
          />
          {fieldErrors.lots ? (
            <span id="forge-lots-error" role="alert" className="text-[10px] text-down-strong block mt-1">
              {fieldErrors.lots}
            </span>
          ) : null}
        </div>

        <div className="flex items-end pb-1">
          <label htmlFor="forge-notify" className="flex items-center gap-2 text-ink-2 cursor-pointer">
            <input
              id="forge-notify"
              type="checkbox"
              checked={notifyTelegram}
              onChange={(e) => {
                markDirty();
                setNotifyTelegram(e.target.checked);
                emitChange({ notify_telegram: e.target.checked });
              }}
              className="accent-primary"
            />
            <span>TELEGRAM ALERT ON PUBLISH</span>
          </label>
        </div>
      </div>

      {/* Confirmation step — exact payload + Telegram toggle */}
      {confirmOpen ? (
        <div className="p-3 rounded border border-accent-line bg-accent-wash space-y-2">
          <div className="font-bold text-primary">CONFIRM &amp; ARM — REVIEW EXACT PAYLOAD</div>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-ink-2">
            <dt className="text-ink-3">Underlying</dt>
            <dd className="text-ink font-bold">{underlying}</dd>
            <dt className="text-ink-3">Direction</dt>
            <dd className="text-ink font-bold">{directionToLong(direction)}</dd>
            <dt className="text-ink-3">Strategy</dt>
            <dd className="text-ink font-bold">{strategy}</dd>
            <dt className="text-ink-3">Timeframe</dt>
            <dd className="text-ink font-bold">{timeframe}</dd>
            <dt className="text-ink-3">Trigger level</dt>
            <dd className="text-ink font-bold">{levels.trigger}</dd>
            <dt className="text-ink-3">Stop loss</dt>
            <dd className="text-ink font-bold">{levels.stopLoss}</dd>
            <dt className="text-ink-3">Target 1</dt>
            <dd className="text-ink font-bold">{levels.target1}</dd>
            <dt className="text-ink-3">Target 2</dt>
            <dd className="text-ink font-bold">{levels.target2}</dd>
            <dt className="text-ink-3">Lots</dt>
            <dd className="text-ink font-bold">{lots}</dd>
          </dl>
          <label htmlFor="forge-confirm-notify" className="flex items-center gap-2 text-ink-2 cursor-pointer">
            <input
              id="forge-confirm-notify"
              type="checkbox"
              checked={notifyTelegram}
              onChange={(e) => setNotifyTelegram(e.target.checked)}
              className="accent-primary"
            />
            <span>
              Send Telegram alert (`notify_telegram: {String(notifyTelegram)}`)
            </span>
          </label>
          <div className="text-[10px] text-ink-3 leading-relaxed">
            Registers ARMED in the FSM. Paper execution is not requested by this form. Retries reuse an
            idempotency key so a network retry cannot duplicate the signal.
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={generating}
              className="flex-1 py-2 px-3 rounded-md bg-primary hover:bg-accent-strong disabled:opacity-40 disabled:cursor-not-allowed text-white font-bold tracking-wider"
            >
              {generating ? 'CREATING & ARMING…' : 'CONFIRM & ARM SIGNAL'}
            </button>
            <button
              type="button"
              onClick={() => setConfirmOpen(false)}
              disabled={generating}
              className="px-3 py-2 rounded-md border border-border bg-surface text-ink-2 hover:text-ink disabled:opacity-40"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {/* Visible outcome — success or failure */}
      {outcome ? (
        <div
          role={outcome.ok ? 'status' : 'alert'}
          aria-live="polite"
          className={`p-3 rounded border text-xs leading-relaxed ${
            outcome.ok
              ? 'bg-up-wash border-up-line text-up-strong'
              : 'bg-down-wash border-down-line text-down-strong'
          }`}
        >
          <div className="font-bold">
            {outcome.ok
              ? `SIGNAL ${outcome.signalId}${outcome.fsmState ? ` · ${outcome.fsmState}` : ''}`
              : 'GENERATION FAILED'}
          </div>
          <div>{outcome.message}</div>
          {outcome.ok ? (
            <div className="text-[11px] mt-1">
              Telegram: {outcome.telegram}
              {outcome.paper ? ` · Paper: ${outcome.paper}` : ''}
            </div>
          ) : null}
        </div>
      ) : null}

      {!confirmOpen ? (
        <button
          type="submit"
          disabled={generating || !canSubmitLevels}
          className="w-full py-3 px-4 rounded-lg bg-primary hover:bg-accent-strong disabled:opacity-40 disabled:cursor-not-allowed text-white font-mono font-bold text-sm tracking-wider shadow-sm transition-all"
        >
          REVIEW &amp; GENERATE SIGNAL →
        </button>
      ) : null}
    </form>
  );
};
