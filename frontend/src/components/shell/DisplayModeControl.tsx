'use client';

import { useEffect, useState } from 'react';
import { Contrast, Moon, Rows3, Sun } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  CONTRAST_LABELS,
  DEFAULT_DISPLAY_MODE,
  DENSITY_HINTS,
  DENSITY_LABELS,
  DISPLAY_CONTRASTS,
  DISPLAY_DENSITIES,
  DISPLAY_THEMES,
  THEME_LABELS,
  applyDisplayMode,
  readStoredDisplayMode,
  setDisplayMode,
  type DisplayContrast,
  type DisplayDensity,
  type DisplayMode,
  type DisplayTheme,
} from '@/lib/displayMode';

/**
 * Appearance control for the three axes in `globals.css` — theme, density and
 * contrast.
 *
 * Stored per device, applied to `<html>` as data attributes, and pre-applied
 * by the bootstrap script in `layout.tsx` so there is no flash on load. This
 * component therefore starts from the CSS defaults and adopts the stored mode
 * in an effect rather than reading storage during render, which keeps the
 * server and first client render identical.
 */
export function DisplayModeControl() {
  const [mode, setMode] = useState<DisplayMode>(DEFAULT_DISPLAY_MODE);

  useEffect(() => {
    const stored = readStoredDisplayMode();
    setMode(stored);
    applyDisplayMode(stored);
  }, []);

  const update = (patch: Partial<DisplayMode>) => {
    const next = { ...mode, ...patch };
    setMode(next);
    setDisplayMode(next);
  };

  const summary = `${THEME_LABELS[mode.theme]} · ${DENSITY_LABELS[mode.density]} · ${CONTRAST_LABELS[mode.contrast]}`;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="btn icon-btn" aria-label="Display mode" title={summary}>
          {mode.theme === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="micro-label">Display</DropdownMenuLabel>
        <p className="px-2 pb-1 text-xs text-ink-3">{summary}</p>
        <DropdownMenuSeparator />

        <DropdownMenuLabel className="micro-label">Theme</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mode.theme}
          onValueChange={(value) => update({ theme: value as DisplayTheme })}
        >
          {DISPLAY_THEMES.map((theme) => (
            <DropdownMenuRadioItem
              key={theme}
              value={theme}
              onSelect={(event) => event.preventDefault()}
            >
              {THEME_LABELS[theme]}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="micro-label">Density</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mode.density}
          onValueChange={(value) => update({ density: value as DisplayDensity })}
        >
          {DISPLAY_DENSITIES.map((density) => (
            <DropdownMenuRadioItem
              key={density}
              value={density}
              title={DENSITY_HINTS[density]}
              onSelect={(event) => event.preventDefault()}
            >
              <span className="inline-flex items-baseline gap-2">
                {DENSITY_LABELS[density]}
                <span className="text-xs text-ink-3">{DENSITY_HINTS[density]}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="micro-label">Contrast</DropdownMenuLabel>
        <DropdownMenuRadioGroup
          value={mode.contrast}
          onValueChange={(value) => update({ contrast: value as DisplayContrast })}
        >
          {DISPLAY_CONTRASTS.map((contrast) => (
            <DropdownMenuRadioItem
              key={contrast}
              value={contrast}
              onSelect={(event) => event.preventDefault()}
            >
              <span className="inline-flex items-center gap-2">
                {contrast === 'high' ? <Contrast size={13} /> : <Rows3 size={13} />}
                {CONTRAST_LABELS[contrast]}
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => update(DEFAULT_DISPLAY_MODE)}>
          Reset to defaults
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
