'use client';

import React, { createContext, useContext, useState, useEffect, useRef, useMemo, useCallback, useReducer } from 'react';
import { useRouter } from 'next/navigation';
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

const SETTINGS_SECTIONS: SettingsSection[] = ['broker', 'quantitative', 'ai', 'paper', 'preferences'];

export interface SettingsActionResult {
  success: boolean;
  error?: string;
}

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
  save: () => Promise<SettingsActionResult>;
  saveSection: (section: SettingsSection) => Promise<SettingsActionResult>;
  reset: () => Promise<SettingsActionResult>;
  exportJson: (includeSecrets?: boolean) => string;
  importJson: (jsonStr: string) => SettingsActionResult;

  // Helpers
  getFieldError: (fieldPath: string) => string | undefined;
  clearMessage: () => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function useOptionalSettings(): SettingsContextValue | null {
  return useContext(SettingsContext);
}

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
  const router = useRouter();
  const [settings, dispatch] = useReducer(settingsReducer, undefined, getInitialSettings);
  const [savedSnapshot, setSavedSnapshot] = useState<string>(() => JSON.stringify(getInitialSettings()));
  const savedRef = useRef<string>(savedSnapshot);
  const settingsRef = useRef<AppSettings>(settings);
  // Pre-hydration local state — used to detect edits made while the remote load is in flight.
  const initialSnapshotRef = useRef<string>(savedSnapshot);
  // Callback identity for which hydration already ran (refetches only when the
  // loader itself changes, e.g. demo-mode flip).
  const hydratedForRef = useRef<typeof onLoadFromBackend>(undefined);
  // Survives StrictMode's mount→cleanup→mount cycle (reset at the top of the
  // hydration effect) so an in-flight load still applies.
  const aliveRef = useRef(true);
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
      const cur = settings as unknown as Record<string, unknown>;
      const sections: SettingsSection[] = SETTINGS_SECTIONS;
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

  // Hydrate from backend — runs at most once per loader identity, never
  // clobbers edits made while the remote load was in flight, and surfaces
  // load failures.
  useEffect(() => {
    if (!onLoadFromBackend) {
      setIsLoading(false);
      return;
    }
    aliveRef.current = true;
    const cleanup = () => { aliveRef.current = false; };
    // StrictMode re-runs the effect; the in-flight load from the first run is
    // still valid and will apply because aliveRef was reset to true above.
    if (hydratedForRef.current === onLoadFromBackend) return cleanup;
    hydratedForRef.current = onLoadFromBackend;
    (async () => {
      try {
        setIsLoading(true);
        const remote = await onLoadFromBackend();
        if (!aliveRef.current || !remote) return;

        // Sections edited during the in-flight load win over the remote copy;
        // everything else takes the server value. savedSnapshot stays at the
        // server payload so preserved edits remain dirty and savable.
        const initial = JSON.parse(initialSnapshotRef.current) as Record<string, unknown>;
        const currentRec = settingsRef.current as unknown as Record<string, unknown>;
        const merged: AppSettings = { ...remote };
        const editedSections: SettingsSection[] = [];
        for (const section of SETTINGS_SECTIONS) {
          if (JSON.stringify(currentRec[section]) !== JSON.stringify(initial[section])) {
            (merged as unknown as Record<string, unknown>)[section] = currentRec[section];
            editedSections.push(section);
          }
        }

        dispatch({ type: 'SET', settings: merged });
        const snap = JSON.stringify(remote);
        setSavedSnapshot(snap);
        savedRef.current = snap;
        saveStoredSettings(merged);
        if (editedSections.length > 0) {
          showMessage({
            type: 'error',
            text: `Server settings loaded, but unsaved local edits to ${editedSections.join(', ')} were kept. Review and Save.`,
          });
        }
      } catch (err) {
        if (aliveRef.current) {
          showMessage({
            type: 'error',
            text: err instanceof Error
              ? `Could not load settings from server (${err.message}) — using local copy.`
              : 'Could not load settings from server — using local copy.',
          });
        }
      } finally {
        setIsLoading(false);
      }
    })();
    return cleanup;
  }, [onLoadFromBackend, showMessage]);

  // Warn before leaving the browser tab with unsaved changes
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

  // Guard in-app link navigation while dirty: confirm before discarding.
  useEffect(() => {
    if (!isDirty) return;
    function handleClick(event: MouseEvent) {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      const anchor = target?.closest?.('a[href]') as HTMLAnchorElement | null;
      if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      let url: URL;
      try {
        url = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      event.preventDefault();
      event.stopPropagation();
      if (window.confirm('You have unsaved settings changes. Leave this page and discard them?')) {
        router.push(`${url.pathname}${url.search}${url.hash}`);
      }
    }
    document.addEventListener('click', handleClick, true);
    return () => document.removeEventListener('click', handleClick, true);
  }, [isDirty, router]);

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

  /** Last persisted (server-side) settings — base for section-only saves. */
  const getPersistedSettings = useCallback((): AppSettings => {
    try {
      const parsed = JSON.parse(savedRef.current) as AppSettings;
      if (parsed && typeof parsed === 'object') return parsed;
    } catch {
      // savedRef is always JSON; fall back to in-memory state below.
    }
    return settingsRef.current;
  }, []);

  const save = useCallback(async (): Promise<SettingsActionResult> => {
    const current = settingsRef.current;
    const validation = validateSettings(current);
    if (!validation.success) {
      const first = validation.errors[0];
      const detail = first ? `${first.path}: ${first.message}` : '';
      const message = `Cannot save — ${validation.errors.length} validation error(s). ${detail} — fix highlighted fields.`;
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
    setIsSaving(true);
    try {
      // Backend first: the local cache is only advanced once the write is
      // authoritative, so a failed save leaves local and remote consistent
      // (still dirty) instead of resurrecting old values on the next hydrate.
      if (onSaveToBackend) await onSaveToBackend(current);
      const storedLocally = saveStoredSettings(current);
      const snap = JSON.stringify(current);
      setSavedSnapshot(snap);
      savedRef.current = snap;
      setLastSaved(new Date());
      if (!storedLocally) {
        const message = 'Saved to server, but the local cache could not be written (storage full or blocked).';
        showMessage({ type: 'error', text: message });
        return { success: true, error: message };
      }
      showMessage({ type: 'success', text: 'All settings saved successfully!' });
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save settings';
      showMessage({ type: 'error', text: `${message} — changes were not saved.` });
      return { success: false, error: message };
    } finally {
      setIsSaving(false);
    }
  }, [onSaveToBackend, showMessage]);

  const saveSection = useCallback(async (section: SettingsSection): Promise<SettingsActionResult> => {
    const current = settingsRef.current;
    const sectionValidation = validateSection(section, (current as unknown as Record<string, unknown>)[section]);
    if (!sectionValidation.success) {
      const first = sectionValidation.errors[0];
      const message = `Cannot save ${section}: ${first?.message ?? 'validation failed'}`;
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
    setIsSavingSections(prev => ({ ...prev, [section]: true }));
    try {
      // Persist ONLY the validated section, layered on the last saved snapshot,
      // so unsaved/invalid edits in other tabs are never silently published.
      const persisted = {
        ...getPersistedSettings(),
        [section]: (current as unknown as Record<string, unknown>)[section],
      } as AppSettings;
      if (onSaveToBackend) await onSaveToBackend(persisted);
      saveStoredSettings(persisted);
      const snap = JSON.stringify(persisted);
      setSavedSnapshot(snap);
      savedRef.current = snap;
      setLastSaved(new Date());
      showMessage({ type: 'success', text: `${section} saved. Other tabs keep their unsaved changes.` });
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : `Failed to save ${section}`;
      showMessage({ type: 'error', text: `${message} — ${section} was not saved.` });
      return { success: false, error: message };
    } finally {
      setIsSavingSections(prev => ({ ...prev, [section]: false }));
    }
  }, [getPersistedSettings, onSaveToBackend, showMessage]);

  // Ctrl+S — only when there is something to persist.
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (!isSaving && isDirty) save();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isSaving, isDirty, save]);

  // ── Reset / Import / Export ──────────────────────────────────────────────

  const reset = useCallback(async (): Promise<SettingsActionResult> => {
    setIsSaving(true);
    // Push defaults to the backend first — if that fails, local state and the
    // local cache are left untouched and the failure is surfaced.
    try {
      if (onSaveToBackend) await onSaveToBackend(DEFAULT_SETTINGS);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to reset settings';
      showMessage({ type: 'error', text: `${message} — settings were left unchanged.` });
      setIsSaving(false);
      return { success: false, error: message };
    }
    const defaults = resetStoredSettings();
    dispatch({ type: 'REPLACE', settings: defaults });
    const snap = JSON.stringify(defaults);
    setSavedSnapshot(snap);
    savedRef.current = snap;
    setLastSaved(new Date());
    showMessage({ type: 'success', text: 'All settings restored to factory defaults.' });
    setIsSaving(false);
    return { success: true };
  }, [onSaveToBackend, showMessage]);

  const exportJson = useCallback((includeSecrets = false) => {
    return exportSettingsJson(settingsRef.current, { includeSecrets });
  }, []);

  const importJson = useCallback((jsonStr: string): SettingsActionResult => {
    let imported: AppSettings;
    try {
      imported = importSettingsJson(jsonStr);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Invalid JSON file';
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
    const validation = validateSettings(imported);
    if (!validation.success) {
      const detail = validation.errors
        .slice(0, 3)
        .map((e) => `${e.path}: ${e.message}`)
        .join('; ');
      const suffix = validation.errors.length > 3 ? ` (+${validation.errors.length - 3} more)` : '';
      const message = `Import rejected — ${validation.errors.length} invalid value(s). ${detail}${suffix}`;
      showMessage({ type: 'error', text: message });
      return { success: false, error: message };
    }
    dispatch({ type: 'REPLACE', settings: imported });
    showMessage({ type: 'success', text: 'Settings imported. Review, then click Save to persist.' });
    return { success: true };
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
