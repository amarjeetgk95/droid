'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useMemo, useCallback, useReducer } from 'react';
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
import { validateSettings, validateSection, ValidationError } from '@/lib/settingsSchema';

// ── Context Value ────────────────────────────────────────────────────────────

type SettingsSection = 'broker' | 'quantitative' | 'ai' | 'paper' | 'preferences';

interface SettingsContextValue {
  // State
  settings: AppSettings;
  isDirty: boolean;
  isDirtySections: Record<SettingsSection, boolean>;
  isSaving: boolean;
  isSavingSection: Record<SettingsSection, boolean>;
  isLoading: boolean;
  validationErrors: ValidationError[];
  sectionErrors: Record<SettingsSection, ValidationError[]>;
  lastSaved: Date | null;
  saveMessage: { type: 'success' | 'error'; text: string } | null;

  // Section updaters (backward-compatible)
  updateBroker: (updates: Partial<BrokerSettings>) => void;
  updateQuantitative: (updates: Partial<QuantitativeSettings>) => void;
  updateAI: (updates: Partial<AISettings>) => void;
  updatePaper: (updates: Partial<PaperTradingSettings>) => void;
  updatePreferences: (updates: Partial<PreferencesSettings>) => void;
  // Generic patch
  patchSection: <K extends SettingsSection>(section: K, updates: Partial<AppSettings[K]>) => void;

  // Full settings operations
  replaceAllSettings: (newSettings: AppSettings) => void;
  save: () => Promise<void>;
  saveSection: (section: SettingsSection) => Promise<void>;
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

function getInitialSettings(): AppSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  return getStoredSettings();
}

// ── Reducer ────────────────────────────────────────────────────────────────

type Action =
  | { type: 'PATCH'; section: SettingsSection; updates: Record<string, unknown> }
  | { type: 'REPLACE'; settings: AppSettings }
  | { type: 'SET'; settings: AppSettings };

function settingsReducer(state: AppSettings, action: Action): AppSettings {
  switch (action.type) {
    case 'PATCH': {
      const prevSection = (state[action.section] as unknown) as Record<string, unknown>;
      // deep merge for nested objects like broker.fyers / ai.taskModels
      const nextSection: Record<string, unknown> = { ...prevSection };
      for (const [k, v] of Object.entries(action.updates)) {
        const prevVal = prevSection[k];
        if (
          prevVal &&
          typeof prevVal === 'object' &&
          !Array.isArray(prevVal) &&
          v &&
          typeof v === 'object' &&
          !Array.isArray(v)
        ) {
          nextSection[k] = { ...(prevVal as object), ...(v as object) };
        } else {
          nextSection[k] = v;
        }
      }
      return { ...state, [action.section]: nextSection };
    }
    case 'REPLACE':
    case 'SET':
      return action.settings;
    default:
      return state;
  }
}

// ── Provider ───────────────────────────────────────────────────────────────

interface SettingsProviderProps {
  children: React.ReactNode;
  onSaveToBackend?: (settings: AppSettings) => Promise<void>;
  onLoadFromBackend?: () => Promise<AppSettings | null>;
}

export function SettingsProvider({ children, onSaveToBackend, onLoadFromBackend }: SettingsProviderProps) {
  const [settings, dispatch] = useReducer(settingsReducer, undefined, getInitialSettings);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(() => JSON.stringify(getInitialSettings()));
  const savedRef = useRef<string>(savedSnapshot);
  const settingsRef = useRef<AppSettings>(settings);
  const [isSaving, setIsSaving] = useState(false);
  const [isSavingSections, setIsSavingSections] = useState<Record<SettingsSection, boolean>>({
    broker: false,
    quantitative: false,
    ai: false,
    paper: false,
    preferences: false,
  });
  const [isLoading, setIsLoading] = useState<boolean>(() => !!onLoadFromBackend);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const messageTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep refs in sync for stable save callback
  useEffect(() => { settingsRef.current = settings; }, [settings]);
  useEffect(() => { savedRef.current = savedSnapshot; }, [savedSnapshot]);

  // ── Debounced validation (300ms) — avoids zod on every keystroke ────────
  const [debouncedSettings, setDebouncedSettings] = useState<AppSettings>(settings);
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSettings(settings), 300);
    return () => clearTimeout(id);
  }, [settings]);

  // ── Dirty — per-section JSON with useRef cache (only changed section re-serialized)
  const sectionSerializedRef = useRef<Record<SettingsSection, string>>({
    broker: '',
    quantitative: '',
    ai: '',
    paper: '',
    preferences: '',
  });
  const prevSectionObjectsRef = useRef<Record<SettingsSection, unknown>>({
    broker: (settings as unknown as Record<string, unknown>).broker,
    quantitative: (settings as unknown as Record<string, unknown>).quantitative,
    ai: (settings as unknown as Record<string, unknown>).ai,
    paper: (settings as unknown as Record<string, unknown>).paper,
    preferences: (settings as unknown as Record<string, unknown>).preferences,
  });
  const savedSerializedRef = useRef<Record<SettingsSection, string>>({
    broker: '',
    quantitative: '',
    ai: '',
    paper: '',
    preferences: '',
  });
  const prevSavedSnapshotForDirtyRef = useRef<string>(savedSnapshot);
  const parsedSavedRef = useRef<AppSettings | null>(null);

  const { isDirty, isDirtySections } = useMemo(() => {
    const dirtySections: Record<SettingsSection, boolean> = {
      broker: false,
      quantitative: false,
      ai: false,
      paper: false,
      preferences: false,
    };
    try {
      // Re-parse saved only when snapshot string changes
      if (prevSavedSnapshotForDirtyRef.current !== savedSnapshot || !parsedSavedRef.current) {
        parsedSavedRef.current = JSON.parse(savedRef.current) as AppSettings;
        prevSavedSnapshotForDirtyRef.current = savedSnapshot;
        // invalidate saved serialized cache when snapshot changes
        const savedObj = parsedSavedRef.current as unknown as Record<string, unknown>;
        const sections: SettingsSection[] = ['broker', 'quantitative', 'ai', 'paper', 'preferences'];
        for (const s of sections) {
          savedSerializedRef.current[s] = JSON.stringify(savedObj[s]);
        }
      }
      const saved = parsedSavedRef.current as unknown as Record<string, unknown>;
      const cur = settings as unknown as Record<string, unknown>;
      const sections: SettingsSection[] = ['broker', 'quantitative', 'ai', 'paper', 'preferences'];
      let globalDirty = false;
      for (const s of sections) {
        const curSection = cur[s];
        // Only serialize section when its object identity changed
        if (prevSectionObjectsRef.current[s] !== curSection || !sectionSerializedRef.current[s]) {
          sectionSerializedRef.current[s] = JSON.stringify(curSection);
          prevSectionObjectsRef.current[s] = curSection;
        }
        const a = sectionSerializedRef.current[s];
        const b = savedSerializedRef.current[s];
        const isSectionDirty = a !== b;
        dirtySections[s] = isSectionDirty;
        if (isSectionDirty) globalDirty = true;
      }
      // global stringify avoided — per-section dirty already covers it; fallback only if no section dirty but snapshot mismatch (e.g. schemaVersion)
      if (!globalDirty) {
        // Check schemaVersion without full stringify: compare cached section serializations + snapshot version
        const curSnap = sectionSerializedRef.current.broker + sectionSerializedRef.current.quantitative + sectionSerializedRef.current.ai + sectionSerializedRef.current.paper + sectionSerializedRef.current.preferences;
        const savedSnap = savedSerializedRef.current.broker + savedSerializedRef.current.quantitative + savedSerializedRef.current.ai + savedSerializedRef.current.paper + savedSerializedRef.current.preferences;
        if (curSnap !== savedSnap) globalDirty = true;
        else {
          // fallback to full comparison only if per-section concat equal but snapshot differs (e.g. schemaVersion)
          const curVersion = (settings as unknown as { schemaVersion?: number }).schemaVersion;
          const savedVersion = (parsedSavedRef.current as unknown as { schemaVersion?: number })?.schemaVersion;
          if (curVersion !== savedVersion) globalDirty = true;
        }
      }
      return { isDirty: globalDirty, isDirtySections: dirtySections };
    } catch {
      // Fallback: minimal stringify only on error path
      const global = JSON.stringify(settings) !== savedRef.current;
      return { isDirty: global, isDirtySections: dirtySections };
    }
  }, [settings, savedSnapshot]);

  // Validation (debounced)
  const validationResult = useMemo(() => validateSettings(debouncedSettings), [debouncedSettings]);
  const validationErrors = validationResult.errors;
  const sectionErrors = useMemo(() => {
    const map: Record<SettingsSection, ValidationError[]> = { broker: [], quantitative: [], ai: [], paper: [], preferences: [] };
    for (const e of validationErrors) {
      const sec = e.path.split('.')[0] as SettingsSection;
      if (sec in map) map[sec].push(e);
    }
    return map;
  }, [validationErrors]);

  // Hydrate from Supabase
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
          dispatch({ type: 'SET', settings: remote });
          const snap = JSON.stringify(remote);
          setSavedSnapshot(snap);
          savedRef.current = snap;
          saveStoredSettings(remote);
        }
      } catch {
        // offline/demo — keep localStorage
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [onLoadFromBackend]);

  // Sync theme from external toggle (TopHeader) — keep provider state in sync with localStorage
  useEffect(() => {
    const syncTheme = () => {
      try {
        const raw = localStorage.getItem('droid_app_settings_v2') || localStorage.getItem('droid_app_settings_v1');
        if (!raw) return;
        const p = JSON.parse(raw) as AppSettings;
        const t = (p.preferences as unknown as { theme?: string })?.theme;
        if (t && t !== settings.preferences.theme) {
          dispatch({ type: 'PATCH', section: 'preferences', updates: { theme: t } as unknown as Record<string, unknown> });
        }
      } catch {}
    };
    window.addEventListener('droid-theme-changed', syncTheme as unknown as EventListener);
    window.addEventListener('storage', syncTheme as unknown as EventListener);
    return () => {
      window.removeEventListener('droid-theme-changed', syncTheme as unknown as EventListener);
      window.removeEventListener('storage', syncTheme as unknown as EventListener);
    };
  }, [settings.preferences.theme]);

  // Warn before leaving with unsaved changes
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (!isDirty) return;
      e.preventDefault();
      e.returnValue = '';
    }
    if (isDirty) {
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }
  }, [isDirty]);

  // Message helper
  const showMessage = useCallback((msg: { type: 'success' | 'error'; text: string }) => {
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    setSaveMessage(msg);
    messageTimeoutRef.current = setTimeout(() => setSaveMessage(null), 6000);
  }, []);

  const clearMessage = useCallback(() => {
    if (messageTimeoutRef.current) clearTimeout(messageTimeoutRef.current);
    setSaveMessage(null);
  }, []);

  // ── Patch helpers ────────────────────────────────────────────────────────

  const patchSection = useCallback(<K extends SettingsSection>(section: K, updates: Partial<AppSettings[K]>) => {
    dispatch({ type: 'PATCH', section, updates: updates as Record<string, unknown> });
  }, []);

  const updateBroker = useCallback((updates: Partial<BrokerSettings>) => patchSection('broker', updates), [patchSection]);
  const updateQuantitative = useCallback((updates: Partial<QuantitativeSettings>) => patchSection('quantitative', updates), [patchSection]);
  const updateAI = useCallback((updates: Partial<AISettings>) => patchSection('ai', updates), [patchSection]);
  const updatePaper = useCallback((updates: Partial<PaperTradingSettings>) => patchSection('paper', updates), [patchSection]);
  const updatePreferences = useCallback((updates: Partial<PreferencesSettings>) => patchSection('preferences', updates), [patchSection]);

  const replaceAllSettings = useCallback((newSettings: AppSettings) => {
    dispatch({ type: 'REPLACE', settings: newSettings });
  }, []);

  // ── Save ─────────────────────────────────────────────────────────────────

  const save = useCallback(async () => {
    const current = settingsRef.current;
    const validation = validateSettings(current);
    if (!validation.success) {
      const first = validation.errors[0];
      const detail = first ? `${first.path}: ${first.message}` : '';
      showMessage({
        type: 'error',
        text: `Cannot save — ${validation.errors.length} validation error(s). ${detail} — fix highlighted fields.`,
      });
      return;
    }
    setIsSaving(true);
    try {
      saveStoredSettings(current);
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('droid-theme-changed'));
      if (onSaveToBackend) await onSaveToBackend(current);
      const snap = JSON.stringify(current);
      setSavedSnapshot(snap);
      setLastSaved(new Date());
      showMessage({ type: 'success', text: 'All settings saved successfully!' });
    } catch (err) {
      showMessage({ type: 'error', text: err instanceof Error ? err.message : 'Failed to save settings' });
    } finally {
      setIsSaving(false);
    }
  }, [onSaveToBackend, showMessage]);

  const saveSection = useCallback(async (section: SettingsSection) => {
    const current = settingsRef.current;
    const sectionValidation = validateSection(section, (current as unknown as Record<string, unknown>)[section]);
    if (!sectionValidation.success) {
      const first = sectionValidation.errors[0];
      showMessage({ type: 'error', text: `Cannot save ${section}: ${first?.message ?? 'validation failed'}` });
      return;
    }
    setIsSavingSections(prev => ({ ...prev, [section]: true }));
    try {
      saveStoredSettings(current);
      if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('droid-theme-changed'));
      if (onSaveToBackend) await onSaveToBackend(current);
      const snap = JSON.stringify(current);
      setSavedSnapshot(snap);
      setLastSaved(new Date());
      showMessage({ type: 'success', text: `${section} saved.` });
    } catch (err) {
      showMessage({ type: 'error', text: err instanceof Error ? err.message : `Failed to save ${section}` });
    } finally {
      setIsSavingSections(prev => ({ ...prev, [section]: false }));
    }
  }, [onSaveToBackend, showMessage]);

  // Ctrl+S
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (!isSaving) save();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSaving, save]);

  // ── Reset / Import / Export ──────────────────────────────────────────────

  const reset = useCallback(async () => {
    const defaults = resetStoredSettings();
    dispatch({ type: 'REPLACE', settings: defaults });
    const snap = JSON.stringify(defaults);
    setSavedSnapshot(snap);
    setLastSaved(new Date());
    if (onSaveToBackend) {
      try { await onSaveToBackend(defaults); } catch {}
    }
    showMessage({ type: 'success', text: 'All settings restored to factory defaults.' });
  }, [onSaveToBackend, showMessage]);

  const exportJson = useCallback((includeSecrets = false) => {
    return exportSettingsJson(settingsRef.current, { includeSecrets });
  }, []);

  const importJson = useCallback((jsonStr: string): { success: boolean; error?: string } => {
    try {
      const imported = importSettingsJson(jsonStr);
      const validation = validateSettings(imported);
      dispatch({ type: 'REPLACE', settings: imported });
      if (!validation.success) {
        showMessage({
          type: 'error',
          text: `Imported with ${validation.errors.length} warning(s). Review highlighted fields before saving.`,
        });
        return { success: true };
      }
      showMessage({ type: 'success', text: 'Settings imported successfully! Click Save to persist.' });
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Invalid JSON file';
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
  }, [showMessage]);

  const getFieldError = useCallback((fieldPath: string): string | undefined => {
    return validationErrors.find((e) => e.path === fieldPath)?.message;
  }, [validationErrors]);

  const value: SettingsContextValue = useMemo(() => ({
    settings,
    isDirty,
    isDirtySections,
    isSaving,
    isSavingSection: isSavingSections,
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
    patchSection,
    replaceAllSettings,
    save,
    saveSection,
    reset,
    exportJson,
    importJson,
    getFieldError,
    clearMessage,
  }), [settings, isDirty, isDirtySections, isSaving, isSavingSections, isLoading, validationErrors, sectionErrors, lastSaved, saveMessage, updateBroker, updateQuantitative, updateAI, updatePaper, updatePreferences, patchSection, replaceAllSettings, save, saveSection, reset, exportJson, importJson, getFieldError, clearMessage]);

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}
