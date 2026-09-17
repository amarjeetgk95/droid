'use client';

import React from 'react';
import { Activity, Eye, Send } from 'lucide-react';
import { SettingSection } from '../ui/SettingPrimitives';
import { INSTRUMENTS, SAMPLE_EVENTS } from './constants';
import type { useTelegram } from './useTelegram';

interface Props {
  tg: ReturnType<typeof useTelegram>;
}

const selectClass =
  'w-full bg-[var(--ds-inset)] border border-[var(--ds-border-strong)] rounded-md px-2.5 py-1.5 text-xs text-[var(--ds-ink)] cursor-pointer transition-colors focus:outline-none focus:border-[var(--ds-accent)]';

/** Mock a signal event through the rate-limiter and formatting pipeline. */
export function TelegramSimulatorCard({ tg }: Props) {
  const linked = tg.status?.binding.linked ?? false;

  return (
    <SettingSection
      title="Delivery probe simulator"
      description="Mock signal event through rate-limiter and formatting pipeline."
      icon={Activity}
    >
      <div className="p-5 space-y-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div>
            <label htmlFor="tg-sim-instrument" className="text-[11px] font-medium text-[var(--ds-ink-3)] block mb-1">
              Instrument
            </label>
            <select
              id="tg-sim-instrument"
              value={tg.simInstrument}
              onChange={(e) => tg.setSimInstrument(e.target.value)}
              className={selectClass}
            >
              {INSTRUMENTS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="tg-sim-event" className="text-[11px] font-medium text-[var(--ds-ink-3)] block mb-1">Event</label>
            <select
              id="tg-sim-event"
              value={tg.simEvent}
              onChange={(e) => tg.setSimEvent(e.target.value)}
              className={selectClass}
            >
              {SAMPLE_EVENTS.map((e) => (
                <option key={e} value={e}>
                  {e}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="tg-sim-timeframe" className="text-[11px] font-medium text-[var(--ds-ink-3)] block mb-1">
              Timeframe
            </label>
            <select
              id="tg-sim-timeframe"
              value={tg.simTimeframe}
              onChange={(e) => tg.setSimTimeframe(e.target.value)}
              className={selectClass}
            >
              <option value="5M">5M</option>
              <option value="1M">1M</option>
            </select>
          </div>

          <div>
            <label htmlFor="tg-sim-direction" className="text-[11px] font-medium text-[var(--ds-ink-3)] block mb-1">
              Direction
            </label>
            <select
              id="tg-sim-direction"
              value={tg.simDirection}
              onChange={(e) => tg.setSimDirection(e.target.value)}
              className={selectClass}
            >
              <option value="BULLISH">Bullish (Long)</option>
              <option value="BEARISH">Bearish (Short)</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2.5 pt-1">
          <button
            type="button"
            onClick={tg.handlePreview}
            disabled={tg.simBusy}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--ds-inset)] hover:bg-[var(--ds-hover)] text-[var(--ds-ink)] border border-[var(--ds-border-strong)] rounded-md text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Eye className="w-3.5 h-3.5 text-[var(--ds-ink-3)]" />
            <span>{tg.simBusy ? 'Loading…' : 'Preview Message'}</span>
          </button>
          <button
            type="button"
            onClick={tg.handleQuickTest}
            disabled={tg.simBusy || !linked}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--ds-accent)] hover:bg-[var(--ds-accent-hover)] text-[var(--ds-accent-ink)] text-xs font-medium rounded-md transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
            <span>{tg.simBusy ? 'Dispatching…' : 'Send Sample Alert'}</span>
          </button>
        </div>

        {tg.preview && (
          <div className="rounded-lg border border-[var(--ds-border-strong)] bg-[var(--ds-inset)] p-3.5 space-y-1.5">
            <div className="text-[11px] font-medium text-[var(--ds-ink-3)] flex items-center justify-between">
              <span>Preview Output</span>
              <span className="font-mono text-[10px]">
                {tg.simInstrument} {tg.simTimeframe} · {tg.simEvent}
              </span>
            </div>
            <pre className="text-xs font-mono whitespace-pre-wrap break-words text-[var(--ds-ink)] max-h-56 overflow-auto">
              {tg.preview}
            </pre>
          </div>
        )}
      </div>
    </SettingSection>
  );
}
