'use client';

import React from 'react';
import { FeedbackBanner } from './ui/SettingPrimitives';
import { useTelegram } from './telegram/useTelegram';
import { TelegramConnectionCard } from './telegram/TelegramConnectionCard';
import { TelegramSubscriptionsCard } from './telegram/TelegramSubscriptionsCard';
import { TelegramSimulatorCard } from './telegram/TelegramSimulatorCard';
import { TelegramTelemetryCard } from './telegram/TelegramTelemetryCard';

/**
 * Telegram alerts tab.
 *
 * State lives in `useTelegram`; this file only composes the four cards.
 * Telegram preferences are stored per-user on the backend (not in the local
 * AppSettings blob), so this tab deliberately takes no settings props.
 */
export function TelegramTab() {
  const tg = useTelegram();

  if (tg.loading) {
    return (
      <div className="flex items-center justify-center min-h-[180px]">
        <div className="w-5 h-5 border-2 border-[var(--ds-accent)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <FeedbackBanner message={tg.msg} onDismiss={() => tg.setMsg(null)} />

      <TelegramConnectionCard tg={tg} />
      <TelegramSubscriptionsCard tg={tg} />
      <TelegramSimulatorCard tg={tg} />
      <TelegramTelemetryCard tg={tg} />
    </div>
  );
}
