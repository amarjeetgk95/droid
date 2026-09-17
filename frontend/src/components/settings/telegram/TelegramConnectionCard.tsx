'use client';

import React from 'react';
import { Bot, ExternalLink, Clock, Send, Unlink } from 'lucide-react';
import { SettingSection, SettingRow } from '../ui/SettingPrimitives';
import type { useTelegram } from './useTelegram';

interface Props {
  tg: ReturnType<typeof useTelegram>;
}

/** Pairing status, OAuth-style link generation, test alert and unlink. */
export function TelegramConnectionCard({ tg }: Props) {
  const linked = tg.status?.binding.linked ?? false;

  return (
    <SettingSection
      title="Telegram notification gateway"
      description="Real-time breakout and execution alerts in your personal chat."
      icon={Bot}
      action={
        <div className="flex items-center gap-2">
          <span
            className={`text-xs px-2.5 py-1 rounded-md font-medium border flex items-center gap-1.5 ${
              linked
                ? 'bg-[var(--ds-bull-wash)] text-[var(--ds-bull-strong)] border-[var(--ds-bull-line)]'
                : 'bg-[var(--ds-inset)] text-[var(--ds-ink-3)] border-[var(--ds-border-subtle)]'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                linked ? 'bg-[var(--ds-bull)] animate-pulse' : 'bg-[var(--ds-ink-4)]'
              }`}
            />
            {linked ? 'Connected' : 'Not Linked'}
          </span>
        </div>
      }
    >
      <SettingRow
        label="Bot Profile & Chat Binding"
        description={
          tg.status?.bot_username
            ? `Connected via @${tg.status.bot_username}`
            : 'Configure your Telegram Bot token in backend/.env (localhost).'
        }
      >
        <div className="text-xs text-[var(--ds-ink-3)]">
          {linked ? (
            <span className="font-mono text-[var(--ds-ink)] font-medium">
              Chat ID: {tg.status?.binding.telegram_chat_id ?? 'Active'}
            </span>
          ) : (
            <span>No chat paired</span>
          )}
        </div>
      </SettingRow>

      {!linked && !tg.linkUrl && (
        <div className="p-5 bg-[var(--ds-inset)]">
          <button
            type="button"
            onClick={tg.handleConnect}
            className="w-full sm:w-auto px-4 py-2 bg-[var(--ds-accent)] hover:bg-[var(--ds-accent-hover)] text-[var(--ds-accent-ink)] text-xs font-medium rounded-md transition-colors cursor-pointer"
          >
            Connect Telegram Account
          </button>
        </div>
      )}

      {!linked && tg.linkUrl && (
        <div className="p-5 bg-[var(--ds-inset-2)] space-y-3">
          <div className="text-xs font-medium text-[var(--ds-ink)]">Complete Telegram Pairing</div>
          <p className="text-xs text-[var(--ds-ink-3)] leading-relaxed">
            Open the bot link below and click <strong>Start</strong> to pair your personal account.
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            <a
              href={tg.linkUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-[var(--ds-accent)] text-[var(--ds-accent-ink)] text-xs font-medium hover:bg-[var(--ds-accent-hover)] transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Open in Telegram</span>
            </a>
            <span className="text-xs text-[var(--ds-ink-3)] font-mono flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              Token expires in: {tg.countdown.mm}:{tg.countdown.ss}
            </span>
          </div>
        </div>
      )}

      {linked && (
        <div className="p-5 flex items-center gap-2.5">
          <button
            type="button"
            onClick={tg.handleTest}
            disabled={tg.testing}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[var(--ds-inset)] hover:bg-[var(--ds-hover)] text-[var(--ds-ink)] border border-[var(--ds-border-strong)] rounded-md text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5 text-[var(--ds-ink-3)]" />
            <span>{tg.testing ? 'Queuing…' : 'Send Test Alert'}</span>
          </button>
          <button
            type="button"
            onClick={tg.handleRevoke}
            className="flex items-center gap-1.5 px-3 py-1.5 text-[var(--ds-bear)] bg-[var(--ds-bear-wash)] hover:bg-[var(--ds-bear-line)] border border-[var(--ds-bear-line)] rounded-md text-xs font-medium transition-colors cursor-pointer"
          >
            <Unlink className="w-3.5 h-3.5" />
            <span>Unlink Chat</span>
          </button>
        </div>
      )}
    </SettingSection>
  );
}
