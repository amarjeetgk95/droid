'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, Link2, RefreshCw, RotateCcw, Save, Send, Unlink, Upload } from 'lucide-react';
import { api } from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import { getFieldError, validateSettings, type ValidationError } from '@/lib/settingsSchema';
import {
  exportSettingsJson,
  getStoredSettings,
  importSettingsJson,
  resetStoredSettings,
  saveStoredSettings,
} from '@/lib/settingsStorage';
import { mergeAppSettingsFromSupabase, toSupabasePayload } from '@/lib/settingsSupabase';
import type { AppSettings } from '@/lib/settingsTypes';
import type { BrokerTokenStatus } from '@/lib/api/tokens';
import { Panel } from '@/components/ui/Panel';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/toast';
import { SelectField, TextField, ToggleField } from './fields';
import { AiSettingsSection } from './AiSettingsSection';

type SettingsSectionId = 'broker' | 'quantitative' | 'ai' | 'paper' | 'preferences' | 'telegram';

const SECTION_LABELS: Array<[SettingsSectionId, string]> = [
  ['broker', 'Broker & Data'],
  ['quantitative', 'Quantitative'],
  ['ai', 'AI Providers'],
  ['paper', 'Paper Trading'],
  ['preferences', 'Preferences'],
  ['telegram', 'Telegram'],
];

const ERROR_SECTION: Record<string, SettingsSectionId> = {
  broker: 'broker',
  quantitative: 'quantitative',
  ai: 'ai',
  paper: 'paper',
  preferences: 'preferences',
};

function BrokerSection() {
  const { push } = useToast();
  const [status, setStatus] = useState<BrokerTokenStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api.getBrokerTokenStatus();
      setStatus(result.data ?? null);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    async (action: () => Promise<unknown>, label: string) => {
      setBusy(true);
      try {
        await action();
        await load();
        push('success', label);
      } catch (err) {
        push('error', errorMessage(err, `${label} failed`));
      } finally {
        setBusy(false);
      }
    },
    [load, push],
  );

  return (
    <Panel title="Broker & Data Feed" meta={status?.provider ?? 'fyers'}>
      <p className="sg-note">
        FYERS appId/secret are read from the backend environment (backend/.env). Values entered here would be
        ignored, so this module reports the live token state instead.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-x-4">
        <div className="sg-kv">
          <span className="l">Token state</span>
          <span className="v">{status?.state ?? '—'}</span>
        </div>
        <div className="sg-kv">
          <span className="l">Valid</span>
          <span className={`v ${status?.is_token_valid ? 'pos-num' : 'neg-num'}`}>
            {status ? (status.is_token_valid ? 'YES' : 'NO') : '—'}
          </span>
        </div>
        <div className="sg-kv">
          <span className="l">Uptime</span>
          <span className="v">
            {status?.uptime_seconds != null ? `${Math.round(status.uptime_seconds / 60)}m` : '—'}
          </span>
        </div>
        <div className="sg-kv">
          <span className="l">Data lag</span>
          <span className="v">{status?.data_lag_seconds != null ? `${status.data_lag_seconds}s` : '—'}</span>
        </div>
        <div className="sg-kv">
          <span className="l">Reconnects</span>
          <span className="v">{status?.reconnect_count ?? '—'}</span>
        </div>
        <div className="sg-kv">
          <span className="l">Subscriptions</span>
          <span className="v">{status?.subscription_count ?? '—'}</span>
        </div>
      </div>
      {status?.last_error ? <p className="sg-err mt-2">{status.last_error}</p> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-ic" disabled={busy} onClick={() => void run(() => api.refreshBrokerToken(), 'Token refreshed')}>
          <RefreshCw size={13} />
          Refresh token
        </button>
        <button type="button" className="btn" disabled={busy} onClick={() => void run(() => api.runTokenDiagnostics(), 'Diagnostics complete')}>
          Run diagnostics
        </button>
      </div>
    </Panel>
  );
}

function TelegramSection() {
  const { push } = useToast();
  const [status, setStatus] = useState<{
    bot_configured: boolean;
    bot_username: string | null;
    webhook_configured: boolean;
    binding: { linked: boolean; telegram_chat_id: string | null; linked_at: number | null; status: string };
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await api.getTelegramStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    async (action: () => Promise<unknown>, label: string) => {
      setBusy(true);
      try {
        await action();
        await load();
        push('success', label);
      } catch (err) {
        push('error', errorMessage(err, `${label} failed`));
      } finally {
        setBusy(false);
      }
    },
    [load, push],
  );

  const handleLink = useCallback(async () => {
    setBusy(true);
    try {
      const result = await api.generateTelegramLink();
      if (result.url) window.open(result.url, '_blank', 'noopener,noreferrer');
      push('info', 'Open the Telegram link to finish pairing.');
    } catch (err) {
      push('error', errorMessage(err, 'Link generation failed'));
    } finally {
      setBusy(false);
    }
  }, [push]);

  return (
    <Panel title="Telegram Alerts" meta={status?.bot_configured ? status.bot_username ?? 'configured' : 'not configured'}>
      <div className="grid grid-cols-2 gap-x-4">
        <div className="sg-kv">
          <span className="l">Bot</span>
          <span className={`v ${status?.bot_configured ? 'pos-num' : 'neg-num'}`}>
            {status?.bot_configured ? 'READY' : 'MISSING TOKEN'}
          </span>
        </div>
        <div className="sg-kv">
          <span className="l">Webhook</span>
          <span className="v">{status?.webhook_configured ? 'SET' : 'NOT SET'}</span>
        </div>
        <div className="sg-kv">
          <span className="l">Linked chat</span>
          <span className="v">{status?.binding.linked ? status.binding.telegram_chat_id ?? 'YES' : 'NO'}</span>
        </div>
        <div className="sg-kv">
          <span className="l">Link status</span>
          <span className="v">{status?.binding.status ?? '—'}</span>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn btn-ic" disabled={busy || !status?.bot_configured} onClick={() => void handleLink()}>
          <Link2 size={13} />
          Link Telegram
        </button>
        <button
          type="button"
          className="btn btn-ic"
          disabled={busy || !status?.binding.linked}
          onClick={() => void run(() => api.revokeTelegramLink(), 'Telegram unlinked')}
        >
          <Unlink size={13} />
          Revoke
        </button>
        <button
          type="button"
          className="btn btn-ic"
          disabled={busy || !status?.binding.linked}
          onClick={() => void run(() => api.sendTelegramTestMessage(), 'Test message sent')}
        >
          <Send size={13} />
          Send test
        </button>
      </div>
    </Panel>
  );
}

export function SettingsModule() {
  const { push } = useToast();
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [section, setSection] = useState<SettingsSectionId>('broker');
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const stored = getStoredSettings();
    setSettings(stored);
    void (async () => {
      try {
        const remote = await api.getSettings();
        if (!cancelled && remote?.app_settings) {
          const merged = mergeAppSettingsFromSupabase(remote.app_settings);
          setSettings(merged);
          saveStoredSettings(merged);
        }
      } catch {
        // Offline: local settings remain authoritative for this session.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const patchSection = useCallback(
    <K extends keyof AppSettings>(key: K, patch: Partial<AppSettings[K]>) => {
      setSettings((prev) =>
        prev ? { ...prev, [key]: { ...(prev[key] as object), ...patch } } : prev,
      );
      setDirty(true);
    },
    [],
  );

  const handleSave = useCallback(async () => {
    if (!settings) return;
    const validation = validateSettings(settings);
    if (!validation.success) {
      setErrors(validation.errors);
      const first = validation.errors[0];
      const firstSection = first ? ERROR_SECTION[first.path.split('.')[0]] : undefined;
      if (firstSection) setSection(firstSection);
      push('error', first ? `${first.path}: ${first.message}` : 'Validation failed');
      return;
    }
    setErrors([]);
    setSaving(true);
    try {
      const localSaved = saveStoredSettings(settings);
      await api.updateSettings(toSupabasePayload(settings));
      setDirty(false);
      push(localSaved ? 'success' : 'warning', 'Settings saved', localSaved ? 'Synced to backend and local storage.' : 'Backend saved; local storage write failed.');
    } catch (err) {
      push('error', errorMessage(err, 'Settings save failed'));
    } finally {
      setSaving(false);
    }
  }, [push, settings]);

  const handleReset = useCallback(async () => {
    const defaults = resetStoredSettings();
    setSettings(defaults);
    setErrors([]);
    try {
      await api.updateSettings(toSupabasePayload(defaults));
      setDirty(false);
      push('info', 'Settings reset to defaults.');
    } catch (err) {
      setDirty(true);
      push('error', errorMessage(err, 'Reset saved locally but backend sync failed'));
    }
  }, [push]);

  const handleExport = useCallback(() => {
    if (!settings) return;
    const json = exportSettingsJson(settings);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'droid-settings.json';
    anchor.click();
    URL.revokeObjectURL(url);
  }, [settings]);

  const handleImport = useCallback(
    async (file: File | null) => {
      if (!file) return;
      try {
        const text = await file.text();
        const imported = importSettingsJson(text);
        setSettings(imported);
        setDirty(true);
        setErrors([]);
        push('info', 'Settings imported. Review and save to persist.');
      } catch (err) {
        push('error', errorMessage(err, 'Import failed'));
      }
    },
    [push],
  );

  const activeErrors = useMemo(() => errors, [errors]);

  if (!settings) {
    return (
      <div className="panel">
        <p className="sg-empty">Loading settings…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <section className="ds-commandbar">
        <div className="ds-title">
          <h2>Settings</h2>
          <span className={`badge ${dirty ? 'b-warn' : 'b-neut'}`}>{dirty ? 'UNSAVED' : 'SYNCED'}</span>
        </div>
        <div className="ds-filters">
          <label className="btn btn-ic cursor-pointer">
            <Upload size={13} />
            Import JSON
            <input
              type="file"
              accept="application/json"
              className="hidden"
              onChange={(event) => void handleImport(event.target.files?.[0] ?? null)}
            />
          </label>
          <button type="button" className="btn btn-ic" onClick={handleExport}>
            <Download size={13} />
            Export JSON
          </button>
          <button type="button" className="btn btn-ic" onClick={() => setResetOpen(true)}>
            <RotateCcw size={13} />
            Reset
          </button>
          <button type="button" className="btn btn-primary btn-ic" disabled={saving || !dirty} onClick={() => void handleSave()}>
            <Save size={13} />
            {saving ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      </section>

      <div className="flex flex-col gap-3 md:flex-row">
        <nav className="tabbar h-fit flex-row gap-1 overflow-x-auto md:w-[190px] md:flex-col" aria-label="Settings sections">
          {SECTION_LABELS.map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`tab ${section === id ? 'is-active' : ''}`}
              aria-current={section === id ? 'true' : undefined}
              onClick={() => setSection(id)}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {section === 'broker' ? <BrokerSection /> : null}

          {section === 'quantitative' ? (
            <Panel title="Quantitative Defaults">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <TextField
                  label="Risk-free rate (0–1)"
                  type="number"
                  min={0}
                  max={1}
                  step={0.005}
                  value={settings.quantitative.riskFreeRate}
                  error={getFieldError(activeErrors, 'quantitative.riskFreeRate')}
                  onChange={(next) => patchSection('quantitative', { riskFreeRate: Number(next) })}
                />
                <SelectField
                  label="Time convention"
                  value={settings.quantitative.timeConvention}
                  options={['ACT365', 'ACT360', 'TradingDays252'] as const}
                  onChange={(next) => patchSection('quantitative', { timeConvention: next })}
                />
                <SelectField
                  label="Default pricing model"
                  value={settings.quantitative.defaultPricingModel}
                  options={['FUTURES_BLACK76', 'SPOT_BLACK_SCHOLES'] as const}
                  onChange={(next) => patchSection('quantitative', { defaultPricingModel: next })}
                />
                <SelectField
                  label="IV solver"
                  value={settings.quantitative.ivMethod}
                  options={['BRENT', 'NEWTON_RAPHSON'] as const}
                  onChange={(next) => patchSection('quantitative', { ivMethod: next })}
                />
                <TextField
                  label="Brokerage per order (₹)"
                  type="number"
                  min={0}
                  step={1}
                  value={settings.quantitative.brokeragePerOrder}
                  error={getFieldError(activeErrors, 'quantitative.brokeragePerOrder')}
                  onChange={(next) => patchSection('quantitative', { brokeragePerOrder: Number(next) })}
                />
                <TextField
                  label="Slippage (%)"
                  type="number"
                  min={0}
                  max={10}
                  step={0.01}
                  value={settings.quantitative.slippagePct}
                  error={getFieldError(activeErrors, 'quantitative.slippagePct')}
                  onChange={(next) => patchSection('quantitative', { slippagePct: Number(next) })}
                />
              </div>
            </Panel>
          ) : null}

          {section === 'ai' ? (
            <Panel title="AI Providers" meta={settings.ai.connectionMode ?? 'OpenRouter'}>
              <AiSettingsSection
                value={settings.ai}
                errors={activeErrors}
                onChange={(patch) => patchSection('ai', patch)}
              />
            </Panel>
          ) : null}

          {section === 'paper' ? (
            <Panel title="Paper Trading Defaults">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <TextField
                  label="Initial capital (₹)"
                  type="number"
                  min={10_000}
                  step={10_000}
                  value={settings.paper.initialCapital}
                  error={getFieldError(activeErrors, 'paper.initialCapital')}
                  onChange={(next) => patchSection('paper', { initialCapital: Number(next) })}
                />
                <TextField
                  label="Auto square-off time (IST)"
                  type="time"
                  value={settings.paper.autoSquareOffTime}
                  error={getFieldError(activeErrors, 'paper.autoSquareOffTime')}
                  onChange={(next) => patchSection('paper', { autoSquareOffTime: next })}
                />
                <TextField
                  label="Max capital per trade (%)"
                  type="number"
                  min={1}
                  max={100}
                  step={0.5}
                  value={settings.paper.maxCapitalPerTradePct}
                  error={getFieldError(activeErrors, 'paper.maxCapitalPerTradePct')}
                  onChange={(next) => patchSection('paper', { maxCapitalPerTradePct: Number(next) })}
                />
                <TextField
                  label="Max daily drawdown halt (%)"
                  type="number"
                  min={1}
                  max={100}
                  step={0.5}
                  value={settings.paper.maxDailyDrawdownHaltPct}
                  error={getFieldError(activeErrors, 'paper.maxDailyDrawdownHaltPct')}
                  onChange={(next) => patchSection('paper', { maxDailyDrawdownHaltPct: Number(next) })}
                />
                <ToggleField
                  label="Require order confirmation"
                  checked={settings.paper.requireOrderConfirm}
                  onChange={(next) => patchSection('paper', { requireOrderConfirm: next })}
                />
                <ToggleField
                  label="Allow overnight positions"
                  checked={settings.paper.allowOvernightPositions}
                  onChange={(next) => patchSection('paper', { allowOvernightPositions: next })}
                />
              </div>
              <div className="mt-3">
                <button
                  type="button"
                  className="btn"
                  onClick={() =>
                    void api
                      .setPaperWalletCapital(Number(settings.paper.initialCapital))
                      .then(() => push('success', 'Paper wallet capital applied.'))
                      .catch((err) => push('error', errorMessage(err, 'Wallet update failed')))
                  }
                >
                  Apply capital to paper wallet
                </button>
              </div>
            </Panel>
          ) : null}

          {section === 'preferences' ? (
            <Panel title="Preferences">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <TextField label="Theme" value="light (fixed)" onChange={() => {}} />
                <SelectField
                  label="Number format"
                  value={settings.preferences.numberFormat}
                  options={['INDIAN', 'INTERNATIONAL'] as const}
                  onChange={(next) => patchSection('preferences', { numberFormat: next })}
                />
                <SelectField
                  label="Default index"
                  value={settings.preferences.defaultIndexSymbol}
                  options={['NIFTY', 'BANKNIFTY', 'SENSEX'] as const}
                  onChange={(next) => patchSection('preferences', { defaultIndexSymbol: next })}
                />
              </div>
            </Panel>
          ) : null}

          {section === 'telegram' ? <TelegramSection /> : null}
        </div>
      </div>

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        tone="danger"
        confirmLabel="Reset to defaults"
        requireTypedConfirmation="RESET"
        title="Reset all settings to defaults?"
        description="Local and backend settings are replaced with factory defaults. API keys are cleared."
        onConfirm={handleReset}
      />
    </div>
  );
}
