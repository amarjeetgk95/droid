/**
 * Display mode — the three appearance axes declared in `globals.css`:
 *
 *   theme     light desk (default) | dark terminal   -> data-theme
 *   density   comfortable | compact | dense          -> data-density
 *   contrast  normal | high                          -> data-contrast
 *
 * These are **device** preferences, not account preferences: density is a
 * property of the panel in front of you, and a trader moving from a 13" laptop
 * to a wall of monitors wants a different one on each. So they live in
 * `localStorage`, and the durable settings store keeps its own `theme` field
 * for backups only.
 *
 * The CSS defaults are light + comfortable + normal, so `applyDisplayMode`
 * *removes* the attribute when a value is the default rather than writing it —
 * the DOM stays clean and `:root` remains the single source of those values.
 *
 * `DISPLAY_BOOTSTRAP_SCRIPT` is generated from the same constants so the
 * pre-paint script in `layout.tsx` cannot drift from this module.
 */

import { resetChartTokens } from './chartTheme';

export const DISPLAY_STORAGE_KEY = 'droid.display';

export const DISPLAY_THEMES = ['light', 'dark'] as const;
export const DISPLAY_DENSITIES = ['comfortable', 'compact', 'dense'] as const;
export const DISPLAY_CONTRASTS = ['normal', 'high'] as const;

export type DisplayTheme = (typeof DISPLAY_THEMES)[number];
export type DisplayDensity = (typeof DISPLAY_DENSITIES)[number];
export type DisplayContrast = (typeof DISPLAY_CONTRASTS)[number];

export type DisplayMode = {
  theme: DisplayTheme;
  density: DisplayDensity;
  contrast: DisplayContrast;
};

export const DEFAULT_DISPLAY_MODE: DisplayMode = {
  theme: 'light',
  density: 'comfortable',
  contrast: 'normal',
};

export const THEME_LABELS: Record<DisplayTheme, string> = {
  light: 'Light desk',
  dark: 'Dark terminal',
};

export const DENSITY_LABELS: Record<DisplayDensity, string> = {
  comfortable: 'Comfortable',
  compact: 'Compact',
  dense: 'Dense',
};

export const DENSITY_HINTS: Record<DisplayDensity, string> = {
  comfortable: '30px rows · 13px base',
  compact: '26px rows · 12.5px base',
  dense: '22px rows · 12px base',
};

export const CONTRAST_LABELS: Record<DisplayContrast, string> = {
  normal: 'Standard',
  high: 'High contrast',
};

/** The browser-visible chrome colour per theme, kept in sync with --ds-page. */
export const THEME_COLORS: Record<DisplayTheme, string> = {
  light: '#f7f8fa',
  dark: '#0b0f17',
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;
type RootLike = Pick<Element, 'setAttribute' | 'removeAttribute'>;

/** Narrow an unknown value (parsed JSON, query string, storage) to a mode. */
export function parseDisplayMode(raw: unknown): DisplayMode {
  const source = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
  const pick = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
    typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;

  return {
    theme: pick(source.theme, DISPLAY_THEMES, DEFAULT_DISPLAY_MODE.theme),
    density: pick(source.density, DISPLAY_DENSITIES, DEFAULT_DISPLAY_MODE.density),
    contrast: pick(source.contrast, DISPLAY_CONTRASTS, DEFAULT_DISPLAY_MODE.contrast),
  };
}

function defaultStorage(): StorageLike | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    // Storage can throw outright in locked-down/private contexts.
    return null;
  }
}

export function readStoredDisplayMode(storage: StorageLike | null = defaultStorage()): DisplayMode {
  if (!storage) return DEFAULT_DISPLAY_MODE;
  try {
    const raw = storage.getItem(DISPLAY_STORAGE_KEY);
    return raw ? parseDisplayMode(JSON.parse(raw)) : DEFAULT_DISPLAY_MODE;
  } catch {
    return DEFAULT_DISPLAY_MODE;
  }
}

export function writeStoredDisplayMode(
  mode: DisplayMode,
  storage: StorageLike | null = defaultStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(mode));
  } catch {
    // A full or blocked store must not break the desk.
  }
}

/** Write the axes onto `<html>`, dropping attributes that are already defaults. */
export function applyDisplayMode(
  mode: DisplayMode,
  root: RootLike | null = typeof document === 'undefined' ? null : document.documentElement,
): void {
  if (!root) return;
  const axes: (keyof DisplayMode)[] = ['theme', 'density', 'contrast'];
  for (const axis of axes) {
    if (mode[axis] === DEFAULT_DISPLAY_MODE[axis]) root.removeAttribute(`data-${axis}`);
    else root.setAttribute(`data-${axis}`, mode[axis]);
  }
  const meta =
    typeof document === 'undefined' ? null : document.querySelector('meta[name="theme-color"]');
  meta?.setAttribute('content', THEME_COLORS[mode.theme]);

  // Canvas/SVG renderers read design tokens once and cache them; a theme change
  // makes that cache stale, so drop it here rather than in every chart.
  resetChartTokens();
}

/** Persist and apply in one call — the only entry point the UI needs. */
export function setDisplayMode(
  mode: DisplayMode,
  root?: RootLike | null,
  storage?: StorageLike | null,
): void {
  writeStoredDisplayMode(mode, storage);
  applyDisplayMode(mode, root);
}

/**
 * Pre-paint bootstrap for `layout.tsx`.
 *
 * Runs before first paint so a stored dark/dense preference cannot flash the
 * light comfortable desk. Deliberately dependency-free and failure-tolerant:
 * any throw leaves the CSS defaults in place, which is a valid state.
 */
export function displayBootstrapScript(): string {
  const spec = JSON.stringify({
    theme: DISPLAY_THEMES,
    density: DISPLAY_DENSITIES,
    contrast: DISPLAY_CONTRASTS,
  });
  const def = JSON.stringify(DEFAULT_DISPLAY_MODE);
  const colors = JSON.stringify(THEME_COLORS);
  return (
    `(function(){try{` +
    `var KEY=${JSON.stringify(DISPLAY_STORAGE_KEY)},SPEC=${spec},DEF=${def},COLORS=${colors};` +
    `var raw=localStorage.getItem(KEY);if(!raw)return;` +
    `var m=JSON.parse(raw)||{},root=document.documentElement;` +
    `for(var axis in SPEC){var v=m[axis];` +
    `if(SPEC[axis].indexOf(v)===-1)v=DEF[axis];` +
    `if(v===DEF[axis])root.removeAttribute('data-'+axis);else root.setAttribute('data-'+axis,v);}` +
    `var meta=document.querySelector('meta[name="theme-color"]');` +
    `if(meta)meta.setAttribute('content',m.theme==='dark'?COLORS.dark:COLORS.light);` +
    `}catch(e){}})();`
  );
}

export const DISPLAY_BOOTSTRAP_SCRIPT = displayBootstrapScript();
