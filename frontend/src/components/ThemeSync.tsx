'use client';

import { useEffect } from 'react';

function resolveTheme(raw: string | null): 'light' | 'dark' {
  if (raw === 'light' || raw === 'dark') return raw;
  if (raw === 'system' || !raw) {
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
    return 'light';
  }
  return 'light';
}

function applyTheme(theme: 'light' | 'dark') {
  const html = document.documentElement;
  html.setAttribute('data-theme', theme);
  html.style.colorScheme = theme;
  // also keep class for Tailwind compat if any component uses .dark
  html.classList.toggle('dark', theme === 'dark');
}

function getStoredTheme(): string | null {
  try {
    const v2 = localStorage.getItem('droid_app_settings_v2');
    if (v2) {
      const p = JSON.parse(v2);
      return p?.preferences?.theme ?? p?.theme ?? null;
    }
    const v1 = localStorage.getItem('droid_app_settings_v1');
    if (v1) {
      const p = JSON.parse(v1);
      return p?.preferences?.theme ?? null;
    }
  } catch {}
  return null;
}

export function ThemeSync() {
  useEffect(() => {
    const sync = () => {
      const stored = getStoredTheme();
      const resolved = resolveTheme(stored);
      applyTheme(resolved);
      // update theme-color meta
      const meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute('content', resolved === 'dark' ? '#020617' : '#f8fafc');
    };

    sync();

    // listen to storage changes (other tabs, Settings page save)
    const onStorage = (e: StorageEvent) => {
      if (e.key === 'droid_app_settings_v2' || e.key === 'droid_app_settings_v1') sync();
    };
    window.addEventListener('storage', onStorage);

    // listen to system change when theme is 'system'
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onSystem = () => {
      const stored = getStoredTheme();
      if (stored === 'system' || !stored) sync();
    };
    mql.addEventListener?.('change', onSystem);

    // custom event dispatched by SettingsProvider after save
    const onCustom = () => sync();
    window.addEventListener('droid-theme-changed', onCustom as EventListener);

    return () => {
      window.removeEventListener('storage', onStorage);
      mql.removeEventListener?.('change', onSystem);
      window.removeEventListener('droid-theme-changed', onCustom as EventListener);
    };
  }, []);

  return null;
}
