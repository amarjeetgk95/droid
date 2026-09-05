'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  Link2,
  Unlink,
  Clock,
  ExternalLink,
  Bot,
  Send,
  Eye,
  RotateCcw,
  ToggleLeft,
  ToggleRight,
  Activity,
  ListChecks,
  RefreshCw,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { TelegramPreferences, TelegramAuditRecord } from '@/lib/types';
import { SettingSection, SettingRow, StatTile } from './ui/SettingPrimitives';

interface TelegramStatus {
  bot_configured: boolean;
  bot_username: string | null;
  webhook_configured: boolean;
  binding: { linked: boolean; telegram_chat_id: string | null; linked_at: number | null; status: string };
  environment: string;
  queue_stats?: Record<string, unknown>;
}

const EVENT_GROUPS: { group: string; items: { key: string; label: string }[] }[] = [
  {
    group: 'Signals',
    items: [
      { key: 'SIGNAL_TRIGGERED', label: '1M / 5M Breakout Triggered' },
      { key: 'SIGNAL_CONFIRMED', label: '1M / 5M Breakout Confirmed' },
      { key: 'POSSIBLE_SETUP', label: 'Possible Setup (Developing)' },
    ],
  },
  {
    group: 'Pipeline',
    items: [
      { key: 'AI_CONFIRMED', label: 'AI Confirmation' },
      { key: 'RISK_APPROVED', label: 'Risk Approval' },
      { key: 'RISK_REJECTED', label: 'Risk Rejected' },
    ],
  },
  {
    group: 'Execution & Result',
    items: [
      { key: 'EXECUTED', label: 'Execution' },
      { key: 'PARTIALLY_FILLED', label: 'Partial Fill' },
      { key: 'TARGET_HIT', label: 'Target Hit' },
      { key: 'STOP_HIT', label: 'Stop Hit' },
      { key: 'SIGNAL_RESULT', label: 'Signal Result' },
    ],
  },
  {
    group: 'Lifecycle',
    items: [
      { key: 'SIGNAL_EXPIRED', label: 'Expired' },
      { key: 'SIGNAL_INVALIDATED', label: 'Invalidated' },
    ],
  },
];

const INSTRUMENTS = ['NIFTY', 'BANKNIFTY', 'SENSEX', 'BTCUSD'];
const TIMEFRAMES = ['1M', '5M'];
const SAMPLE_EVENTS = [
  'SIGNAL_TRIGGERED',
  'SIGNAL_CONFIRMED',
  'POSSIBLE_SETUP',
  'AI_CONFIRMED',
  'RISK_APPROVED',
  'RISK_REJECTED',
  'EXECUTED',
  'PARTIALLY_FILLED',
  'TARGET_HIT',
  'STOP_HIT',
  'SIGNAL_RESULT',
  'SIGNAL_EXPIRED',
  'SIGNAL_INVALIDATED',
];

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer group py-1">
      <span
        onClick={(e) => {
          e.preventDefault();
          onChange(!checked);
        }}
        className={`w-3.5 h-3.5 rounded border flex items-center justify-center transition-colors shrink-0 ${
          checked
            ? 'bg-primary border-primary text-primary-foreground'
            : 'bg-card border-border/70 group-hover:border-foreground/40'
        }`}
      >
        {checked && <CheckCircle2 className="w-2.5 h-2.5" />}
      </span>
      <span className={`text-xs ${checked ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
        {label}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="hidden" />
    </label>
  );
}

export function TelegramTab() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [prefs, setPrefs] = useState<TelegramPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<number | null>(null);
  const [testing, setTesting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [now, setNow] = useState(Date.now());

  // Testing & Audit additions
  const [audit, setAudit] = useState<TelegramAuditRecord[]>([]);
  const [queueStats, setQueueStats] = useState<Record<string, unknown> | null>(null);
  const [adjustBusy, setAdjustBusy] = useState(false);

  // Simulator
  const [simInstrument, setSimInstrument] = useState('NIFTY');
  const [simEvent, setSimEvent] = useState('SIGNAL_CONFIRMED');
  const [simTimeframe, setSimTimeframe] = useState('5M');
  const [simDirection, setSimDirection] = useState('BULLISH');
  const [preview, setPreview] = useState<string | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.getTelegramStatus();
      setStatus(s as unknown as TelegramStatus);
      setQueueStats((s as unknown as { queue_stats: Record<string, unknown> }).queue_stats || null);
      if ((s as unknown as TelegramStatus).binding.linked && linkUrl) {
        setLinkUrl(null);
        setExpiry(null);
        setMsg({ type: 'success', text: 'Telegram connected! Your chat is now linked.' });
      }
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to load Telegram status' });
    } finally {
      setLoading(false);
    }
  }, [linkUrl]);

  const loadPrefs = useCallback(async () => {
    try {
      setPrefs(await api.getTelegramPreferences());
    } catch {
      /* prefs optional */
    }
  }, []);

  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await api.getTelegramAudit(20);
      setAudit(res.records as unknown as TelegramAuditRecord[]);
    } catch {
      /* audit optional */
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const s = await api.getTelegramStats();
      setQueueStats(s.notification_queue as Record<string, unknown>);
    } catch {
      /* stats optional */
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    loadPrefs();
    loadAudit();
    loadStats();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (tickRef.current) clearInterval(tickRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (expiry) {
      tickRef.current = setInterval(() => setNow(Date.now()), 1000);
      return () => {
        if (tickRef.current) clearInterval(tickRef.current);
      };
    }
  }, [expiry]);

  const handleConnect = async () => {
    setMsg(null);
    try {
      const res = await api.generateTelegramLink();
      setLinkUrl(res.url);
      setExpiry(Date.now() + res.ttl_seconds * 1000);
      setNow(Date.now());
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        if (Date.now() > (expiry ?? 0)) {
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        try {
          const s = await api.getTelegramStatus();
          if (s.binding.linked) {
            setStatus(s as unknown as TelegramStatus);
            setLinkUrl(null);
            setExpiry(null);
            if (pollRef.current) clearInterval(pollRef.current);
            setMsg({ type: 'success', text: 'Telegram successfully linked!' });
          }
        } catch {}
      }, 2500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to generate link' });
    }
  };

  const handleRevoke = async () => {
    if (!confirm('Are you sure you want to unlink Telegram notifications?')) return;
    try {
      await api.revokeTelegramLink();
      setMsg({ type: 'success', text: 'Telegram unlinked successfully.' });
      refreshStatus();
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to unlink' });
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setMsg(null);
    try {
      const res = await api.sendTelegramTestMessage();
      setMsg({ type: 'success', text: `Test alert queued (ID: ${res.notification_id || res.status})` });
      setTimeout(loadAudit, 1500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to send test alert' });
    } finally {
      setTesting(false);
    }
  };

  const savePrefs = async (next: TelegramPreferences) => {
    setPrefs(next);
    try {
      await api.updateTelegramPreferences(next);
    } catch {
      setMsg({ type: 'error', text: 'Failed to update notification filters.' });
    }
  };

  const handleEnableAll = async () => {
    if (!prefs) return;
    setAdjustBusy(true);
    const updated: TelegramPreferences = {
      ...prefs,
      breakout: true,
      breakdown: true,
      instruments: INSTRUMENTS.reduce((acc, i) => ({ ...acc, [i]: true }), {}),
      timeframes: TIMEFRAMES.reduce((acc, t) => ({ ...acc, [t]: true }), {}),
      events: EVENT_GROUPS.flatMap((g) => g.items).reduce((acc, it) => ({ ...acc, [it.key]: true }), {}),
    };
    await savePrefs(updated);
    setAdjustBusy(false);
  };

  const handleDisableAll = async () => {
    if (!prefs) return;
    setAdjustBusy(true);
    const updated: TelegramPreferences = {
      ...prefs,
      breakout: false,
      breakdown: false,
      instruments: INSTRUMENTS.reduce((acc, i) => ({ ...acc, [i]: false }), {}),
      timeframes: TIMEFRAMES.reduce((acc, t) => ({ ...acc, [t]: false }), {}),
      events: EVENT_GROUPS.flatMap((g) => g.items).reduce((acc, it) => ({ ...acc, [it.key]: false }), {}),
    };
    await savePrefs(updated);
    setAdjustBusy(false);
  };

  const handleReset = async () => {
    if (!prefs) return;
    setAdjustBusy(true);
    try {
      const res = await api.resetTelegramPreferences();
      setPrefs(res);
      setMsg({ type: 'success', text: 'Notification preferences reset to defaults.' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Reset failed' });
    } finally {
      setAdjustBusy(false);
    }
  };

  const handlePreview = async () => {
    setSimBusy(true);
    try {
      const res = await api.previewTelegramEvent({
        instrument: simInstrument,
        event_type: simEvent,
        candle_timeframe: simTimeframe,
        direction: simDirection,
      });
      setPreview(res.preview);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Preview failed' });
    } finally {
      setSimBusy(false);
    }
  };

  const handleQuickTest = async () => {
    setSimBusy(true);
    setMsg(null);
    try {
      const res = await api.quickTestTelegram({
        instrument: simInstrument,
        event_type: simEvent,
        candle_timeframe: simTimeframe,
        direction: simDirection,
      });
      setMsg({ type: 'success', text: `Sample signal dispatched (${res.signal_id || res.status})` });
      if (res.preview) setPreview(res.preview);
      setTimeout(loadAudit, 1500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Delivery probe failed' });
    } finally {
      setSimBusy(false);
    }
  };

  const msLeft = Math.max(0, (expiry ?? 0) - now);
  const secLeft = Math.floor(msLeft / 1000);
  const mm = String(Math.floor(secLeft / 60)).padStart(2, '0');
  const ss = String(secLeft % 60).padStart(2, '0');

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[180px]">
        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const linked = status?.binding.linked ?? false;
  const statuses = queueStats?.statuses as Record<string, number> | undefined;

  return (
    <div className="space-y-4">
      {msg && (
        <div
          className={`px-4 py-3 rounded-lg text-xs flex items-center gap-2.5 transition-all ${
            msg.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-600 border border-emerald-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {msg.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{msg.text}</span>
          <button
            type="button"
            onClick={() => setMsg(null)}
            className="ml-auto text-muted-foreground hover:text-foreground text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* 1. Telegram Connection Gateway */}
      <SettingSection
        title="Telegram notification gateway"
        description="Real-time breakout and execution alerts in your personal chat."
        icon={Bot}
        action={
          <div className="flex items-center gap-2">
            <span
              className={`text-xs px-2.5 py-1 rounded-md font-medium border flex items-center gap-1.5 ${
                linked
                  ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                  : 'bg-secondary text-muted-foreground border-border/60'
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  linked ? 'bg-emerald-500 animate-pulse' : 'bg-muted-foreground'
                }`}
              />
              {linked ? 'Connected' : 'Not Linked'}
            </span>
          </div>
        }
      >
        <SettingRow
          label="Bot Profile &amp; Chat Binding"
          description={
            status?.bot_username
              ? `Connected via @${status.bot_username}`
              : 'Configure your Telegram Bot token in Render environment.'
          }
        >
          <div className="text-xs text-muted-foreground">
            {linked ? (
              <span className="font-mono text-foreground font-medium">
                Chat ID: {status?.binding.telegram_chat_id ?? 'Active'}
              </span>
            ) : (
              <span>No chat paired</span>
            )}
          </div>
        </SettingRow>

        {!linked && !linkUrl && (
          <div className="p-5 bg-secondary/20">
            <button
              type="button"
              onClick={handleConnect}
              className="w-full sm:w-auto px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-md transition-colors cursor-pointer"
            >
              Connect Telegram Account
            </button>
          </div>
        )}

        {!linked && linkUrl && (
          <div className="p-5 bg-secondary/30 space-y-3">
            <div className="text-xs font-medium text-foreground">Complete Telegram Pairing</div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              Open the bot link below and click <strong>Start</strong> to pair your personal account.
            </p>
            <div className="flex items-center gap-3 flex-wrap">
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Open in Telegram</span>
              </a>
              <span className="text-xs text-muted-foreground font-mono flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Token expires in: {mm}:{ss}
              </span>
            </div>
          </div>
        )}

        {linked && (
          <div className="p-5 flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleTest}
              disabled={testing}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 rounded-md text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5 text-muted-foreground" />
              <span>{testing ? 'Queuing…' : 'Send Test Alert'}</span>
            </button>
            <button
              type="button"
              onClick={handleRevoke}
              className="flex items-center gap-1.5 px-3 py-1.5 text-destructive bg-destructive/5 hover:bg-destructive/10 border border-destructive/20 rounded-md text-xs font-medium transition-colors cursor-pointer"
            >
              <Unlink className="w-3.5 h-3.5" />
              <span>Unlink Chat</span>
            </button>
          </div>
        )}
      </SettingSection>

      {/* 2. Notification Subscriptions & Filters */}
      {prefs && (
        <SettingSection
          title="Signal & event subscriptions"
          description="Per-user dispatch filters. Unchecked events are muted without restarting workers."
          icon={ListChecks}
          action={
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleEnableAll}
                disabled={adjustBusy}
                className="px-2.5 py-1 rounded text-[11px] font-medium text-foreground bg-secondary hover:bg-secondary/80 transition-colors cursor-pointer disabled:opacity-50"
              >
                Enable All
              </button>
              <button
                type="button"
                onClick={handleDisableAll}
                disabled={adjustBusy}
                className="px-2.5 py-1 rounded text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
              >
                Mute All
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={adjustBusy}
                className="px-2.5 py-1 rounded text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors cursor-pointer disabled:opacity-50"
              >
                Reset
              </button>
            </div>
          }
        >
          {/* Instruments */}
          <div className="p-5 space-y-2">
            <span className="text-xs font-medium text-foreground block">Active Instruments</span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {INSTRUMENTS.map((i) => (
                <Toggle
                  key={i}
                  label={i}
                  checked={prefs.instruments[i] ?? false}
                  onChange={(v) => savePrefs({ ...prefs, instruments: { ...prefs.instruments, [i]: v } })}
                />
              ))}
            </div>
          </div>

          {/* Timeframes & Direction */}
          <div className="p-5 border-t border-border/40 grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <span className="text-xs font-medium text-foreground block mb-2">Candle Timeframes</span>
              <div className="flex gap-4">
                {TIMEFRAMES.map((t) => (
                  <Toggle
                    key={t}
                    label={t}
                    checked={prefs.timeframes[t] ?? false}
                    onChange={(v) => savePrefs({ ...prefs, timeframes: { ...prefs.timeframes, [t]: v } })}
                  />
                ))}
              </div>
            </div>

            <div>
              <span className="text-xs font-medium text-foreground block mb-2">Setup Direction</span>
              <div className="flex gap-4">
                <Toggle
                  label="Breakout (Long)"
                  checked={prefs.breakout}
                  onChange={(v) => savePrefs({ ...prefs, breakout: v })}
                />
                <Toggle
                  label="Breakdown (Short)"
                  checked={prefs.breakdown}
                  onChange={(v) => savePrefs({ ...prefs, breakdown: v })}
                />
              </div>
            </div>
          </div>

          {/* Lifecycle & Result Events */}
          <div className="p-5 border-t border-border/40 space-y-3">
            <span className="text-xs font-medium text-foreground block">Notification Triggers</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {EVENT_GROUPS.map((g) => (
                <div key={g.group} className="space-y-1.5">
                  <div className="text-[10px] uppercase font-semibold text-muted-foreground tracking-wider">
                    {g.group}
                  </div>
                  {g.items.map((ev) => (
                    <Toggle
                      key={ev.key}
                      label={ev.label}
                      checked={prefs.events[ev.key] ?? false}
                      onChange={(v) =>
                        savePrefs({ ...prefs, events: { ...prefs.events, [ev.key]: v } })
                      }
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </SettingSection>
      )}

      {/* 3. Signal Simulator Probe */}
      <SettingSection
        title="Delivery probe simulator"
        description="Mock signal event through rate-limiter and formatting pipeline."
        icon={Activity}
      >
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                Instrument
              </label>
              <select
                value={simInstrument}
                onChange={(e) => setSimInstrument(e.target.value)}
                className="w-full bg-secondary/50 border border-border/70 rounded-md px-2.5 py-1.5 text-xs text-foreground"
              >
                {INSTRUMENTS.map((i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] font-medium text-muted-foreground block mb-1">Event</label>
              <select
                value={simEvent}
                onChange={(e) => setSimEvent(e.target.value)}
                className="w-full bg-secondary/50 border border-border/70 rounded-md px-2.5 py-1.5 text-xs text-foreground"
              >
                {SAMPLE_EVENTS.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                Timeframe
              </label>
              <select
                value={simTimeframe}
                onChange={(e) => setSimTimeframe(e.target.value)}
                className="w-full bg-secondary/50 border border-border/70 rounded-md px-2.5 py-1.5 text-xs text-foreground"
              >
                <option value="5M">5M</option>
                <option value="1M">1M</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                Direction
              </label>
              <select
                value={simDirection}
                onChange={(e) => setSimDirection(e.target.value)}
                className="w-full bg-secondary/50 border border-border/70 rounded-md px-2.5 py-1.5 text-xs text-foreground"
              >
                <option value="BULLISH">Bullish (Long)</option>
                <option value="BEARISH">Bearish (Short)</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2.5 pt-1">
            <button
              type="button"
              onClick={handlePreview}
              disabled={simBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border/60 rounded-md text-xs font-medium transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Eye className="w-3.5 h-3.5 text-muted-foreground" />
              <span>{simBusy ? 'Loading…' : 'Preview Message'}</span>
            </button>
            <button
              type="button"
              onClick={handleQuickTest}
              disabled={simBusy || !linked}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-medium rounded-md transition-colors disabled:opacity-50 cursor-pointer"
            >
              <Send className="w-3.5 h-3.5" />
              <span>{simBusy ? 'Dispatching…' : 'Send Sample Alert'}</span>
            </button>
          </div>

          {preview && (
            <div className="rounded-lg border border-border/60 bg-muted/20 p-3.5 space-y-1.5">
              <div className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
                <span>Preview Output</span>
                <span className="font-mono text-[10px]">
                  {simInstrument} {simTimeframe} · {simEvent}
                </span>
              </div>
              <pre className="text-xs font-mono whitespace-pre-wrap break-words text-foreground max-h-56 overflow-auto">
                {preview}
              </pre>
            </div>
          )}
        </div>
      </SettingSection>

      {/* 4. Telemetry & Audit Trail */}
      <SettingSection
        title="Delivery telemetry & recent audit"
        description="Background dispatcher queue health and delivery logs."
        icon={RefreshCw}
        action={
          <button
            type="button"
            onClick={() => {
              refreshStatus();
              loadStats();
              loadAudit();
            }}
            disabled={auditLoading}
            className="flex items-center gap-1 px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground rounded transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${auditLoading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        }
      >
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatTile label="Queued" value={String(queueStats?.queued ?? '0')} />
            <StatTile
              label="Dead letter"
              value={String(queueStats?.dead_letter ?? '0')}
              tone={String(queueStats?.dead_letter ?? '0') !== '0' ? 'negative' : 'default'}
            />
            <StatTile label="Total audited" value={String(queueStats?.total ?? '0')} />
            <StatTile
              label="Status counts"
              value={statuses ? String(Object.values(statuses).reduce((a: number, b) => a + Number(b), 0)) : '0'}
              sub={
                statuses ? (
                  <span className="flex flex-wrap gap-1">
                    {Object.entries(statuses).map(([k, v]) => (
                      <span key={k} className="font-mono">
                        {k}: {String(v)}
                      </span>
                    ))}
                  </span>
                ) : undefined
              }
            />
          </div>

          {audit.length > 0 ? (
            <div className="rounded-lg border border-border/50 overflow-hidden">
              <table className="w-full text-xs font-mono">
                <thead className="bg-muted/30 border-b border-border/40 text-muted-foreground">
                  <tr>
                    <th className="text-left p-2.5 font-medium">Time</th>
                    <th className="text-left p-2.5 font-medium">Event</th>
                    <th className="text-left p-2.5 font-medium">Status</th>
                    <th className="text-right p-2.5 font-medium">Attempts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/30">
                  {audit.map((r) => (
                    <tr key={r.notification_id} className="hover:bg-muted/20">
                      <td className="p-2.5 text-muted-foreground whitespace-nowrap">
                        {new Date(r.created_at_utc).toLocaleTimeString()}
                      </td>
                      <td className="p-2.5 truncate max-w-[160px]">
                        <span className="text-foreground">{r.event_type}</span>
                        <div className="text-[10px] text-muted-foreground truncate">{r.signal_id}</div>
                      </td>
                      <td className="p-2.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                            r.delivery_status === 'SENT'
                              ? 'bg-emerald-500/10 text-emerald-600'
                              : r.delivery_status === 'FAILED'
                                ? 'bg-destructive/10 text-destructive'
                                : 'bg-muted text-muted-foreground'
                          }`}
                        >
                          {r.delivery_status}
                        </span>
                      </td>
                      <td className="p-2.5 text-right text-muted-foreground">{r.attempt_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground text-center py-6 border border-dashed border-border/60 rounded-lg">
              No delivery logs recorded yet. Send a test probe to verify.
            </p>
          )}
        </div>
      </SettingSection>
    </div>
  );
}
