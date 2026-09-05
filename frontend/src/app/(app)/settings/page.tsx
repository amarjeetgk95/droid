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
    <div className="max-w-5xl mx-auto space-y-6 animate-pulse py-2">
      <div className="h-10 w-48 bg-muted/60 rounded-lg" />
      <div className="flex gap-8">
        <div className="w-56 h-72 bg-muted/40 rounded-xl hidden md:block" />
        <div className="flex-1 space-y-4">
          <div className="h-44 bg-muted/40 rounded-xl" />
          <div className="h-56 bg-muted/40 rounded-xl" />
        </div>
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
    <div className="max-w-5xl mx-auto pb-24 space-y-6">
      {/* 1. Header Area */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/50 pb-5">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">Settings</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Configure algorithmic models, execution gateways, and workspace preferences.
          </p>
        </div>

        <div className="flex items-center gap-3 text-xs">
          {saveMessage && (
            <span
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${
                saveMessage.type === 'success'
                  ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20'
                  : 'bg-destructive/10 text-destructive border-destructive/20'
              }`}
            >
              {saveMessage.type === 'success' ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <AlertCircle className="w-3.5 h-3.5" />
              )}
              <span className="truncate max-w-[200px]">{saveMessage.text}</span>
            </span>
          )}

          {!isDirty && lastSaved && !saveMessage && (
            <span className="text-[11px] text-muted-foreground font-mono flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Saved {new Date(lastSaved).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      </div>

      {/* 2. Validation Errors Alert (if any) */}
      {validationErrors.length > 0 && (
        <div className="bg-card border border-border/60 rounded-lg p-3.5 space-y-2">
          <div className="flex items-center gap-2 text-xs font-medium text-foreground">
            <AlertCircle className="w-4 h-4 text-destructive" />
            <span>{validationErrors.length} configuration error(s) need attention</span>
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {validationErrors.map((e) => {
              const section = e.path.split('.')[0] as TabId;
              return (
                <button
                  key={e.path}
                  type="button"
                  onClick={() => handleTabChange(section)}
                  className="text-[11px] px-2.5 py-1 rounded-md bg-secondary/50 border border-border/60 hover:bg-secondary text-muted-foreground hover:text-foreground flex items-center gap-1.5 cursor-pointer transition-colors"
                >
                  <span className="capitalize">{section}</span>
                  <span className="text-destructive">·</span>
                  <span className="font-mono">{e.message}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* 3. Master-Detail Layout */}
      <div className="flex flex-col md:flex-row gap-8 items-start">
        {/* Left Sub-Navigation (Desktop Sidebar) */}
        <aside className="w-full md:w-56 shrink-0 md:sticky md:top-4 space-y-1">
          {/* Mobile horizontal scrollable pill tabs */}
          <div className="md:hidden flex items-center gap-1 p-1 bg-secondary/50 border border-border/50 rounded-lg overflow-x-auto">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              const isTabDirty = !!(isDirtySections as Record<string, boolean>)?.[tab.id];
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => handleTabChange(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors cursor-pointer ${
                    isActive
                      ? 'bg-card text-foreground shadow-2xs font-semibold'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  <span>{tab.label}</span>
                  {isTabDirty && <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />}
                </button>
              );
            })}
          </div>

          {/* Desktop vertical sidebar navigation */}
          <nav className="hidden md:block space-y-1" aria-label="Settings navigation">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              const tabErrorCount =
                sectionErrors?.[tab.id]?.length ??
                validationErrors.filter((e) => e.path.startsWith(tab.id + '.')).length;
              const isTabDirty = !!(isDirtySections as Record<string, boolean>)?.[tab.id];

              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => handleTabChange(tab.id)}
                  aria-selected={isActive}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all text-left cursor-pointer ${
                    isActive
                      ? 'bg-secondary text-foreground font-semibold shadow-2xs'
                      : 'text-muted-foreground hover:text-foreground hover:bg-secondary/40'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Icon
                      className={`w-4 h-4 shrink-0 transition-colors ${
                        isActive ? 'text-foreground' : 'text-muted-foreground'
                      }`}
                    />
                    <span className="truncate">{tab.label}</span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {isTabDirty && (
                      <span
                        className="w-1.5 h-1.5 bg-amber-500 rounded-full"
                        title="Unsaved changes"
                      />
                    )}
                    {tabErrorCount > 0 && (
                      <span className="px-1.5 py-0.5 rounded-md bg-secondary border border-border/60 text-muted-foreground text-[10px] font-mono">
                        {tabErrorCount}
                      </span>
                    )}
                  </div>
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Right Content Canvas */}
        <main className="flex-1 min-w-0 max-w-3xl w-full space-y-4">
          {/* Active section header info */}
          <div className="space-y-1">
            <h2 className="text-base font-semibold tracking-tight text-foreground">
              {currentTabConfig.label}
            </h2>
            <p className="text-xs text-muted-foreground">{currentTabConfig.description}</p>
          </div>

          {/* Keep-alive tab mounts */}
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

      {/* 4. Floating Unsaved Changes Dock */}
      {isDirty && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-3.5 px-4 py-2.5 rounded-full bg-card border border-border shadow-md text-xs">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="font-medium text-foreground">Unsaved changes</span>
            </div>

            <div className="h-4 w-px bg-border/80" />

            <button
              type="button"
              onClick={reset}
              disabled={isSaving}
              className="text-xs text-muted-foreground hover:text-foreground font-medium transition-colors cursor-pointer px-1.5 py-0.5 rounded"
            >
              Discard
            </button>

            <button
              type="button"
              onClick={save}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground text-xs font-semibold rounded-full shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
            >
              {isSaving ? (
                <span className="w-3 h-3 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              <span>{isSaving ? 'Saving…' : 'Save Changes'}</span>
              <kbd className="hidden sm:inline-block ml-1 text-[10px] font-mono opacity-60">⌘S</kbd>
            </button>
          </div>
        </div>
      )}
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
