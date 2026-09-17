'use client';

import React from 'react';
import { ListChecks } from 'lucide-react';
import { SettingSection } from '../ui/SettingPrimitives';
import { TelegramToggle } from './TelegramToggle';
import { EVENT_GROUPS, INSTRUMENTS, TIMEFRAMES } from './constants';
import type { useTelegram } from './useTelegram';

interface Props {
  tg: ReturnType<typeof useTelegram>;
}

/** Per-user dispatch filters for instruments, timeframes, direction and events. */
export function TelegramSubscriptionsCard({ tg }: Props) {
  const { prefs } = tg;
  if (!prefs) {
    if (!tg.prefsError) return null;
    return (
      <SettingSection
        title="Signal & event subscriptions"
        description="Per-user dispatch filters. Unchecked events are muted without restarting workers."
        icon={ListChecks}
      >
        <div className="p-5 text-xs text-[var(--ds-bear-strong)]">
          Subscriptions unavailable — {tg.prefsError}
        </div>
      </SettingSection>
    );
  }

  return (
    <SettingSection
      title="Signal & event subscriptions"
      description="Per-user dispatch filters. Unchecked events are muted without restarting workers."
      icon={ListChecks}
      action={
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={tg.handleEnableAll}
            disabled={tg.adjustBusy}
            className="px-2.5 py-1 rounded text-[11px] font-medium text-[var(--ds-ink)] bg-[var(--ds-inset)] hover:bg-[var(--ds-hover)] transition-colors cursor-pointer disabled:opacity-50"
          >
            Enable All
          </button>
          <button
            type="button"
            onClick={tg.handleDisableAll}
            disabled={tg.adjustBusy}
            className="px-2.5 py-1 rounded text-[11px] font-medium text-[var(--ds-ink-3)] hover:text-[var(--ds-ink)] transition-colors cursor-pointer disabled:opacity-50"
          >
            Mute All
          </button>
          <button
            type="button"
            onClick={tg.handleReset}
            disabled={tg.adjustBusy}
            title="Reset all subscriptions to server defaults (asks for confirmation)"
            className="px-2.5 py-1 rounded text-[11px] font-medium text-[var(--ds-ink-3)] hover:text-[var(--ds-ink)] transition-colors cursor-pointer disabled:opacity-50"
          >
            Reset
          </button>
        </div>
      }
    >
      {/* Instruments */}
      <div className="p-5 space-y-2">
        <span className="text-xs font-medium text-[var(--ds-ink)] block">Active Instruments</span>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {INSTRUMENTS.map((i) => (
            <TelegramToggle
              key={i}
              label={i}
              checked={prefs.instruments[i] ?? false}
              onChange={(v) => tg.savePrefs({ ...prefs, instruments: { ...prefs.instruments, [i]: v } })}
            />
          ))}
        </div>
      </div>

      {/* Timeframes & Direction */}
      <div className="p-5 border-t border-[var(--ds-border-subtle)] grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <span className="text-xs font-medium text-[var(--ds-ink)] block mb-2">Candle Timeframes</span>
          <div className="flex gap-4">
            {TIMEFRAMES.map((t) => (
              <TelegramToggle
                key={t}
                label={t}
                checked={prefs.timeframes[t] ?? false}
                onChange={(v) => tg.savePrefs({ ...prefs, timeframes: { ...prefs.timeframes, [t]: v } })}
              />
            ))}
          </div>
        </div>

        <div>
          <span className="text-xs font-medium text-[var(--ds-ink)] block mb-2">Setup Direction</span>
          <div className="flex gap-4">
            <TelegramToggle
              label="Breakout (Long)"
              checked={prefs.breakout}
              onChange={(v) => tg.savePrefs({ ...prefs, breakout: v })}
            />
            <TelegramToggle
              label="Breakdown (Short)"
              checked={prefs.breakdown}
              onChange={(v) => tg.savePrefs({ ...prefs, breakdown: v })}
            />
          </div>
        </div>
      </div>

      {/* Lifecycle & Result Events */}
      <div className="p-5 border-t border-[var(--ds-border-subtle)] space-y-3">
        <span className="text-xs font-medium text-[var(--ds-ink)] block">Notification Triggers</span>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {EVENT_GROUPS.map((g) => (
            <div key={g.group} className="space-y-1.5">
              <div className="text-[10px] uppercase font-semibold text-[var(--ds-ink-3)] tracking-wider">
                {g.group}
              </div>
              {g.items.map((ev) => (
                <TelegramToggle
                  key={ev.key}
                  label={ev.label}
                  checked={prefs.events[ev.key] ?? false}
                  onChange={(v) => tg.savePrefs({ ...prefs, events: { ...prefs.events, [ev.key]: v } })}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </SettingSection>
  );
}
