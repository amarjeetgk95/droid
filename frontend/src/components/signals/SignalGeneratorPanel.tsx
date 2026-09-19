'use client';

import { useCallback, useMemo, useState } from 'react';
import { Sparkles, Wand2 } from 'lucide-react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { useInstrument } from '@/context/InstrumentContext';
import { useToast } from '@/components/ui/toast';
import type { DeskActionResult, GenerateSignalInput, SignalDeskState } from '@/hooks/useSignalDesk';
import type { DeskScope } from '@/lib/signalsNormalize';

const TIMEFRAMES = ['1M', '3M', '5M', '15M', '1H'] as const;

function toNumber(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function SignalGeneratorPanel({ desk }: { desk: SignalDeskState }) {
  const { instrument } = useInstrument();
  const { push } = useToast();

  const [deskScope, setDeskScope] = useState<DeskScope>('INTRADAY');
  const [strategy, setStrategy] = useState('');
  const [direction, setDirection] = useState<'BULLISH' | 'BEARISH'>('BULLISH');
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>('5M');
  const [confidence, setConfidence] = useState('80');
  const [trigger, setTrigger] = useState('');
  const [stopLoss, setStopLoss] = useState('');
  const [target1, setTarget1] = useState('');
  const [target2, setTarget2] = useState('');
  const [notifyTelegram, setNotifyTelegram] = useState(true);
  const [allowClosedMarket, setAllowClosedMarket] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [feedNote, setFeedNote] = useState<string | null>(null);

  const strategyOptions = useMemo(() => {
    const entries = desk.engines.length > 0 ? desk.engines : ['BREAKOUT', 'MOMENTUM', 'MEAN_REVERSION'];
    if (strategy && !entries.includes(strategy)) return [strategy, ...entries];
    return entries;
  }, [desk.engines, strategy]);

  const effectiveStrategy = strategy || strategyOptions[0] || 'BREAKOUT';

  const buildPayload = useCallback(
    (): GenerateSignalInput => ({
      underlying: instrument,
      strategy: effectiveStrategy,
      direction,
      timeframe,
      desk: deskScope,
      confidence: toNumber(confidence) ?? 80,
      trigger: toNumber(trigger),
      stop_loss: toNumber(stopLoss),
      target_1: toNumber(target1),
      target_2: toNumber(target2),
      notifyTelegram,
      allowClosedMarket,
      confirm: allowClosedMarket,
    }),
    [
      allowClosedMarket,
      confidence,
      deskScope,
      direction,
      effectiveStrategy,
      instrument,
      notifyTelegram,
      stopLoss,
      target1,
      target2,
      timeframe,
      trigger,
    ],
  );

  const handleAutoDetect = useCallback(async () => {
    setDetecting(true);
    setFeedNote(null);
    try {
      const candidate = await desk.autoDetect({
        underlying: instrument,
        strategy: effectiveStrategy,
        timeframe,
      });
      if (!candidate) {
        setFeedNote('No setup detected for this instrument and timeframe.');
        return;
      }
      const candidateDirection = String(candidate.direction ?? '').toUpperCase();
      if (candidateDirection.includes('BEAR')) setDirection('BEARISH');
      else if (candidateDirection.includes('BULL')) setDirection('BULLISH');
      const nextTrigger = candidate.trigger_level ?? candidate.trigger;
      const nextStop = candidate.stop_loss;
      const nextTarget1 = candidate.target_1;
      const nextTarget2 = candidate.target_2;
      const nextConfidence = candidate.confidence ?? candidate.overall_confidence;
      if (nextTrigger !== null && nextTrigger !== undefined) setTrigger(String(nextTrigger));
      if (nextStop !== null && nextStop !== undefined) setStopLoss(String(nextStop));
      if (nextTarget1 !== null && nextTarget1 !== undefined) setTarget1(String(nextTarget1));
      if (nextTarget2 !== null && nextTarget2 !== undefined) setTarget2(String(nextTarget2));
      if (typeof nextConfidence === 'number') setConfidence(String(Math.round(nextConfidence)));
      if (candidate.strategy) setStrategy(candidate.strategy);
      setFeedNote(
        candidate.rationale?.slice(0, 2).join(' · ') ??
          `Detected ${candidateDirection || 'setup'} with level ${nextTrigger ?? '—'}.`,
      );
    } catch (err) {
      setFeedNote(errorMessage(err, 'Auto-detect unavailable'));
    } finally {
      setDetecting(false);
    }
  }, [desk, effectiveStrategy, instrument, timeframe]);

  const handlePreview = useCallback(async () => {
    setPreviewing(true);
    try {
      const result = await api.previewSignal({
        underlying: instrument,
        direction,
        timeframe,
        strategy: effectiveStrategy,
        confidence: toNumber(confidence) ?? 80,
        trigger_level: toNumber(trigger),
        stop_loss: toNumber(stopLoss),
        target_1: toNumber(target1),
        target_2: toNumber(target2),
      });
      setPreview(result.preview);
    } catch (err) {
      setPreview(`Preview failed: ${errorMessage(err, 'unknown error')}`);
    } finally {
      setPreviewing(false);
    }
  }, [confidence, direction, effectiveStrategy, instrument, stopLoss, target1, target2, timeframe, trigger]);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    try {
      const result: DeskActionResult = await desk.generate(buildPayload());
      push(result.ok ? 'success' : 'error', result.message);
    } finally {
      setGenerating(false);
    }
  }, [buildPayload, desk, push]);

  return (
    <section className="panel">
      <header className="card-hd">
        <h3 className="card-title">Signal Generator</h3>
        <span className="card-meta">{instrument}</span>
      </header>
      <div className="border-b border-border-subtle bg-surface-subtle px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="sg-lab">
            <span>Desk</span>
            <span className="seg">
              {(['INTRADAY', 'SCALP'] as DeskScope[]).map((scope) => (
                <button
                  key={scope}
                  type="button"
                  className="seg-btn"
                  data-active={deskScope === scope}
                  onClick={() => setDeskScope(scope)}
                >
                  {scope}
                </button>
              ))}
            </span>
          </span>
          <span className="sg-lab">
            <span>Direction</span>
            <span className="seg">
              {(['BULLISH', 'BEARISH'] as const).map((bias) => (
                <button
                  key={bias}
                  type="button"
                  className="seg-btn"
                  data-active={direction === bias}
                  onClick={() => setDirection(bias)}
                >
                  {bias}
                </button>
              ))}
            </span>
          </span>
          <label className="field">
            <span className="field-l">Strategy</span>
            <select
              className="input"
              value={effectiveStrategy}
              onChange={(event) => setStrategy(event.target.value)}
            >
              {strategyOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-l">Timeframe</span>
            <select
              className="input"
              value={timeframe}
              onChange={(event) => setTimeframe(event.target.value as (typeof TIMEFRAMES)[number])}
            >
              {TIMEFRAMES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-l">Confidence</span>
            <input
              className="input num"
              type="number"
              min={0}
              max={100}
              value={confidence}
              onChange={(event) => setConfidence(event.target.value)}
            />
          </label>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <label className="field">
            <span className="field-l">Trigger</span>
            <input
              className="input num"
              type="number"
              step="0.05"
              value={trigger}
              onChange={(event) => setTrigger(event.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="field">
            <span className="field-l">Stop loss</span>
            <input
              className="input num"
              type="number"
              step="0.05"
              value={stopLoss}
              onChange={(event) => setStopLoss(event.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="field">
            <span className="field-l">Target 1</span>
            <input
              className="input num"
              type="number"
              step="0.05"
              value={target1}
              onChange={(event) => setTarget1(event.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="field">
            <span className="field-l">Target 2</span>
            <input
              className="input num"
              type="number"
              step="0.05"
              value={target2}
              onChange={(event) => setTarget2(event.target.value)}
              placeholder="optional"
            />
          </label>
          <label className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-ink-2">
            <input
              type="checkbox"
              checked={notifyTelegram}
              onChange={(event) => setNotifyTelegram(event.target.checked)}
            />
            Telegram alert
          </label>
          <label className="mt-4 flex items-center gap-1.5 text-xs font-semibold text-ink-2">
            <input
              type="checkbox"
              checked={allowClosedMarket}
              onChange={(event) => setAllowClosedMarket(event.target.checked)}
            />
            Force when market closed
          </label>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn btn-ic"
            onClick={() => void handleAutoDetect()}
            disabled={detecting}
          >
            <Wand2 size={13} />
            {detecting ? 'Scanning…' : 'Auto-detect setup'}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => void handlePreview()}
            disabled={previewing}
          >
            {previewing ? 'Building preview…' : 'Preview alert'}
          </button>
          <button
            type="button"
            className="btn btn-primary btn-ic"
            onClick={() => void handleGenerate()}
            disabled={generating}
          >
            <Sparkles size={13} />
            {generating ? 'Generating…' : 'Generate signal'}
          </button>
          {feedNote ? <span className="sg-note">{feedNote}</span> : null}
        </div>

        {preview ? (
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-sm border border-border bg-card p-2 font-mono text-[10.5px] leading-snug text-ink-2">
            {preview}
          </pre>
        ) : null}
      </div>
    </section>
  );
}
