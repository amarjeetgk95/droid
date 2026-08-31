'use client';

import React, { useState, useCallback } from 'react';
import {
  Settings,
  Bot,
  KeyRound,
  Sliders,
  Save,
  CheckCircle2,
  AlertCircle,
  FileText,
  Palette,
  Send,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';

// Unified settings provider + hook
import { SettingsProvider, useSettings } from '@/components/settings/SettingsProvider';

// Tab components (the well-structured ones that already exist)
import { AIEngineTab } from '@/components/settings/AIEngineTab';
import { BrokerConnectionTab } from '@/components/settings/BrokerConnectionTab';
import { QuantitativePricingTab } from '@/components/settings/QuantitativePricingTab';
import { PaperTradingRiskTab } from '@/components/settings/PaperTradingRiskTab';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { TelegramTab } from '@/components/settings/TelegramTab';

// ============================================================================
// Tab Configuration
// ============================================================================

type TabId = 'ai' | 'broker' | 'quantitative' | 'paper' | 'preferences' | 'telegram';

interface TabConfig {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const TABS: TabConfig[] = [
  { id: 'ai', label: 'AI Engine', icon: Bot, description: 'LLM providers, models & persona' },
  { id: 'broker', label: 'Broker APIs', icon: KeyRound, description: 'Trading execution connections' },
  { id: 'quantitative', label: 'Quantitative', icon: Sliders, description: 'Pricing models & cost engine' },
  { id: 'paper', label: 'Paper Trading', icon: FileText, description: 'Virtual capital & risk rules' },
  { id: 'preferences', label: 'Preferences', icon: Palette, description: 'Theme, format & backup' },
  { id: 'telegram', label: 'Telegram', icon: Send, description: 'Signal notifications to your chat' },
];

// ============================================================================
// Settings Page Inner (uses context)
// ============================================================================

function SettingsPageInner() {
  const [activeTab, setActiveTab] = useState<TabId>('ai');

  const {
    settings,
    isDirty,
    isSaving,
    isLoading,
    validationErrors,
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
  } = useSettings();

  // --- Render loading state ---
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex items-center gap-3 text-muted-foreground text-sm">
          <div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span>Loading terminal configuration...</span>
        </div>
      </div>
    );
  }

  // --- Render active tab content ---
  const renderTabContent = () => {
    switch (activeTab) {
      case 'ai':
        return (
          <AIEngineTab
            settings={settings.ai}
            onChange={updateAI}
            errors={validationErrors}
          />
        );
      case 'broker':
        return (
          <BrokerConnectionTab
            settings={settings.broker}
            onChange={updateBroker}
            errors={validationErrors}
          />
        );
      case 'quantitative':
        return (
          <QuantitativePricingTab
            settings={settings.quantitative}
            onChange={updateQuantitative}
            errors={validationErrors}
          />
        );
      case 'paper':
        return (
          <PaperTradingRiskTab
            settings={settings.paper}
            onChange={updatePaper}
            errors={validationErrors}
          />
        );
      case 'preferences':
        return (
          <PreferencesTab
            settings={settings.preferences}
            fullSettings={settings}
            onChange={updatePreferences}
            onFullSettingsChange={replaceAllSettings}
            onResetAll={reset}
            errors={validationErrors}
          />
        );
      case 'telegram':
        return <TelegramTab />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6 pb-12 max-w-5xl mx-auto">
      {/* ================================================================= */}
      {/* Settings Top Bar                                                    */}
      {/* ================================================================= */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-card border border-border/80 rounded-2xl p-5 shadow-lg backdrop-blur-sm">
        <div className="flex items-center gap-3.5">
          <div className="bg-primary/10 border border-primary/30 p-3 rounded-xl text-primary">
            <Settings className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-foreground">Terminal Configuration</h1>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                PRO ACTIVE
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Configure AI intelligence engines, broker execution APIs, and quantitative parameters
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Save status indicator */}
          {isDirty && !saveMessage && (
            <span className="text-xs text-amber-400 flex items-center gap-1.5 bg-amber-500/10 px-3 py-1.5 rounded-lg border border-amber-500/20">
              <div className="w-1.5 h-1.5 bg-amber-400 rounded-full animate-pulse" />
              <span>Unsaved changes</span>
            </span>
          )}
          {!isDirty && lastSaved && !saveMessage && (
            <span className="text-xs text-emerald-400 flex items-center gap-1.5 bg-emerald-500/10 px-3 py-1.5 rounded-lg border border-emerald-500/20">
              <CheckCircle2 className="w-3 h-3" />
              <span>Saved</span>
            </span>
          )}

          {/* Validation error count */}
          {validationErrors.length > 0 && (
            <span className="text-xs text-destructive flex items-center gap-1.5 bg-destructive/10 px-3 py-1.5 rounded-lg border border-destructive/20">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{validationErrors.length} issue{validationErrors.length > 1 ? 's' : ''}</span>
            </span>
          )}

          {/* Toast message */}
          {saveMessage && (
            <span
              className={`text-xs flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all ${
                saveMessage.type === 'success'
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : 'text-destructive bg-destructive/10 border-destructive/20'
              }`}
            >
              {saveMessage.type === 'success' ? (
                <CheckCircle2 className="w-3.5 h-3.5" />
              ) : (
                <AlertCircle className="w-3.5 h-3.5" />
              )}
              <span className="max-w-[200px] truncate">{saveMessage.text}</span>
            </span>
          )}

          {/* Save button */}
          <button
            type="button"
            onClick={save}
            disabled={isSaving || !isDirty}
            title={isDirty ? 'Save all changes (Ctrl+S)' : 'No changes to save'}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl text-xs font-bold transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{isSaving ? 'Saving...' : 'Save Configuration'}</span>
          </button>
        </div>
      </div>

      {/* ================================================================= */}
      {/* Navigation Tabs                                                     */}
      {/* ================================================================= */}
      <div className="flex items-center gap-2 p-1.5 bg-card border border-border/80 rounded-xl overflow-x-auto">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          // Count validation errors for this tab section
          const tabErrorCount = validationErrors.filter((e) =>
            e.path.startsWith(tab.id === 'ai' ? 'ai.' : tab.id === 'broker' ? 'broker.' : tab.id + '.')
          ).length;

          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold transition-all cursor-pointer whitespace-nowrap relative ${
                isActive
                  ? 'bg-primary text-primary-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
              {tabErrorCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-destructive text-destructive-foreground rounded-full text-[9px] font-bold flex items-center justify-center">
                  {tabErrorCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Validation Summary — shown when there are errors so save blockage is actionable */}
      {validationErrors.length > 0 && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-destructive">
            <AlertCircle className="w-4 h-4" />
            <span>{validationErrors.length} validation issue{validationErrors.length > 1 ? 's' : ''} — click to jump to field</span>
          </div>
          <ul className="space-y-1">
            {validationErrors.map((e) => {
              const section = e.path.split('.')[0] as TabId;
              return (
                <li key={e.path}>
                  <button
                    type="button"
                    onClick={() => setActiveTab(section)}
                    className="text-xs text-left w-full px-2 py-1 rounded bg-card border border-border hover:border-destructive/30 text-destructive/90 hover:text-destructive font-mono flex items-center gap-2 cursor-pointer"
                  >
                    <span className="text-[10px] bg-destructive/15 px-1.5 py-0.5 rounded">{section}</span>
                    <span className="truncate">{e.path}: {e.message}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* ================================================================= */}
      {/* Active Tab Content                                                  */}
      {/* ================================================================= */}
      {renderTabContent()}
    </div>
  );
}

// ============================================================================
// Settings Page (wraps with provider)
// ============================================================================

export default function SettingsPage() {
  const { isDemoMode } = useAuth();

  // RECTIFY: Supabase is now source of truth — persist full AppSettings as JSONB
  const handleSaveToBackend = useCallback(
    async (settings: import('@/lib/settings').AppSettings) => {
      if (isDemoMode) return;
      const { toSupabasePayload } = await import('@/lib/settings');
      const payload = toSupabasePayload(settings);
      // Throws on failure so provider can show error toast; localStorage already saved as cache
      await api.updateSettings(payload as import('@/lib/types').UserSettingsUpdate);
    },
    [isDemoMode]
  );

  // RECTIFY: Hydrate from Supabase on mount — Supabase wins over localStorage
  const handleLoadFromBackend = useCallback(async (): Promise<import('@/lib/settings').AppSettings | null> => {
    if (isDemoMode) return null;
    try {
      const res = await api.getSettings();
      if (res?.app_settings && typeof res.app_settings === 'object') {
        const { mergeAppSettingsFromSupabase } = await import('@/lib/settings');
        return mergeAppSettingsFromSupabase(res.app_settings);
      }
      // No app_settings blob — keep localStorage settings (don't clobber real credentials with defaults)
      return null;
    } catch {
      return null; // offline or 404 → keep localStorage
    }
  }, [isDemoMode]);

  return (
    <SettingsProvider onSaveToBackend={handleSaveToBackend} onLoadFromBackend={handleLoadFromBackend}>
      <SettingsPageInner />
    </SettingsProvider>
  );
}
