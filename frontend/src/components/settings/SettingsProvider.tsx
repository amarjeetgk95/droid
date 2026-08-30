'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useMemo } from 'react';
import {
  AppSettings,
  BrokerSettings,
  QuantitativeSettings,
  AISettings,
  PaperTradingSettings,
  PreferencesSettings,
  DEFAULT_SETTINGS,
  getStoredSettings,
  saveStoredSettings,
  resetStoredSettings,
  exportSettingsJson,
  importSettingsJson,
} from '@/lib/settings';
import { validateSettings, ValidationError } from '@/lib/settingsValidation';

// ============================================================================
// Settings Context — Single Source of Truth
// ============================================================================

interface SettingsContextValue {
  // State
  settings: AppSettings;
  isDirty: boolean;
  isSaving: boolean;
  isLoading: boolean;
  validationErrors: ValidationError[];
  lastSaved: Date | null;
  saveMessage: { type: 'success' | 'error'; text: string } | null;

  // Section updaters
  updateBroker: (updates: Partial<BrokerSettings>) => void;
  updateQuantitative: (updates: Partial<QuantitativeSettings>) => void;
  updateAI: (updates: Partial<AISettings>) => void;
  updatePaper: (updates: Partial<PaperTradingSettings>) => void;
  updatePreferences: (updates: Partial<PreferencesSettings>) => void;

  // Full settings operations
  replaceAllSettings: (newSettings: AppSettings) => void;
  save: () => Promise<void>;
  reset: () => void;
  exportJson: (includeSecrets?: boolean) => string;
  importJson: (jsonStr: string) => { success: boolean; error?: string };

  // Helpers
  getFieldError: (fieldPath: string) => string | undefined;
  clearMessage: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function useSettings(): SettingsContextValue {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error('useSettings() must be used within a <SettingsProvider>');
  }
  return ctx;
}

// ============================================================================
// Helper: read stored settings safely (only on client)
// ============================================================================

function getInitialSettings(): AppSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  return getStoredSettings();
}

// ============================================================================
// Settings Provider
// ============================================================================

interface SettingsProviderProps {
  children: React.ReactNode;
  /**
   * Optional async callback to persist settings to backend.
   * Called during save() after localStorage write.
   */
  onSaveToBackend?: (settings: AppSettings) => Promise<void>;
  /**
   * Optional async callback to load settings from backend (Supabase).
   * RECTIFY: Supabase is now source of truth — if provided, settings are
   * hydrated from Supabase on mount and Supabase wins over localStorage.
   */
  onLoadFromBackend?: () => Promise<AppSettings | null>;
}

export function SettingsProvider({ children, onSaveToBackend, onLoadFromBackend }: SettingsProviderProps) {
  // Initialize from localStorage directly (avoids cascading render from useEffect setState)
  const [settings, setSettings] = useState<AppSettings>(getInitialSettings);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(() => JSON.stringify(getInitialSettings()));
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState<boolean>(() => !!onLoadFromBackend);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [saveMessage, setSaveMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);
  const messageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Compute dirty state by comparing current settings to last saved snapshot
  const isDirty = JSON.stringify(settings) !== savedSnapshot;

  // Compute validation inline (not in effect) — it's pure computation
  const validationResult = useMemo(() => validateSettings(settings), [settings]);
  const validationErrors = validationResult.errors;

  // RECTIFY: Hydrate from Supabase (source of truth) on mount
  useEffect(() => {
    if (!onLoadFromBackend) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        setIsLoading(true);
        const remote = await onLoadFromBackend();
        if (!cancelled && remote) {
          setSettings(remote);
          const snap = JSON.stringify(remote);
          setSavedSnapshot(snap);
          // Keep localStorage as warm cache/mirror
          saveStoredSettings(remote);
        }
      } catch {
        // Keep localStorage fallback silently — offline/demo mode
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [onLoadFromBackend]);

  // Warn before leaving with unsaved changes
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      // Read current state via the DOM-event closure; re-evaluate each time
      // because we re-register the handler whenever isDirty changes
      e.preventDefault();
    }

    if (isDirty) {
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }
  }, [isDirty]);

  // Ctrl+S shortcut to save — uses a ref-free approach by re-registering
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        // Trigger save by dispatching a custom event — picked up below
        window.dispatchEvent(new CustomEvent('droid-settings-save'));
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Listen for save custom event
  useEffect(() => {
    function handleSaveEvent() {
      if (isDirty && !isSaving) {
        save();
      }
    }
    window.addEventListener('droid-settings-save', handleSaveEvent);
    return () => window.removeEventListener('droid-settings-save', handleSaveEvent);
  });

  // Auto-dismiss messages helper
  function showMessage(msg: { type: 'success' | 'error'; text: string }) {
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    setSaveMessage(msg);
    messageTimeoutRef.current = setTimeout(() => setSaveMessage(null), 6000);
  }

  function clearMessage() {
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    setSaveMessage(null);
  }

  // --- Section updaters ---
  function updateBroker(updates: Partial<BrokerSettings>) {
    setSettings((prev) => ({
      ...prev,
      broker: { ...prev.broker, ...updates },
    }));
  }

  function updateQuantitative(updates: Partial<QuantitativeSettings>) {
    setSettings((prev) => ({
      ...prev,
      quantitative: { ...prev.quantitative, ...updates },
    }));
  }

  function updateAI(updates: Partial<AISettings>) {
    setSettings((prev) => ({
      ...prev,
      ai: { ...prev.ai, ...updates },
    }));
  }

  function updatePaper(updates: Partial<PaperTradingSettings>) {
    setSettings((prev) => ({
      ...prev,
      paper: { ...prev.paper, ...updates },
    }));
  }

  function updatePreferences(updates: Partial<PreferencesSettings>) {
    setSettings((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, ...updates },
    }));
  }

  function replaceAllSettings(newSettings: AppSettings) {
    setSettings(newSettings);
  }

  // --- Save ---
  async function save() {
    // Validate before saving
    const validation = validateSettings(settings);
    if (!validation.success) {
      showMessage({
        type: 'error',
        text: `Cannot save — ${validation.errors.length} validation error(s). Fix highlighted fields.`,
      });
      return;
    }

    setIsSaving(true);
    try {
      // 1. Save to localStorage as cache/mirror
      saveStoredSettings(settings);

      // 2. Persist to Supabase via backend (RECTIFY: now required, Supabase is source of truth)
      if (onSaveToBackend) {
        await onSaveToBackend(settings);
      }

      const snapshot = JSON.stringify(settings);
      setSavedSnapshot(snapshot);
      setLastSaved(new Date());
      showMessage({ type: 'success', text: 'All settings saved successfully!' });
    } catch (err) {
      showMessage({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to save settings',
      });
    } finally {
      setIsSaving(false);
    }
  }

  // --- Reset ---
  async function reset() {
    const defaults = resetStoredSettings();
    setSettings(defaults);
    setSavedSnapshot(JSON.stringify(defaults));
    setLastSaved(new Date());
    // RECTIFY: also persist reset to Supabase so remote state matches
    if (onSaveToBackend) {
      try { await onSaveToBackend(defaults); } catch { /* show local success anyway */ }
    }
    showMessage({ type: 'success', text: 'All settings restored to factory defaults.' });
  }

  // --- Export ---
  function exportJson(includeSecrets = false) {
    return exportSettingsJson(settings, { includeSecrets });
  }

  // --- Import ---
  function importJson(jsonStr: string): { success: boolean; error?: string } {
    try {
      const imported = importSettingsJson(jsonStr);

      // Validate the imported settings
      const validation = validateSettings(imported);
      if (!validation.success) {
        // Still apply them but warn — they're merged with defaults so won't crash
        setSettings(imported);
        showMessage({
          type: 'error',
          text: `Imported with ${validation.errors.length} warning(s). Review highlighted fields before saving.`,
        });
        return { success: true };
      }

      setSettings(imported);
      showMessage({
        type: 'success',
        text: 'Settings imported successfully! Click Save to persist.',
      });
      return { success: true };
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Invalid JSON file';
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
  }

  // --- Field error helper ---
  function getFieldError(fieldPath: string): string | undefined {
    return validationErrors.find((e) => e.path === fieldPath)?.message;
  }

  const value: SettingsContextValue = {
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
    exportJson,
    importJson,
    getFieldError,
    clearMessage,
  };

  return (
    <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>
  );
}
