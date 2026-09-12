'use client';

import React, { useState, useCallback, useEffect } from 'react';
import {
  Bot,
  KeyRound,
  Sliders,
  Save,
  CheckCircle2,
  AlertCircle,
  FileText,
  Palette,
  Send,
  RotateCcw,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';
import { SettingsProvider, useSettings } from '@/components/settings/SettingsProvider';
import { AIEngineTab } from '@/components/settings/AIEngineTab';
import { BrokerConnectionTab } from '@/components/settings/BrokerConnectionTab';
import { QuantitativePricingTab } from '@/components/settings/QuantitativePricingTab';
import { PaperTradingRiskTab } from '@/components/settings/PaperTradingRiskTab';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { TelegramTab } from '@/components/settings/TelegramTab';

type TabId = 'preferences' | 'ai' | 'broker' | 'quantitative' | 'paper' | 'telegram';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const TABS: TabConfig[] = [
  { id: 'preferences', label: 'Preferences', icon: Palette, description: 'Display formatting, number systems & configuration backups' },
  { id: 'ai', label: 'AI Engine', icon: Bot, description: 'Inference runtime, model routing & analyst persona' },
  { id: 'broker', label: 'Broker Gateways', icon: KeyRound, description: 'Market universe, OAuth exchanges & live execution sessions' },
  { id: 'quantitative', label: 'Quant Valuation', icon: Sliders, description: 'Options pricing models, Greeks solvers & transaction friction' },
  { id: 'paper', label: 'Paper Trading', icon: FileText, description: 'Virtual capital, risk boundaries & execution guardrails' },
  { id: 'telegram', label: 'Telegram Alerts', icon: Send, description: 'Signal notification routing & personal chat delivery' },
];

function SettingsSkeleton() {
  return (
    <div className="ds-page animate-pulse">
      <div className="page-hero h-20 bg-[var(--ds-surface)]" />
      <div className="card h-12 bg-[var(--ds-surface)]" />
      <div className="space-y-4">
        <div className="card h-48 bg-[var(--ds-surface)]" />
        <div className="card h-64 bg-[var(--ds-surface)]" />
      </div>
    </div>
  );
}

function SettingsPageInner() {
  const [activeTab, setActiveTab] = useState<TabId>('preferences');

  const handleTabChange = useCallback((id: TabId) => {
    setActiveTab(id);
  }, []);

  const {
    settings,
    isDirty,
    isDirtySections,
    isSaving,
    isLoading,
    validationErrors,
    sectionErrors,
    lastSaved,
    saveMessage,
    updateBroker,
    updateQuantitative,
    updateAI,
    updatePaper,
    updatePreferences,
    replaceAllSettings,
    save,
    reset,
  } = useSettings() as unknown as {
    settings: import('@/lib/settings').AppSettings;
    isDirty: boolean;
    isDirtySections: Record<string, boolean>;
    isSaving: boolean;
    isLoading: boolean;
    validationErrors: { path: string; message: string }[];
    sectionErrors: Record<string, { path: string; message: string }[]>;
    lastSaved: Date | null;
    saveMessage: { type: 'success' | 'error'; text: string } | null;
    updateBroker: (u: Partial<import('@/lib/settings').BrokerSettings>) => void;
    updateQuantitative: (u: Partial<import('@/lib/settings').QuantitativeSettings>) => void;
    updateAI: (u: Partial<import('@/lib/settings').AISettings>) => void;
    updatePaper: (u: Partial<import('@/lib/settings').PaperTradingSettings>) => void;
    updatePreferences: (u: Partial<import('@/lib/settings').PreferencesSettings>) => void;
    replaceAllSettings: (s: import('@/lib/settings').AppSettings) => void;
    save: () => Promise<void>;
    reset: () => void;
  };

  // Keyboard shortcut: Cmd/Ctrl + S to trigger Save
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        if (isDirty && !isSaving) {
          save();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isDirty, isSaving, save]);

  if (isLoading) {
    return <SettingsSkeleton />;
  }

  const currentTabConfig = TABS.find((t) => t.id === activeTab) || TABS[0];

  return (
    <div className="ds-page">
      {/* 1. Header Toolbar (Page Hero) */}
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>Settings</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>SYSTEM CONFIG</span>
            </div>
            <p className="muted num">
              Execution gateways · Risk boundaries · Quantitative models · Workspace preferences
            </p>
          </div>

          <span className="spacer" />

          <div className="flex items-center gap-2.5">
            {saveMessage && (
              <span
                className={`badge ${
                  saveMessage.type === 'success' ? 'b-bull' : 'b-bear'
                }`}
                style={{ fontSize: 11 }}
              >
                {saveMessage.type === 'success' ? (
                  <CheckCircle2 className="w-3.5 h-3.5" />
                ) : (
                  <AlertCircle className="w-3.5 h-3.5" />
                )}
                <span className="truncate max-w-[220px]">{saveMessage.text}</span>
              </span>
            )}

            {!isDirty && lastSaved && !saveMessage && (
              <span className="muted num text-xs flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--ds-bull)]" />
                Saved {new Date(lastSaved).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}

            {isDirty && (
              <div className="flex items-center gap-2">
                <span className="muted num text-xs flex items-center gap-1.5 mr-1">
                  <span className="w-2 h-2 rounded-full bg-[var(--ds-warn)] animate-pulse" />
                  Unsaved changes
                </span>
                <button
                  type="button"
                  onClick={reset}
                  disabled={isSaving}
                  className="btn btn-sm"
                >
                  Discard
                </button>
                <button
                  type="button"
                  onClick={save}
                  disabled={isSaving}
                  className="btn btn-sm btn-primary flex items-center gap-1.5"
                >
                  {isSaving ? (
                    <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Save className="w-3.5 h-3.5" />
                  )}
                  <span>{isSaving ? 'Saving…' : 'Save Changes'}</span>
                  <kbd className="hidden sm:inline-block ml-0.5 text-[10px] font-mono opacity-80">⌘S</kbd>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* 2. Validation Errors (if any) */}
      {validationErrors.length > 0 && (
        <div className="card card-pad border-[var(--ds-bear)]/30 bg-[var(--ds-bear-wash)] space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-[var(--ds-bear-strong)]">
            <AlertCircle className="w-4 h-4 text-[var(--ds-bear)]" />
            <span>{validationErrors.length} configuration error(s) need attention</span>
          </div>
          <div className="flex flex-wrap gap-2 pt-0.5">
            {validationErrors.map((e) => {
              const section = e.path.split('.')[0] as TabId;
              return (
                <button
                  key={e.path}
                  type="button"
                  onClick={() => handleTabChange(section)}
                  className="badge b-bear cursor-pointer hover:opacity-80 transition-opacity"
                >
                  <span className="capitalize">{section}</span>
                  <span className="mx-1 opacity-60">·</span>
                  <span className="font-mono">{e.message}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Segmented Navigation Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="seg overflow-x-auto max-w-full" role="tablist" aria-label="Settings navigation">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            const isTabDirty = !!(isDirtySections as Record<string, boolean>)?.[tab.id];
            const tabErrorCount =
              sectionErrors?.[tab.id]?.length ??
              validationErrors.filter((e) => e.path.startsWith(tab.id + '.')).length;

            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => handleTabChange(tab.id)}
                data-active={isActive}
                className="seg-btn flex items-center gap-1.5"
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{tab.label}</span>
                {isTabDirty && (
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-[var(--ds-warn)] shrink-0"
                    title="Unsaved changes"
                  />
                )}
                {tabErrorCount > 0 && (
                  <span className="badge b-bear" style={{ fontSize: '9px', padding: '0 4px' }}>
                    {tabErrorCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="text-[11px] muted num hidden md:block">
          {currentTabConfig.description}
        </div>
      </div>

      {/* 4. Active Tab Content Canvas */}
      <main className="space-y-4">
        <div hidden={activeTab !== 'preferences'} className={activeTab !== 'preferences' ? 'hidden' : 'block'}>
          <PreferencesTab
            settings={settings.preferences}
            fullSettings={settings}
            onChange={updatePreferences}
            onFullSettingsChange={replaceAllSettings}
            onResetAll={reset}
            errors={validationErrors}
          />
        </div>

        <div hidden={activeTab !== 'ai'} className={activeTab !== 'ai' ? 'hidden' : 'block'}>
          <AIEngineTab settings={settings.ai} onChange={updateAI} errors={validationErrors} />
        </div>

        <div hidden={activeTab !== 'broker'} className={activeTab !== 'broker' ? 'hidden' : 'block'}>
          <BrokerConnectionTab
            settings={settings.broker}
            fullSettings={settings}
            onChange={updateBroker}
            errors={validationErrors}
          />
        </div>

        <div hidden={activeTab !== 'quantitative'} className={activeTab !== 'quantitative' ? 'hidden' : 'block'}>
          <QuantitativePricingTab
            settings={settings.quantitative}
            onChange={updateQuantitative}
            errors={validationErrors}
          />
        </div>

        <div hidden={activeTab !== 'paper'} className={activeTab !== 'paper' ? 'hidden' : 'block'}>
          <PaperTradingRiskTab
            settings={settings.paper}
            onChange={updatePaper}
            errors={validationErrors}
          />
        </div>

        <div hidden={activeTab !== 'telegram'} className={activeTab !== 'telegram' ? 'hidden' : 'block'}>
          <TelegramTab />
        </div>
      </main>
    </div>
  );
}

export default function SettingsPage() {
  const { isDemoMode } = useAuth();

  const handleSaveToBackend = useCallback(
    async (settings: import('@/lib/settings').AppSettings) => {
      if (isDemoMode) return;
      const { toSupabasePayload } = await import('@/lib/settings');
      const payload = toSupabasePayload(settings);
      await api.updateSettings(payload as import('@/lib/types').UserSettingsUpdate);
    },
    [isDemoMode]
  );

  const handleLoadFromBackend = useCallback(async (): Promise<import('@/lib/settings').AppSettings | null> => {
    if (isDemoMode) return null;
    try {
      const res = await api.getSettings();
      if (res?.app_settings && typeof res.app_settings === 'object') {
        const { mergeAppSettingsFromSupabase } = await import('@/lib/settings');
        return mergeAppSettingsFromSupabase(res.app_settings);
      }
      return null;
    } catch {
      return null;
    }
  }, [isDemoMode]);

  return (
    <SettingsProvider onSaveToBackend={handleSaveToBackend} onLoadFromBackend={handleLoadFromBackend}>
      <SettingsPageInner />
    </SettingsProvider>
  );
}
