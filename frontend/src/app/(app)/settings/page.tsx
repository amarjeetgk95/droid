'use client';

import React, { useState, useCallback, useTransition } from 'react';
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
import { SettingsProvider, useSettings } from '@/components/settings/SettingsProvider';
import { AIEngineTab } from '@/components/settings/AIEngineTab';
import { BrokerConnectionTab } from '@/components/settings/BrokerConnectionTab';
import { QuantitativePricingTab } from '@/components/settings/QuantitativePricingTab';
import { PaperTradingRiskTab } from '@/components/settings/PaperTradingRiskTab';
import { PreferencesTab } from '@/components/settings/PreferencesTab';
import { TelegramTab } from '@/components/settings/TelegramTab';

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

// --- Skeleton for fast first paint, cheap shimmer (no blur) ---
function SettingsSkeleton() {
 return (
 <div className="space-y-4 max-w-5xl mx-auto animate-pulse">
  <div className="h-[88px] rounded-xl bg-slate-900 border border-slate-800" />
  <div className="h-12 rounded-xl bg-slate-900 border border-slate-800" />
  <div className="space-y-3">
  <div className="h-40 rounded-xl bg-slate-900 border border-slate-800" />
  <div className="h-64 rounded-xl bg-slate-900 border border-slate-800" />
  </div>
 </div>
 );
}

function TabSkeleton() {
 return (
 <div className="space-y-3 p-4">
  <div className="skeleton h-6 w-32 rounded" />
  <div className="skeleton h-24 w-full rounded-lg" />
  <div className="grid grid-cols-2 gap-3">
  <div className="skeleton h-20 rounded-lg" />
  <div className="skeleton h-20 rounded-lg" />
  </div>
 </div>
 );
}

function SettingsPageInner() {
 const [activeTab, setActiveTab] = useState<TabId>('ai');
 const [isPending, startTransition] = useTransition();

 const handleTabChange = useCallback((id: TabId) => {
 startTransition(() => setActiveTab(id));
 }, []);

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
 replaceAllSettings,
 save,
 saveSection,
 reset,
 } = useSettings() as unknown as {
 settings: import('@/lib/settings').AppSettings;
 isDirty: boolean;
 isDirtySections: Record<string, boolean>;
 isSaving: boolean;
 isSavingSection: Record<string, boolean>;
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
 saveSection: (s: string) => Promise<void>;
 reset: () => void;
 };

 if (isLoading) {
 return <SettingsSkeleton />;
 }

 return (
 <div className="space-y-4 pb-10 max-w-5xl mx-auto">
  {/* Top Bar — TradingView tight, no blur, shadow-sm */}
  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card border border-border rounded-xl p-4 shadow-sm [contain:paint]">
  <div className="flex items-center gap-3">
   <div className="bg-primary/10 border border-primary/20 p-2.5 rounded-lg text-primary">
   <Settings className="w-5 h-5" />
   </div>
   <div>
   <div className="flex items-center gap-2">
    <h1 className="text-[15px] font-bold tracking-tight text-foreground">Terminal Configuration</h1>
    <span className="px-1.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
    PRO
    </span>
   </div>
   <p className="text-[11px] text-muted-foreground mt-0.5 leading-tight">
    AI engines, broker APIs, and quantitative parameters
   </p>
   </div>
  </div>

  <div className="flex items-center gap-2 flex-wrap">
   {isDirty && !saveMessage && (
   <span className="text-[11px] text-amber-400 flex items-center gap-1.5 bg-amber-500/10 px-2.5 py-1 rounded-md border border-amber-500/20">
    <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
    Unsaved
   </span>
   )}
   {!isDirty && lastSaved && !saveMessage && (
   <span className="text-[11px] text-emerald-400 flex items-center gap-1 bg-emerald-500/10 px-2.5 py-1 rounded-md border border-emerald-500/20">
    <CheckCircle2 className="w-3 h-3" />
    Saved
   </span>
   )}
   {validationErrors.length > 0 && (
   <span className="text-[11px] text-destructive flex items-center gap-1 bg-destructive/10 px-2.5 py-1 rounded-md border border-destructive/20">
    <AlertCircle className="w-3 h-3" />
    {validationErrors.length} issues
   </span>
   )}
   {saveMessage && (
   <span
    className={`text-[11px] flex items-center gap-1 px-2.5 py-1 rounded-md border ${
    saveMessage.type === 'success'
     ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
     : 'text-destructive bg-destructive/10 border-destructive/20'
    }`}
   >
    {saveMessage.type === 'success' ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
    <span className="max-w-[180px] truncate">{saveMessage.text}</span>
   </span>
   )}
   {activeTab !== 'telegram' && isDirtySections?.[activeTab] && (
   <button
    type="button"
    onClick={() => saveSection(activeTab)}
    disabled={isSavingSection?.[activeTab] || isSaving}
    className="flex items-center gap-1.5 px-3 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground border border-border rounded-md text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
   >
    {isSavingSection?.[activeTab] ? <span className="w-3 h-3 border-2 border-foreground border-t-transparent rounded-full animate-spin" /> : <Save className="w-3 h-3" />}
    Save {activeTab}
   </button>
   )}
   <button
   type="button"
   onClick={save}
   disabled={isSaving || !isDirty}
   className="flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-md text-xs font-semibold transition-colors cursor-pointer shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
   >
   {isSaving ? <span className="w-3.5 h-3.5 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" /> : <Save className="w-3.5 h-3.5" />}
   <span>{isSaving ? 'Saving...' : 'Save'}</span>
   </button>
  </div>
  </div>

  {/* Navigation Tabs — tight 12px grid, no heavy shadow */}
  <div className="flex items-center gap-1 p-1 bg-card border border-border rounded-xl overflow-x-auto">
  {TABS.map((tab) => {
   const Icon = tab.icon;
   const isActive = activeTab === tab.id;
   const tabErrorCount = (sectionErrors?.[tab.id]?.length ?? validationErrors.filter((e) => e.path.startsWith(tab.id + '.')).length);
   const isTabDirty = !!(isDirtySections as Record<string, boolean>)?.[tab.id];
   return (
   <button
    key={tab.id}
    type="button"
    onClick={() => handleTabChange(tab.id)}
    aria-selected={isActive}
    className={`flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium transition-colors cursor-pointer whitespace-nowrap relative ${
    isActive
     ? 'bg-primary text-primary-foreground'
     : 'text-muted-foreground hover:text-foreground hover:bg-secondary/60'
    } ${isPending && isActive ? 'opacity-60' : ''}`}
   >
    <Icon className="w-3.5 h-3.5" />
    <span>{tab.label}</span>
    {isTabDirty && tab.id !== 'telegram' && <span className="w-1 h-1 bg-amber-400 rounded-full ml-0.5" title="Unsaved" />}
    {tabErrorCount > 0 && (
    <span className="absolute -top-1 -right-1 w-4 h-4 bg-destructive text-destructive-foreground rounded-full text-[9px] font-bold flex items-center justify-center">
     {tabErrorCount}
    </span>
    )}
   </button>
   );
  })}
  </div>

  {validationErrors.length > 0 && (
  <div className="bg-destructive/10 border border-destructive/20 rounded-xl p-3 space-y-2">
   <div className="flex items-center gap-2 text-xs font-semibold text-destructive">
   <AlertCircle className="w-3.5 h-3.5" />
   <span>{validationErrors.length} issues — click to jump</span>
   </div>
   <ul className="space-y-1">
   {validationErrors.map((e) => {
    const section = e.path.split('.')[0] as TabId;
    return (
    <li key={e.path}>
     <button
     type="button"
     onClick={() => handleTabChange(section)}
     className="text-xs text-left w-full px-2 py-1 rounded bg-card border border-border hover:border-destructive/30 text-destructive/90 hover:text-destructive font-mono flex items-center gap-2 cursor-pointer"
     >
     <span className="text-[10px] bg-destructive/15 px-1 py-0.5 rounded">{section}</span>
     <span className="truncate">{e.path}: {e.message}</span>
     </button>
    </li>
    );
   })}
   </ul>
  </div>
  )}

  {/* Keep-alive tabs — hidden, not mount/unmount. content-visibility for perf */}
  <div className={`relative ${isPending ? 'opacity-90' : ''}`} style={{ contentVisibility: 'auto' } as React.CSSProperties}>
  {isPending && (
          <div className="absolute inset-0 z-10 bg-card/60 rounded-xl flex items-center justify-center">
   <TabSkeleton />
   </div>
  )}
  <div hidden={activeTab !== 'ai'} className={activeTab !== 'ai' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'ai' ? 'visible' : 'auto' } as React.CSSProperties}>
   <AIEngineTab settings={settings.ai} onChange={updateAI} errors={validationErrors} />
  </div>
  <div hidden={activeTab !== 'broker'} className={activeTab !== 'broker' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'broker' ? 'visible' : 'auto' } as React.CSSProperties}>
   <BrokerConnectionTab settings={settings.broker} fullSettings={settings} onChange={updateBroker} errors={validationErrors} />
  </div>
  <div hidden={activeTab !== 'quantitative'} className={activeTab !== 'quantitative' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'quantitative' ? 'visible' : 'auto' } as React.CSSProperties}>
   <QuantitativePricingTab settings={settings.quantitative} onChange={updateQuantitative} errors={validationErrors} />
  </div>
  <div hidden={activeTab !== 'paper'} className={activeTab !== 'paper' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'paper' ? 'visible' : 'auto' } as React.CSSProperties}>
   <PaperTradingRiskTab settings={settings.paper} onChange={updatePaper} errors={validationErrors} />
  </div>
  <div hidden={activeTab !== 'preferences'} className={activeTab !== 'preferences' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'preferences' ? 'visible' : 'auto' } as React.CSSProperties}>
   <PreferencesTab settings={settings.preferences} fullSettings={settings} onChange={updatePreferences} onFullSettingsChange={replaceAllSettings} onResetAll={reset} errors={validationErrors} />
  </div>
  <div hidden={activeTab !== 'telegram'} className={activeTab !== 'telegram' ? 'hidden' : 'block'} style={{ contentVisibility: activeTab === 'telegram' ? 'visible' : 'auto' } as React.CSSProperties}>
   <TelegramTab />
  </div>
  </div>
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
