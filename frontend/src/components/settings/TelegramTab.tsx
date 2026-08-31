'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2, AlertCircle, Link2, Unlink, Clock, ExternalLink, Bot,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { TelegramPreferences } from '@/lib/types';

interface TelegramStatus {
  bot_configured: boolean;
  bot_username: string | null;
  webhook_configured: boolean;
  binding: { linked: boolean; telegram_chat_id: string | null; linked_at: number | null; status: string };
  environment: string;
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

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="flex items-center gap-2.5 cursor-pointer group py-1">
      <span
        onClick={(e) => { e.preventDefault(); onChange(!checked); }}
        className={`w-4 h-4 rounded border flex items-center justify-center transition-colors shrink-0 ${
          checked ? 'bg-emerald-500/20 border-emerald-500/60' : 'bg-card border-border group-hover:border-muted-foreground/40'
        }`}
      >
        {checked && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
      </span>
      <span className={`text-xs font-mono ${checked ? 'text-foreground' : 'text-muted-foreground'}`}>{label}</span>
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

  const refreshStatus = useCallback(async () => {
    try {
      const s = await api.getTelegramStatus();
      setStatus(s);
      if (s.binding.linked && linkUrl) {
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

  useEffect(() => {
    refreshStatus();
    loadPrefs();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (tickRef.current) clearInterval(tickRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Countdown tick while a link token is alive
  useEffect(() => {
    if (expiry) {
      tickRef.current = setInterval(() => setNow(Date.now()), 1000);
      return () => { if (tickRef.current) clearInterval(tickRef.current); };
    }
  }, [expiry]);

  const handleConnect = async () => {
    setMsg(null);
    try {
      const res = await api.generateTelegramLink();
      setLinkUrl(res.url);
      setExpiry(Date.now() + res.ttl_seconds * 1000);
      setNow(Date.now());
      // Poll for link completion while the one-time token is alive
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        if (Date.now() > (expiry ?? 0)) {
          if (pollRef.current) clearInterval(pollRef.current);
          return;
        }
        try {
          const s = await api.getTelegramStatus();
          if (s.binding.linked) {
            setStatus(s);
            setLinkUrl(null);
            setExpiry(null);
            if (pollRef.current) clearInterval(pollRef.current);
            setMsg({ type: 'success', text: 'Telegram connected! Your chat is now linked.' });
          }
        } catch { /* keep polling */ }
      }, 4000);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to generate link token' });
    }
  };

  const handleRevoke = async () => {
    try {
      await api.revokeTelegramLink();
      setLinkUrl(null);
      setExpiry(null);
      setMsg({ type: 'success', text: 'Telegram chat unlinked.' });
      await refreshStatus();
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to unlink' });
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setMsg(null);
    try {
      await api.sendTelegramTestMessage();
      setMsg({ type: 'success', text: 'Test message queued — check your Telegram (labeled TEST MESSAGE).' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to send test message' });
    } finally {
      setTesting(false);
    }
  };

  const savePrefs = async (next: TelegramPreferences) => {
    setPrefs(next);
    try {
      await api.updateTelegramPreferences(next);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to save preferences' });
    }
  };

  const remaining = expiry ? Math.max(0, Math.floor((expiry - now) / 1000)) : 0;
  const mm = String(Math.floor(remaining / 60)).padStart(2, '0');
  const ss = String(remaining % 60).padStart(2, '0');

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[200px]">
        <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const linked = status?.binding.linked ?? false;

  return (
    <div className="space-y-6">
      {msg && (
        <div
          className={`p-3.5 rounded-xl text-xs flex items-center gap-2 ${
            msg.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-destructive/10 text-destructive border border-destructive/20'
          }`}
        >
          {msg.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
          <span>{msg.text}</span>
        </div>
      )}

      {/* ── TELEGRAM INTEGRATION status card ── */}
      <div className="rounded-xl border border-border bg-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold tracking-wide">TELEGRAM INTEGRATION</h3>
          <span
            className={`text-[10px] font-mono px-2 py-0.5 rounded-full border flex items-center gap-1.5 ${
              linked
                ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-muted text-muted-foreground border-border'
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${linked ? 'bg-emerald-400' : 'bg-muted-foreground'}`} />
            {linked ? 'CONNECTED' : 'NOT CONNECTED'}
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          <div className="flex items-center gap-2">
            <Bot className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Bot:</span>
            <span>{status?.bot_username ? `@${status.bot_username}` : (status?.bot_configured ? 'configured' : 'not configured')}</span>
          </div>
          <div className="flex items-center gap-2">
            <Link2 className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">Linked Telegram Chat:</span>
            <span>{linked ? (status?.binding.telegram_chat_id ?? 'Linked') : 'Not Linked'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Environment:</span>
            <span>{(status?.environment ?? '—').toUpperCase()}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Webhook:</span>
            <span>{status?.webhook_configured ? 'secret configured' : 'not configured'}</span>
          </div>
        </div>

        {/* ── Connect flow ── */}
        {!linked && !linkUrl && (
          <button
            onClick={handleConnect}
            className="w-full py-2.5 rounded-lg bg-sky-600/20 border border-sky-500/40 text-sky-300 text-xs font-mono font-semibold hover:bg-sky-600/30 transition-colors"
          >
            [ CONNECT TELEGRAM ]
          </button>
        )}

        {!linked && linkUrl && (
          <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4 space-y-3">
            <div className="text-xs font-semibold text-sky-300">Connect Telegram</div>
            <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside font-mono">
              <li>Open the Telegram bot</li>
              <li>Press Start</li>
            </ol>
            <div className="flex items-center gap-3">
              <a
                href={linkUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-mono hover:bg-sky-500 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                [ OPEN TELEGRAM ]
              </a>
              <span className="text-xs text-muted-foreground font-mono flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5" />
                Token expires in: {mm}:{ss}
              </span>
            </div>
          </div>
        )}

        {linked && (
          <div className="flex gap-3">
            <button
              onClick={handleTest}
              disabled={testing}
              className="flex-1 py-2.5 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs font-mono font-semibold hover:bg-emerald-500/25 transition-colors disabled:opacity-50"
            >
              {testing ? 'QUEUING…' : '[ SEND TEST MESSAGE ]'}
            </button>
            <button
              onClick={handleRevoke}
              className="px-4 py-2.5 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-xs font-mono hover:bg-destructive/20 transition-colors flex items-center gap-1.5"
            >
              <Unlink className="w-3.5 h-3.5" />
              UNLINK
            </button>
          </div>
        )}
      </div>

      {/* ── Notification preferences ── */}
      {prefs && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-5">
          <h3 className="text-sm font-semibold tracking-wide">NOTIFICATIONS</h3>

          {/* Instruments */}
          <div>
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Instrument</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4">
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

          {/* Timeframes */}
          <div>
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Candle Timeframe</div>
            <div className="flex gap-6">
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

          {/* Setup direction */}
          <div>
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Setup</div>
            <div className="flex gap-6">
              <Toggle label="Breakout" checked={prefs.breakout} onChange={(v) => savePrefs({ ...prefs, breakout: v })} />
              <Toggle label="Breakdown" checked={prefs.breakdown} onChange={(v) => savePrefs({ ...prefs, breakdown: v })} />
            </div>
          </div>

          {/* Events */}
          <div>
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Event</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8">
              {EVENT_GROUPS.map((g) => (
                <div key={g.group}>
                  <div className="text-[10px] font-mono text-muted-foreground/70 mt-2 mb-1">{g.group}</div>
                  {g.items.map((ev) => (
                    <Toggle
                      key={ev.key}
                      label={ev.label}
                      checked={prefs.events[ev.key] ?? false}
                      onChange={(v) => savePrefs({ ...prefs, events: { ...prefs.events, [ev.key]: v } })}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>

          <p className="text-[10px] text-muted-foreground font-mono">
            Duplicate notifications for the same signal + event are suppressed automatically.
            Preferences save instantly.
          </p>
        </div>
      )}
    </div>
  );
}
