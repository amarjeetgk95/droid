/**
 * Token contract.
 *
 * `globals.css` is the whole visual system — 2k lines that every module reads
 * through. Nothing enforced it, so this test parses the stylesheet and asserts
 * the properties that make it institutional rather than decorative:
 *
 *   1. every `var(--x)` reference resolves to a declaration in the file (or to
 *      a documented external source, e.g. `next/font`); a typo'd token used to
 *      fail silently and paint nothing;
 *   2. the ink ramp and semantic colours clear WCAG AA on the surface they are
 *      used against, in **both** themes, and control borders clear 1.4.11;
 *   3. the dark theme defines every theme-sensitive token the light theme does
 *      (a missing override inherits a light colour and looks like a bug report);
 *   4. the density blocks define the same key set, all of it real tokens;
 *   5. every tone defines all three slots (ink/wash/line), and every one of the
 *      tone containers consumes them;
 *   6. `!important` appears only in the reduced-motion escape hatch.
 *
 * Pure string work — no CSS parser dependency, no browser.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS_PATH = path.resolve(process.cwd(), 'src/app/globals.css');
const CSS = readFileSync(CSS_PATH, 'utf8');

type Block = { selector: string; body: string; parents: string[] };

/**
 * CSS block parser. Every `selector { ... }` becomes a block whose `body` holds
 * only its own declarations (children are separate entries), with `parents`
 * giving the enclosing at-rule chain.
 */
function parseBlocks(source: string): Block[] {
  const clean = source.replace(/\/\*[\s\S]*?\*\//g, '');
  const blocks: Block[] = [];
  const stack: Block[] = [];
  // Whatever we have read since the last `;`, `{` or `}`: either the selector
  // of the next block / at-rule, or a declaration belonging to the open block.
  let pending = '';

  for (const ch of clean) {
    if (ch === '{') {
      stack.push({
        selector: pending.replace(/\s+/g, ' ').trim(),
        body: '',
        parents: stack.map((b) => b.selector),
      });
      pending = '';
    } else if (ch === '}') {
      const done = stack.pop();
      if (done) {
        done.body += pending;
        blocks.push(done);
      }
      pending = '';
    } else if (ch === ';') {
      // A `;` at depth 0 is a statement (@import, @custom-variant); inside a
      // block it terminates a declaration.
      if (stack.length > 0) stack[stack.length - 1].body += `${pending};`;
      pending = '';
    } else {
      pending += ch;
    }
  }
  return blocks;
}

const BLOCKS = parseBlocks(CSS);

function findBlock(selector: string, parent?: string): Block {
  const candidates = BLOCKS.filter(
    (b) => b.selector === selector && (!parent || b.parents.includes(parent)),
  );
  // Without an explicit parent, prefer the un-nested rule (the base/`@theme`
  // declaration), not a scoped override inside a media query.
  const match = parent ? candidates[0] : candidates.find((b) => b.parents.length === 0) ?? candidates[0];
  if (!match) throw new Error(`globals.css: block \`${selector}\` not found`);
  return match;
}

/** Custom-property declarations in a block: name -> raw value. */
function decls(block: Block): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of block.body.matchAll(/(--[\w-]+)\s*:\s*([^;}]+)/g)) out.set(m[1], m[2].trim());
  return out;
}

const LIGHT = decls(findBlock(':root'));
const DARK = decls(findBlock('html[data-theme="dark"]'));

const ALL_DECLARED = new Set<string>();
for (const block of BLOCKS) for (const name of decls(block).keys()) ALL_DECLARED.add(name);

/** Vars supplied from outside the stylesheet, with the reason they exist. */
const EXTERNAL_VARS = new Map<string, string>([
  ['--font-inter', 'next/font in layout.tsx'],
  ['--font-jetbrains', 'next/font in layout.tsx'],
  ['--tone-ink', 'set per-element by the tone slot maps'],
  ['--tone-wash', 'set per-element by the tone slot maps'],
  ['--tone-line', 'set per-element by the tone slot maps'],
  ['--ds-enter-opacity', 'animation start state, set by a companion utility'],
  ['--ds-enter-scale', 'animation start state, set by a companion utility'],
  ['--ds-enter-translate-x', 'animation start state, set by a companion utility'],
  ['--ds-enter-translate-y', 'animation start state, set by a companion utility'],
  ['--ds-exit-opacity', 'animation end state, set by a companion utility'],
  ['--ds-exit-scale', 'animation end state, set by a companion utility'],
  ['--ds-exit-translate-x', 'animation end state, set by a companion utility'],
  ['--ds-exit-translate-y', 'animation end state, set by a companion utility'],
]);

// ── colour maths ──────────────────────────────────────────────────────────

type Rgb = { r: number; g: number; b: number };

function parseColor(value: string): Rgb | null {
  const hex = value.trim().match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)?.[1];
  if (hex) {
    const full =
      hex.length === 3
        ? hex
            .split('')
            .map((c) => c + c)
            .join('')
        : hex;
    return {
      r: parseInt(full.slice(0, 2), 16),
      g: parseInt(full.slice(2, 4), 16),
      b: parseInt(full.slice(4, 6), 16),
    };
  }
  const rgb = value.trim().match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i);
  if (rgb) return { r: Number(rgb[1]), g: Number(rgb[2]), b: Number(rgb[3]) };
  return null; // rgba()/transparent — composited values are out of scope here
}

function luminance({ r, g, b }: Rgb): number {
  const channel = (raw: number) => {
    const c = raw / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Resolve `var(--other)` chains inside one theme, then the light fallback. */
function resolve(name: string, theme: Map<string, string>, depth = 0): string | undefined {
  const raw = theme.get(name) ?? LIGHT.get(name);
  if (raw === undefined || depth > 4) return undefined;
  const ref = raw.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  return ref ? resolve(ref[1], theme, depth + 1) : raw;
}

function resolvedColor(name: string, theme: Map<string, string>): Rgb {
  const raw = resolve(name, theme);
  const color = raw ? parseColor(raw) : null;
  if (!color) throw new Error(`${name} did not resolve to an opaque colour (got ${raw})`);
  return color;
}

// ── 1. reference integrity ────────────────────────────────────────────────

describe('token references', () => {
  it('resolves every var() reference to a declaration or a documented external', () => {
    const referenced = new Set<string>();
    for (const m of CSS.matchAll(/var\(\s*(--[\w-]+)/g)) referenced.add(m[1]);

    const unresolved = [...referenced].filter(
      (name) => !ALL_DECLARED.has(name) && !EXTERNAL_VARS.has(name),
    );
    expect(unresolved, `undefined tokens referenced by globals.css: ${unresolved.join(', ')}`).toEqual([]);
  });

  it('documents each external var with a reason', () => {
    for (const [, reason] of EXTERNAL_VARS) expect(reason.length).toBeGreaterThan(10);
  });
});

// ── 2 & 3. contrast and theme parity ──────────────────────────────────────

describe('light theme contrast (WCAG 2.1)', () => {
  const surface = resolvedColor('--ds-surface', LIGHT);

  it.each([
    ['--ds-ink', 12],
    ['--ds-ink-2', 4.5],
    ['--ds-ink-3', 4.5],
    ['--ds-bull-strong', 4.5],
    ['--ds-bear-strong', 4.5],
    ['--ds-warn-strong', 4.5],
    ['--ds-accent', 4.5],
  ])('%s clears %s:1 on the surface', (token, min) => {
    expect(contrast(resolvedColor(token, LIGHT), surface)).toBeGreaterThanOrEqual(min);
  });

  it('holds control borders to the 3:1 non-text requirement', () => {
    expect(contrast(resolvedColor('--ds-border-control', LIGHT), surface)).toBeGreaterThanOrEqual(3);
  });

  it('keeps decorative hairlines lighter than control borders', () => {
    expect(contrast(resolvedColor('--ds-border', LIGHT), surface)).toBeLessThan(
      contrast(resolvedColor('--ds-border-control', LIGHT), surface),
    );
  });
});

describe('dark theme contrast', () => {
  const surface = resolvedColor('--ds-surface', DARK);

  it.each([
    ['--ds-ink', 12],
    ['--ds-ink-2', 4.5],
    ['--ds-ink-3', 4.5],
    ['--ds-bull-strong', 4.5],
    ['--ds-bear-strong', 4.5],
    ['--ds-warn-strong', 4.5],
    ['--ds-accent', 4.5],
  ])('%s clears %s:1 on the dark surface', (token, min) => {
    expect(contrast(resolvedColor(token, DARK), surface)).toBeGreaterThanOrEqual(min);
  });

  it('holds control borders to the 3:1 non-text requirement', () => {
    expect(contrast(resolvedColor('--ds-border-control', DARK), surface)).toBeGreaterThanOrEqual(3);
  });
});

describe('theme parity', () => {
  /** Tokens whose value must differ between light and dark. */
  const THEME_TOKENS = [
    '--ds-page',
    '--ds-surface',
    '--ds-surface-subtle',
    '--ds-inset',
    '--ds-inset-2',
    '--ds-hover',
    '--ds-selected',
    '--ds-scrim',
    '--ds-border-subtle',
    '--ds-border',
    '--ds-border-strong',
    '--ds-border-control',
    '--ds-ink',
    '--ds-ink-2',
    '--ds-ink-3',
    '--ds-ink-4',
    '--ds-disabled',
    '--ds-ink-inverse',
    '--ds-chrome',
    '--ds-accent',
    '--ds-accent-hover',
    '--ds-accent-active',
    '--ds-accent-wash',
    '--ds-accent-line',
    '--ds-accent-glow',
    '--ds-selection',
    '--ds-bull',
    '--ds-bull-strong',
    '--ds-bull-wash',
    '--ds-bull-line',
    '--ds-bull-transparent',
    '--ds-bear',
    '--ds-bear-strong',
    '--ds-bear-action',
    '--ds-bear-action-hover',
    '--ds-bear-wash',
    '--ds-bear-line',
    '--ds-bear-glow',
    '--ds-neut',
    '--ds-neut-wash',
    '--ds-warn',
    '--ds-warn-strong',
    '--ds-warn-wash',
    '--ds-warn-line',
    '--ds-warn-ink',
    '--ds-chart-grid',
    '--ds-chart-crosshair',
    '--ds-chart-axis',
    '--ds-shadow-card',
    '--ds-shadow-overlay',
  ];

  it('overrides every theme-sensitive token in the dark theme', () => {
    const missing = THEME_TOKENS.filter((token) => !DARK.has(token) && !LIGHT?.has?.(token));
    expect(missing, `missing from html[data-theme="dark"]: ${missing.join(', ')}`).toEqual([]);
    const absent = THEME_TOKENS.filter((token) => !DARK.has(token));
    expect(absent).toEqual([]);
  });

  it('declares each theme-sensitive token in the light theme too', () => {
    const absent = THEME_TOKENS.filter((token) => !LIGHT.has(token));
    expect(absent, `missing from :root: ${absent.join(', ')}`).toEqual([]);
  });

  it('actually changes the value of every one of them', () => {
    const unchanged = THEME_TOKENS.filter((token) => LIGHT.get(token) === DARK.get(token));
    expect(unchanged, `identical in both themes: ${unchanged.join(', ')}`).toEqual([]);
  });

  it('sets color-scheme so native chrome follows the theme', () => {
    expect(findBlock('html[data-theme="dark"]').body).toContain('color-scheme: dark');
  });
});

// ── 4. density parity ─────────────────────────────────────────────────────

describe('density axes', () => {
  const densityBlocks = ['compact', 'dense'].map((name) =>
    findBlock(`html[data-density="${name}"]`),
  );

  it('shares one key set across every density', () => {
    const [compact, dense] = densityBlocks.map((b) => [...decls(b).keys()].sort());
    expect(compact).toEqual(dense);
    expect(compact.length).toBeGreaterThan(10);
  });

  it('only overrides real tokens', () => {
    const unknown = densityBlocks.flatMap((b) =>
      [...decls(b).keys()].filter((key) => !LIGHT.has(key) && !key.startsWith('--radius-')),
    );
    expect(unknown).toEqual([]);
  });

  it('keeps the type floor at 10px and never renders below it', () => {
    for (const block of [findBlock(':root'), ...densityBlocks]) {
      const micro = decls(block).get('--ds-fs-micro');
      if (micro) expect(parseFloat(micro)).toBeGreaterThanOrEqual(10);
    }
  });

  it('tightens rows and padding monotonically', () => {
    const rowOf = (b: Block) => parseFloat(decls(b).get('--ds-row-h') ?? '0');
    expect(rowOf(densityBlocks[0])).toBeLessThan(rowOf(findBlock(':root')));
    expect(rowOf(densityBlocks[1])).toBeLessThan(rowOf(densityBlocks[0]));
    const padOf = (b: Block) => parseFloat(decls(b).get('--ds-pad-cell-y') ?? '0');
    expect(padOf(densityBlocks[1])).toBeLessThan(padOf(densityBlocks[0]));
  });
});

// ── 5. tone system ────────────────────────────────────────────────────────

describe('tone system', () => {
  const TONES = ['bull', 'up', 'long', 'bear', 'down', 'short', 'warn', 'info', 'neut'];

  it.each(TONES)('tone "%s" defines ink, wash and line', (tone) => {
    const block = BLOCKS.find(
      (b) => b.parents.includes('@layer components') && b.selector.includes(`[data-tone="${tone}"]`),
    );
    expect(block, `no tone block for ${tone}`).toBeDefined();
    const body = block!.body + block!.selector;
    for (const slot of ['--tone-ink', '--tone-wash', '--tone-line']) {
      expect(body).toContain(slot);
    }
  });

  const TONE_LAYER = BLOCKS.filter((b) => b.parents.includes('@layer components'));

  it('paints the slots in exactly one place', () => {
    const painters = TONE_LAYER.filter(
      (b) => b.body.includes('color: var(--tone-ink)') && b.body.includes('background: var(--tone-wash)'),
    );
    expect(painters).toHaveLength(1);
  });

  it('keeps the tone layer below utilities, so utility overrides still win', () => {
    // Tailwind's layer order is theme → base → components → utilities, so a
    // utility (`bg-up-wash`, `text-ink-3`) still beats a tone slot.
    const painters = TONE_LAYER.filter((b) => b.body.includes('color: var(--tone-ink)'));
    expect(painters).toHaveLength(1);
    expect(painters[0].parents).toEqual(['@layer components']);
  });

  it('routes every legacy pill family through the slots', () => {
    const families = ['chip', 'badge', 'sg-tag', 'sg-dir', 'ttl-pill', 'feed-pill', 'rail-chip', 'stat-chip'];
    const selectors = TONE_LAYER.map((b) => b.selector).join(' ');
    for (const family of families) {
      expect(selectors, `${family} is not routed through the tone slots`).toContain(`.${family}`);
    }
  });
});

// ── 6. hygiene invariants ─────────────────────────────────────────────────

describe('stylesheet hygiene', () => {
  it('uses !important only to honour prefers-reduced-motion', () => {
    const offenders = BLOCKS.filter(
      (b) =>
        b.body.includes('!important') &&
        !b.parents.some((p) => p.includes('prefers-reduced-motion')),
    );
    expect(offenders.map((b) => b.selector)).toEqual([]);
  });

  it('keeps elevation tokens available for overlays', () => {
    expect(LIGHT.has('--ds-shadow-overlay')).toBe(true);
    expect(DARK.has('--ds-shadow-overlay')).toBe(true);
  });

  it('honours the OS contrast preference and forced colours', () => {
    const parents = BLOCKS.flatMap((b) => b.parents);
    expect(parents.some((p) => p.includes('prefers-contrast: more'))).toBe(true);
    expect(parents.some((p) => p.includes('forced-colors: active'))).toBe(true);
  });

  it('exposes the focus ring through tokens, not literals', () => {
    expect(CSS).toContain('outline: var(--ds-focus-w) solid var(--ds-focus-ink)');
  });

  it('declares the numeral contract once', () => {
    expect(LIGHT.has('--ds-num')).toBe(true);
    expect(findBlock('html').body).toContain('slashed-zero');
  });
});

// ── 7. the canvas palette is part of the contract too ─────────────────────

describe('chart palette', () => {
  /**
   * Canvas/SVG renderers cannot resolve `var()`, so `chartTheme.ts` carries a
   * literal mirror of :root for SSR. That mirror is exactly the kind of copy
   * that rots unnoticed, so it is asserted here rather than reviewed.
   */
  const CHART_SOURCE = readFileSync(path.resolve(process.cwd(), 'src/lib/chartTheme.ts'), 'utf8');
  const FALLBACK_BODY = CHART_SOURCE.slice(
    CHART_SOURCE.indexOf('const FALLBACK'),
    CHART_SOURCE.indexOf('const TOKEN_MAP'),
  );
  const TOKEN_FOR: Record<string, string> = {
    up: '--ds-bull',
    down: '--ds-bear',
    accent: '--ds-accent',
    warn: '--ds-warn',
    grid: '--ds-chart-grid',
    crosshair: '--ds-chart-crosshair',
    axis: '--ds-chart-axis',
    text: '--ds-ink-3',
    surface: '--ds-surface',
  };

  const normalize = (value: string) => value.replace(/\s+/g, '').toLowerCase();

  it.each(Object.keys(TOKEN_FOR))('SSR fallback for "%s" mirrors its token', (key) => {
    const literal = FALLBACK_BODY.match(new RegExp(`${key}:\\s*'([^']+)'`))?.[1];
    const token = LIGHT.get(TOKEN_FOR[key]);
    expect(token, `${TOKEN_FOR[key]} is missing from :root`).toBeDefined();
    expect(literal, `no fallback literal for ${key}`).toBeDefined();
    expect(normalize(literal!)).toBe(normalize(token!));
  });

  it('maps every chart token to a real design token', () => {
    const mapBody = CHART_SOURCE.slice(CHART_SOURCE.indexOf('const TOKEN_MAP'));
    for (const name of Object.values(TOKEN_FOR)) {
      expect(mapBody).toContain(`'${name}'`);
      expect(LIGHT.has(name), `${name} is not declared in :root`).toBe(true);
    }
  });
});
