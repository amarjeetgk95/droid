'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type { TelegramPreferences, TelegramAuditRecord } from '@/lib/types';
import { EVENT_GROUPS, INSTRUMENTS, TIMEFRAMES, type TelegramStatus } from './constants';

export interface FeedbackMessage {
  type: 'success' | 'error';
  text: string;
}

/**
 * Owns all Telegram state + side effects for the settings tab.
 *
 * The tab used to hold this inline (812 lines). Lifting it into a hook lets the
 * four presentational cards stay dumb and keeps polling/cleanup in one place.
 */
export function useTelegram() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [prefs, setPrefs] = useState<TelegramPreferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<FeedbackMessage | null>(null);

  const [linkUrl, setLinkUrl] = useState<string | null>(null);
  const [expiry, setExpiry] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [testing, setTesting] = useState(false);

  const [audit, setAudit] = useState<TelegramAuditRecord[]>([]);
  const [queueStats, setQueueStats] = useState<Record<string, unknown> | null>(null);
  const [adjustBusy, setAdjustBusy] = useState(false);
  const [auditLoading, setAuditLoading] = useState(false);
  const [prefsError, setPrefsError] = useState<string | null>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);

  // Simulator
  const [simInstrument, setSimInstrument] = useState('NIFTY');
  const [simEvent, setSimEvent] = useState('SIGNAL_CONFIRMED');
  const [simTimeframe, setSimTimeframe] = useState('5M');
  const [simDirection, setSimDirection] = useState('BULLISH');
  const [preview, setPreview] = useState<string | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Keep the latest expiry readable from inside the polling interval without
  // re-creating the interval (avoids the stale-closure bug in the old version).
  const expiryRef = useRef<number | null>(null);
  expiryRef.current = expiry;
  // Latest prefs snapshot for optimistic updates that must roll back on failure.
  const prefsRef = useRef<TelegramPreferences | null>(prefs);
  prefsRef.current = prefs;

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const s = await api.getTelegramStats();
      setQueueStats(s.notification_queue as Record<string, unknown>);
      setStatsError(null);
    } catch (e: unknown) {
      setQueueStats(null);
      setStatsError(e instanceof Error ? e.message : 'Telegram stats unavailable');
    }
  }, []);

  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    try {
      const res = await api.getTelegramAudit(20);
      setAudit(res.records as unknown as TelegramAuditRecord[]);
      setAuditError(null);
    } catch (e: unknown) {
      setAudit([]);
      setAuditError(e instanceof Error ? e.message : 'Delivery audit unavailable');
    } finally {
      setAuditLoading(false);
    }
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      const s = (await api.getTelegramStatus()) as unknown as TelegramStatus;
      setStatus(s);
      setQueueStats(
        (s as unknown as { queue_stats: Record<string, unknown> }).queue_stats || queueStats,
      );
      if (s.binding.linked && linkUrl) {
        setLinkUrl(null);
        setExpiry(null);
        setMsg({ type: 'success', text: 'Telegram connected! Your chat is now linked.' });
      }
    } catch (e: unknown) {
      setMsg({
        type: 'error',
        text: e instanceof Error ? e.message : 'Failed to load Telegram status',
      });
    } finally {
      setLoading(false);
    }
  }, [linkUrl, queueStats]);

  const loadPrefs = useCallback(async () => {
    try {
      const next = await api.getTelegramPreferences();
      setPrefs(next);
      prefsRef.current = next;
      setPrefsError(null);
    } catch (e: unknown) {
      setPrefs(null);
      setPrefsError(e instanceof Error ? e.message : 'Notification preferences unavailable');
    }
  }, []);

  // Initial load
  useEffect(() => {
    refreshStatus();
    loadPrefs();
    loadAudit();
    loadStats();
    return clearPoll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Countdown ticker while a pairing token is live
  useEffect(() => {
    if (!expiry) return;
    tickRef.current = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [expiry]);

  useEffect(() => {
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, []);

  const handleConnect = useCallback(async () => {
    setMsg(null);
    try {
      const res = await api.generateTelegramLink();
      setLinkUrl(res.url);
      const expiresAt = Date.now() + res.ttl_seconds * 1000;
      setExpiry(expiresAt);
      setNow(Date.now());

      clearPoll();
      pollRef.current = setInterval(async () => {
        if (Date.now() > (expiryRef.current ?? 0)) {
          clearPoll();
          return;
        }
        try {
          const s = (await api.getTelegramStatus()) as unknown as TelegramStatus;
          if (s.binding.linked) {
            setStatus(s);
            setLinkUrl(null);
            setExpiry(null);
            clearPoll();
            setMsg({ type: 'success', text: 'Telegram successfully linked!' });
          }
        } catch (err) {
          // Transient poll failures are non-fatal: keep polling until the
          // pairing token expires, but leave a trace for debugging.
          console.error('Telegram link status poll failed:', err);
        }
      }, 2500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to generate link' });
    }
  }, [clearPoll]);

  const handleRevoke = useCallback(async () => {
    if (!confirm('Are you sure you want to unlink Telegram notifications?')) return;
    try {
      await api.revokeTelegramLink();
      setMsg({ type: 'success', text: 'Telegram unlinked successfully.' });
      await refreshStatus();
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Failed to unlink' });
    }
  }, [refreshStatus]);

  const handleTest = useCallback(async () => {
    setTesting(true);
    setMsg(null);
    try {
      const res = await api.sendTelegramTestMessage();
      setMsg({
        type: 'success',
        text: `Test alert queued (ID: ${res.notification_id || res.status})`,
      });
      setTimeout(loadAudit, 1500);
    } catch (e: unknown) {
      setMsg({
        type: 'error',
        text: e instanceof Error ? e.message : 'Failed to send test alert',
      });
    } finally {
      setTesting(false);
    }
  }, [loadAudit]);

  const savePrefs = useCallback(async (next: TelegramPreferences) => {
    const previous = prefsRef.current;
    setPrefs(next);
    prefsRef.current = next;
    try {
      await api.updateTelegramPreferences(next);
    } catch (e: unknown) {
      // Roll the optimistic update back — the server still holds `previous`.
      setPrefs(previous);
      prefsRef.current = previous;
      setMsg({
        type: 'error',
        text: e instanceof Error
          ? `Failed to update notification filters: ${e.message}`
          : 'Failed to update notification filters.',
      });
    }
  }, []);

  const applyBulk = useCallback(
    async (enabled: boolean) => {
      if (!prefs) return;
      setAdjustBusy(true);
      const updated: TelegramPreferences = {
        ...prefs,
        breakout: enabled,
        breakdown: enabled,
        instruments: INSTRUMENTS.reduce((acc, i) => ({ ...acc, [i]: enabled }), {}),
        timeframes: TIMEFRAMES.reduce((acc, t) => ({ ...acc, [t]: enabled }), {}),
        events: EVENT_GROUPS.flatMap((g) => g.items).reduce(
          (acc, it) => ({ ...acc, [it.key]: enabled }),
          {},
        ),
      };
      await savePrefs(updated);
      setAdjustBusy(false);
    },
    [prefs, savePrefs],
  );

  const handleEnableAll = useCallback(() => applyBulk(true), [applyBulk]);
  const handleDisableAll = useCallback(() => applyBulk(false), [applyBulk]);

  const handleReset = useCallback(async () => {
    if (
      !window.confirm(
        'Reset all notification subscriptions to the server defaults? This replaces your current instrument, timeframe, direction and event filters.',
      )
    ) {
      return;
    }
    setAdjustBusy(true);
    try {
      const res = await api.resetTelegramPreferences();
      setPrefs(res);
      prefsRef.current = res;
      setPrefsError(null);
      setMsg({ type: 'success', text: 'Notification preferences reset to defaults.' });
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Reset failed' });
    } finally {
      setAdjustBusy(false);
    }
  }, []);

  const handlePreview = useCallback(async () => {
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
  }, [simInstrument, simEvent, simTimeframe, simDirection]);

  const handleQuickTest = useCallback(async () => {
    setSimBusy(true);
    setMsg(null);
    try {
      const res = await api.quickTestTelegram({
        instrument: simInstrument,
        event_type: simEvent,
        candle_timeframe: simTimeframe,
        direction: simDirection,
      });
      setMsg({
        type: 'success',
        text: `Sample signal dispatched (${res.signal_id || res.status})`,
      });
      if (res.preview) setPreview(res.preview);
      setTimeout(loadAudit, 1500);
    } catch (e: unknown) {
      setMsg({ type: 'error', text: e instanceof Error ? e.message : 'Delivery probe failed' });
    } finally {
      setSimBusy(false);
    }
  }, [simInstrument, simEvent, simTimeframe, simDirection, loadAudit]);

  const refreshAll = useCallback(async () => {
    await refreshStatus();
    await Promise.all([loadStats(), loadAudit()]);
  }, [refreshStatus, loadStats, loadAudit]);

  const msLeft = Math.max(0, (expiry ?? 0) - now);
  const secLeft = Math.floor(msLeft / 1000);
  const countdown = {
    mm: String(Math.floor(secLeft / 60)).padStart(2, '0'),
    ss: String(secLeft % 60).padStart(2, '0'),
  };

  return {
    status,
    prefs,
    loading,
    msg,
    setMsg,
    linkUrl,
    expiry,
    countdown,
    testing,
    audit,
    queueStats,
    adjustBusy,
    auditLoading,
    prefsError,
    statsError,
    auditError,
    simInstrument,
    setSimInstrument,
    simEvent,
    setSimEvent,
    simTimeframe,
    setSimTimeframe,
    simDirection,
    setSimDirection,
    preview,
    simBusy,
    handleConnect,
    handleRevoke,
    handleTest,
    savePrefs,
    handleEnableAll,
    handleDisableAll,
    handleReset,
    handlePreview,
    handleQuickTest,
    refreshAll,
  };
}
