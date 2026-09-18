'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, RefreshCw, Save, Settings2 } from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import { api } from '@/lib/api';
import { SettingsProvider, useSettings } from '@/components/settings/SettingsProvider';
import { SettingsSidebar } from '@/components/settings/SettingsSidebar';
import {
  isSaveableTab,
  SETTINGS_TAB_IDS,
  DEFAULT_SETTINGS_TAB,
  type SettingsTabId,
} from '@/components/settings/registry';
import { useEnumQueryParam, useQueryParamsWriter } from '@/lib/urlState';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { AIEngineTab } from '@/components/settings/AIEngineTab';
import { BrokerConnectionTab } from '@/components/settings/BrokerConnectionTab';
import { QuantitativePricingTab } from '@/components/settings/QuantitativePricingTab';
import { PaperTradingRiskTab } from '@/components/settings/PaperTradingRiskTab';
import { TelegramTab } from '@/components/settings/TelegramTab';
import { MonitoringTab } from '@/components/settings/MonitoringTab';
import { MLOperationsTab } from '@/components/settings/MLOperationsTab';
import { SystemNerveTab } from '@/components/settings/SystemNerveTab';
import {
  mergeAppSettingsFromSupabase,
  toSupabasePayload,
  type AppSettings,
} from '@/lib/settings';
import type { UserSettingsUpdate } from '@/lib/types';

function SettingsDesk() {
  const tabParam = useEnumQueryParam('tab', SETTINGS_TAB_IDS, DEFAULT_SETTINGS_TAB);
  const setQueryParams = useQueryParamsWriter();
  const [activeTab, setActiveTab] = useState<SettingsTabId>(tabParam);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setActiveTab(tabParam);
  }, [tabParam]);

  const handleTabChange = useCallback(
    (nextTab: SettingsTabId) => {
      setActiveTab(nextTab);
      setQueryParams({ tab: nextTab === DEFAULT_SETTINGS_TAB ? null : nextTab });
    },
    [setQueryParams],
  );

  const {
    settings,
    isDirty,
    isDirtySections,
    isSaving,
    isSavingSection,
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
    save,
    saveSection,
    reset,
    importJson,
  } = useSettings();

  const errorCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const [section, errors] of Object.entries(sectionErrors)) {
      counts[section] = errors.length;
    }
    return counts;
  }, [sectionErrors]);

  const renderTab = () => {
    switch (activeTab) {
      case 'preferences':
        return (
          <PreferencesTab
            settings={settings.preferences}
            fullSettings={settings}
            onChange={updatePreferences}
            onImportJson={importJson}
            onResetAll={reset}
            errors={sectionErrors.preferences}
          />
        );
      case 'ai':
        return <AIEngineTab settings={settings.ai} onChange={updateAI} errors={sectionErrors.ai} />;
      case 'broker':
        return (
          <BrokerConnectionTab
            settings={settings.broker}
            fullSettings={settings}
            onChange={updateBroker}
          />
        );
      case 'quantitative':
        return (
          <QuantitativePricingTab
            settings={settings.quantitative}
            onChange={updateQuantitative}
            errors={sectionErrors.quantitative}
          />
        );
      case 'paper':
        return (
          <PaperTradingRiskTab
            settings={settings.paper}
            onChange={updatePaper}
            errors={sectionErrors.paper}
          />
        );
      case 'telegram':
        return <TelegramTab />;
      case 'monitoring':
        return <MonitoringTab />;
      case 'ml':
        return <MLOperationsTab />;
      case 'system':
        return <SystemNerveTab />;
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <div className="ds-page">
        <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <RefreshCw className="w-4 h-4 animate-spin text-[var(--ds-ink-3)]" />
          <span className="muted" style={{ fontSize: 13 }}>Loading terminal configuration…</span>
        </div>
      </div>
    );
  }

  const canSectionSave = isSaveableTab(activeTab);

  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <Settings2 className="w-4 h-4 text-[var(--ds-ink-3)]" />
              <h1>Terminal Configuration</h1>
            </div>
            <p>Broker gateways, AI engine, quantitative kernel &amp; app preferences</p>
          </div>
          <span className="spacer" />

          {isDirty && !saveMessage ? (
            <span className="badge b-warn" style={{ fontSize: 11 }}>
              Unsaved changes
            </span>
          ) : null}
          {!isDirty && lastSaved && !saveMessage ? (
            <span className="badge b-bull" style={{ fontSize: 11 }}>
              Saved
            </span>
          ) : null}
          {validationErrors.length > 0 ? (
            <span className="badge b-bear" style={{ fontSize: 11 }}>
              {validationErrors.length} issue{validationErrors.length > 1 ? 's' : ''}
            </span>
          ) : null}
          {saveMessage ? (
            <span
              className={`badge ${saveMessage.type === 'success' ? 'b-bull' : 'b-bear'}`}
              style={{ fontSize: 11 }}
              title={saveMessage.text}
            >
              {saveMessage.type === 'success' ? (
                <CheckCircle2 className="w-3 h-3" />
              ) : (
                <AlertCircle className="w-3 h-3" />
              )}
              <span className="max-w-[220px] truncate">{saveMessage.text}</span>
            </span>
          ) : null}

          {canSectionSave && isDirtySections[activeTab] ? (
            <button
              type="button"
              className="btn"
              disabled={isSavingSection[activeTab] || isSaving}
              onClick={() => void saveSection(activeTab)}
              title={`Save only the ${activeTab} section`}
            >
              {isSavingSection[activeTab] ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Save className="w-3.5 h-3.5" />
              )}
              Save {activeTab}
            </button>
          ) : null}

          <button
            type="button"
            className="btn btn-primary"
            disabled={isSaving || !isDirty}
            onClick={() => void save()}
            title={isDirty ? 'Save all changes (Ctrl+S)' : 'No changes to save'}
          >
            {isSaving ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            {isSaving ? 'Saving…' : 'Save all'}
          </button>
        </div>
      </header>

      {validationErrors.length > 0 ? (
        <div className="notice notice--down" style={{ fontSize: 12 }}>
          <span>
            {validationErrors.length} validation issue{validationErrors.length > 1 ? 's' : ''} —{' '}
            {validationErrors
              .slice(0, 2)
              .map((e) => `${e.path}: ${e.message}`)
              .join(' · ')}
            {validationErrors.length > 2 ? ' · …' : ''}
          </span>
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-[250px_minmax(0,1fr)] gap-5 items-start">
        <SettingsSidebar
          activeTab={activeTab}
          onTabChange={handleTabChange}
          query={query}
          onQueryChange={setQuery}
          dirtySections={isDirtySections}
          errorCounts={errorCounts}
        />
        <section className="min-w-0">{renderTab()}</section>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { isDemoMode } = useAuth();

  const handleSaveToBackend = useCallback(
    async (next: AppSettings) => {
      if (isDemoMode) return;
      await api.updateSettings(toSupabasePayload(next) as Partial<UserSettingsUpdate>);
    },
    [isDemoMode],
  );

  const handleLoadFromBackend = useCallback(async (): Promise<AppSettings | null> => {
    if (isDemoMode) return null;
    // Let failures propagate — the provider surfaces an explicit load error
    // instead of silently falling back to the local copy.
    const res = await api.getSettings();
    if (res?.app_settings && typeof res.app_settings === 'object') {
      return mergeAppSettingsFromSupabase(res.app_settings);
    }
    return null;
  }, [isDemoMode]);

  return (
    <SettingsProvider onSaveToBackend={handleSaveToBackend} onLoadFromBackend={handleLoadFromBackend}>
      <Suspense
        fallback={
          <div className="ds-page">
            <div className="card card-pad" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <RefreshCw className="w-4 h-4 animate-spin text-[var(--ds-ink-3)]" />
              <span className="muted" style={{ fontSize: 13 }}>Loading terminal configuration…</span>
            </div>
          </div>
        }
      >
        <SettingsDesk />
      </Suspense>
    </SettingsProvider>
  );
}
