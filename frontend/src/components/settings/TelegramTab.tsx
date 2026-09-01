'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  CheckCircle2, AlertCircle, Link2, Unlink, Clock, ExternalLink, Bot,
  Send, Eye, RotateCcw, ToggleLeft, ToggleRight, Activity, ListChecks, RefreshCw,
} from 'lucide-react';
import { api } from '@/lib/api';
import type { TelegramPreferences, TelegramAuditRecord } from '@/lib/types';

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
  'SIGNAL_TRIGGERED', 'SIGNAL_CONFIRMED', 'POSSIBLE_SETUP',
  'AI_CONFIRMED', 'RISK_APPROVED', 'RISK_REJECTED',
  'EXECUTED', 'PARTIALLY_FILLED', 'TARGET_HIT', 'STOP_HIT', 'SIGNAL_RESULT',
  'SIGNAL_EXPIRED', 'SIGNAL_INVALIDATED',
];

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

function SectionHeader({ title, subtitle, icon: Icon }: { title: string; subtitle?: string; icon?: React.ComponentType<{ className?: string }> }) {
  return (
    <div className="flex items-center gap-2.5">
      {Icon && <div className="p-1.5 rounded-lg bg-primary/10 border border-primary/20 text-primary"><Icon className="w-3.5 h-3.5" /></div>}
      <div>
        <h3 className="text-sm font-semibold tracking-wide">{title}</h3>
        {subtitle && <p className="text-[10px] font-mono text-muted-foreground">{subtitle}</p>}
      </div>
    </div>
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

  // ── Adjustment & Testing additions ──
  const [audit, setAudit] = useState<TelegramAuditRecord[]>([]);
  const [queueStats, setQueueStats] = useState<Record<string, unknown> | null>(null);
  const [adjustBusy, setAdjustBusy] = useState(false);
  // Signal Center simulator
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
      /* audit optional when not linked */
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const s = await api.getTelegramStats();
      setQueueStats(s.notification_queue as Record<string, unknown>);
    } catch {
      /* best-effort */
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
          if ((s as unknown as TelegramStatus).binding.linked) {
            setStatus(s as unknown as TelegramStatus);
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
      setTimeout(loadAudit, 1500);
      loadStats();
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

  // ── Adjustment helpers ──
  const handleEnableAll = async () => {
    setAdjustBusy(true);
    try {
      const next = await api.bulkTelegramPreferences(true);
      setPrefs(next);
      setMsg({ type: 'success', text: 'All event alerts enabled.' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Bulk enable failed' });
    } finally { setAdjustBusy(false); }
  };
  const handleDisableAll = async () => {
    setAdjustBusy(true);
    try {
      const next = await api.bulkTelegramPreferences(false);
      setPrefs(next);
      setMsg({ type: 'success', text: 'All event alerts disabled.' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Bulk disable failed' });
    } finally { setAdjustBusy(false); }
  };
  const handleReset = async () => {
    setAdjustBusy(true);
    try {
      const next = await api.resetTelegramPreferences();
      setPrefs(next);
      setMsg({ type: 'success', text: 'Preferences reset to defaults.' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Reset failed' });
    } finally { setAdjustBusy(false); }
  };

  // ── Testing helpers (Signal Center) ──
  const handlePreview = async () => {
    setSimBusy(true);
    setMsg(null);
    try {
      // Build minimal event mirroring backend quick-test logic for preview-only
      const demo: Record<string, number> = { NIFTY: 24885, BANKNIFTY: 52100, SENSEX: 81500, BTCUSD: 65000 };
      const spot = demo[simInstrument] ?? 10000;
      const event: Record<string, unknown> = {
        event_type: simEvent,
        signal_id: `preview-${Date.now()}`,
        instrument: simInstrument,
        candle_timeframe: simTimeframe,
        setup_type: simDirection === 'BEARISH' ? 'BREAKDOWN' : 'BREAKOUT',
        direction: simDirection,
        status: simEvent.replace('SIGNAL_', ''),
        trigger_level: spot * 1.005,
        current_price: spot,
        confidence: 84,
        breakout_pressure: 78,
        false_breakout_risk: 22,
        stop_loss: spot * 0.992,
        target_low: spot * 1.01,
        target_high: spot * 1.015,
        options_status: 'SUPPORTIVE',
        ai_status: 'CONFIRMED',
        risk_status: 'APPROVED',
        ai_decision: 'CONFIRM',
        ai_confidence: 82,
        risk_portfolio: 'PASS',
        risk_exposure: 'Within Limits',
        requested_qty: 75, filled_qty: 75, average_fill_price: spot, broker_order_id: 'ORD-PREVIEW',
      };
      const res = await api.previewTelegramEvent(event);
      setPreview(res.preview);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Preview failed' });
    } finally { setSimBusy(false); }
  };

  const handleQuickTest = async () => {
    setSimBusy(true);
    setMsg(null);
    setPreview(null);
    try {
      const res = await api.quickTestTelegram({
        instrument: simInstrument,
        event_type: simEvent,
        candle_timeframe: simTimeframe,
        direction: simDirection,
      });
      setPreview(res.preview);
      if (res.notification_ids.length === 0) {
        setMsg({ type: 'error', text: 'No notification queued — check: linked? event enabled? instrument/timeframe enabled? dedup within 60s?' });
      } else {
        setMsg({ type: 'success', text: `Sample ${simEvent} queued (${res.notification_ids.length} chat) — signal ${res.signal_id}. Check Telegram.` });
      }
      setTimeout(() => { loadAudit(); loadStats(); }, 1500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Sample publish failed' });
    } finally { setSimBusy(false); }
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
  const statuses = (queueStats?.statuses as Record<string, number> | undefined);

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
          <SectionHeader title="TELEGRAM INTEGRATION" subtitle="Signal Center → Telegram Queue → Rate Limiter → Bot" icon={Bot} />
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
            <span className="truncate">{linked ? (status?.binding.telegram_chat_id ?? 'Linked') : 'Not Linked'}</span>
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
            className="w-full py-2.5 rounded-lg bg-sky-600/20 border border-sky-500/40 text-sky-300 text-xs font-mono font-semibold hover:bg-sky-600/30 transition-colors cursor-pointer"
          >
            [ CONNECT TELEGRAM ]
          </button>
        )}

        {!linked && linkUrl && (
          <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-4 space-y-3">
            <div className="text-xs font-semibold text-sky-300">Connect Telegram</div>
            <ol className="text-xs text-muted-foreground space-y-1 list-decimal list-inside font-mono">
              <li>Open the Telegram bot</li>
              <li>Press Start — sends <code className="bg-card px-1 rounded">/start &lt;token&gt;</code></li>
            </ol>
            <div className="flex items-center gap-3 flex-wrap">
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
              className="flex-1 py-2.5 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs font-mono font-semibold hover:bg-emerald-500/25 transition-colors disabled:opacity-50 cursor-pointer flex items-center justify-center gap-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              {testing ? 'QUEUING…' : '[ SEND TEST MESSAGE ]'}
            </button>
            <button
              onClick={handleRevoke}
              className="px-4 py-2.5 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-xs font-mono hover:bg-destructive/20 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <Unlink className="w-3.5 h-3.5" />
              UNLINK
            </button>
          </div>
        )}
      </div>

      {/* ── ADJUSTMENT ── Notification preferences ── */}
      {prefs && (
        <div className="rounded-xl border border-border bg-card p-5 space-y-5">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <SectionHeader title="ADJUSTMENT" subtitle="Per-user filters — instant effect, no restart. Signal Center respects these." icon={ListChecks} />
            <div className="flex gap-2">
              <button onClick={handleEnableAll} disabled={adjustBusy} className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-[11px] font-mono hover:bg-emerald-500/20 disabled:opacity-50 cursor-pointer flex items-center gap-1">
                <ToggleRight className="w-3.5 h-3.5" /> Enable All
              </button>
              <button onClick={handleDisableAll} disabled={adjustBusy} className="px-3 py-1.5 rounded-lg bg-muted border border-border text-muted-foreground text-[11px] font-mono hover:bg-secondary disabled:opacity-50 cursor-pointer flex items-center gap-1">
                <ToggleLeft className="w-3.5 h-3.5" /> Disable All
              </button>
              <button onClick={handleReset} disabled={adjustBusy} className="px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] font-mono hover:bg-amber-500/20 disabled:opacity-50 cursor-pointer flex items-center gap-1">
                <RotateCcw className="w-3.5 h-3.5" /> Reset Defaults
              </button>
            </div>
          </div>

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
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Candle Timeframe — §13</div>
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
            <p className="text-[10px] text-muted-foreground font-mono mt-1">1M messages show ⚡ header, 5M show 🟢/🔴 — never mislabeled.</p>
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
            <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider mb-1.5">Event — uncheck to mute (still audited as SKIPPED)</div>
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

          <p className="text-[10px] text-muted-foreground font-mono border-t border-border pt-3">
            Duplicate <code className="bg-muted px-1 rounded">signal_id:event_type:user</code> suppressed (§33). Per-instrument throttle 60s (§11). Rate-limited 20/s global, 1/s per chat (§25).
          </p>
        </div>
      )}

      {/* ── TESTING ── Signal Center simulator ── */}
      <div className="rounded-xl border border-border bg-card p-5 space-y-4">
        <SectionHeader title="TESTING — Signal Center" subtitle="Build a realistic SignalEvent and push it through the same queue/rate-limiter your live signals use." icon={Activity} />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <label className="space-y-1">
            <span className="text-[10px] font-mono text-muted-foreground uppercase">Instrument</span>
            <select value={simInstrument} onChange={e => setSimInstrument(e.target.value)} className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-xs font-mono">
              {INSTRUMENTS.map(i => <option key={i} value={i}>{i}</option>)}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] font-mono text-muted-foreground uppercase">Event</span>
            <select value={simEvent} onChange={e => setSimEvent(e.target.value)} className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-xs font-mono">
              {SAMPLE_EVENTS.map(e => <option key={e} value={e}>{e}</option>)}
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] font-mono text-muted-foreground uppercase">Timeframe</span>
            <select value={simTimeframe} onChange={e => setSimTimeframe(e.target.value)} className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-xs font-mono">
              <option value="5M">5M</option>
              <option value="1M">1M</option>
            </select>
          </label>
          <label className="space-y-1">
            <span className="text-[10px] font-mono text-muted-foreground uppercase">Direction</span>
            <select value={simDirection} onChange={e => setSimDirection(e.target.value)} className="w-full bg-background border border-border rounded-lg px-2 py-1.5 text-xs font-mono">
              <option value="BULLISH">BULLISH (LONG)</option>
              <option value="BEARISH">BEARISH (SHORT)</option>
            </select>
          </label>
        </div>
        <div className="flex gap-3">
          <button onClick={handlePreview} disabled={simBusy} className="flex-1 py-2 rounded-lg bg-secondary border border-border text-foreground text-xs font-mono hover:bg-secondary/80 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-1.5">
            <Eye className="w-3.5 h-3.5" /> {simBusy ? '...' : '[ PREVIEW MESSAGE ]'}
          </button>
          <button onClick={handleQuickTest} disabled={simBusy || !linked} title={!linked ? 'Link Telegram first' : ''} className="flex-1 py-2 rounded-lg bg-sky-600 text-white text-xs font-mono font-semibold hover:bg-sky-500 disabled:opacity-50 cursor-pointer flex items-center justify-center gap-1.5">
            <Send className="w-3.5 h-3.5" /> {simBusy ? 'QUEUING…' : '[ SEND SAMPLE SIGNAL ]'}
          </button>
        </div>
        {!linked && <p className="text-[11px] text-amber-400 font-mono">Link Telegram first — samples are delivered only to your linked chat and respect the Adjustment filters above.</p>}
        {preview && (
          <div className="rounded-lg border border-border bg-background p-3">
            <div className="text-[10px] font-mono text-muted-foreground uppercase mb-1.5 flex items-center justify-between">
              <span>Telegram preview — exactly what will be sent</span>
              <span className="text-[10px] bg-muted px-1.5 py-0.5 rounded">{simInstrument} {simTimeframe} · {simEvent}</span>
            </div>
            <pre className="text-xs font-mono whitespace-pre-wrap break-words text-foreground max-h-[320px] overflow-auto">{preview}</pre>
          </div>
        )}
        <p className="text-[10px] text-muted-foreground font-mono">Uses <code className="bg-muted px-1 rounded">POST /api/v1/telegram/dev/quick-test</code> — live price if buffer has ticks, else demo. Throttled 60s per instrument/event; deduped by signal_id.</p>
      </div>

      {/* ── Queue Health & Audit ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-xl border border-border bg-card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold tracking-wide font-mono">QUEUE HEALTH</h4>
            <button onClick={() => { refreshStatus(); loadStats(); }} className="p-1 rounded hover:bg-secondary cursor-pointer"><RefreshCw className="w-3.5 h-3.5 text-muted-foreground" /></button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="rounded-lg bg-background border border-border p-2.5">
              <div className="text-[10px] text-muted-foreground uppercase">Queued</div>
              <div className="text-lg font-bold">{String(queueStats?.queued ?? (status?.queue_stats as Record<string, unknown>)?.queued ?? '—')}</div>
            </div>
            <div className="rounded-lg bg-background border border-border p-2.5">
              <div className="text-[10px] text-muted-foreground uppercase">Dead Letter</div>
              <div className="text-lg font-bold">{String(queueStats?.dead_letter ?? (status?.queue_stats as Record<string, unknown>)?.dead_letter ?? '—')}</div>
            </div>
            <div className="rounded-lg bg-background border border-border p-2.5 col-span-2">
              <div className="text-[10px] text-muted-foreground uppercase">Total audited</div>
              <div className="text-sm font-bold">{String(queueStats?.total ?? (status?.queue_stats as Record<string, unknown>)?.total ?? '—')}</div>
              {statuses && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {Object.entries(statuses).map(([k, v]) => (
                    <span key={k} className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${k === 'SENT' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : k === 'FAILED' ? 'bg-destructive/10 text-destructive border-destructive/20' : k === 'SKIPPED' ? 'bg-muted text-muted-foreground border-border' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>{k}: {String(v)}</span>
                  ))}
                </div>
              )}
            </div>
            <div className="rounded-lg bg-background border border-border p-2.5 col-span-2">
              <div className="text-[10px] text-muted-foreground uppercase">Outbound queue</div>
              <div className="text-sm">{String((queueStats as Record<string, unknown> | null)?.outbound_queue_size ?? '—')} pending to Telegram API (rate-limited 20/s global, 1/s per chat)</div>
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-semibold tracking-wide font-mono">RECENT AUDIT (20)</h4>
            <button onClick={loadAudit} disabled={auditLoading} className="p-1 rounded hover:bg-secondary cursor-pointer disabled:opacity-50"><RefreshCw className={`w-3.5 h-3.5 text-muted-foreground ${auditLoading ? 'animate-spin' : ''}`} /></button>
          </div>
          {audit.length === 0 ? (
            <p className="text-xs font-mono text-muted-foreground py-6 text-center border border-dashed border-border rounded-lg">No records yet — send a Test or Sample Signal.</p>
          ) : (
            <div className="max-h-[260px] overflow-auto rounded-lg border border-border">
              <table className="w-full text-[11px] font-mono">
                <thead className="sticky top-0 bg-card border-b border-border text-muted-foreground">
                  <tr><th className="text-left p-2 font-semibold">Time</th><th className="text-left p-2 font-semibold">Event</th><th className="text-left p-2 font-semibold">Status</th><th className="text-left p-2 font-semibold">Attempts</th></tr>
                </thead>
                <tbody>
                  {audit.map(r => (
                    <tr key={r.notification_id} className="border-b border-border/60 hover:bg-muted/20">
                      <td className="p-2 whitespace-nowrap">{new Date(r.created_at_utc).toLocaleTimeString()}</td>
                      <td className="p-2 truncate max-w-[140px]" title={r.signal_id}>{r.event_type}<div className="text-[10px] text-muted-foreground truncate">{r.signal_id}</div></td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] border ${r.delivery_status === 'SENT' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : r.delivery_status === 'FAILED' ? 'bg-destructive/10 text-destructive border-destructive/20' : r.delivery_status === 'SKIPPED' ? 'bg-muted text-muted-foreground border-border' : 'bg-amber-500/10 text-amber-400 border-amber-500/20'}`}>{r.delivery_status}</span>
                        {r.error && <div className="text-[10px] text-destructive truncate max-w-[120px]" title={r.error}>{r.error}</div>}
                      </td>
                      <td className="p-2 text-center">{r.attempt_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[10px] font-mono text-muted-foreground">Never stores bot token. Dedup key = signal_id:event_type:user. Tap refresh after Test/Sample.</p>
        </div>
      </div>
    </div>
  );
}
