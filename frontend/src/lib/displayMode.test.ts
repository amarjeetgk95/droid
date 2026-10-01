import { describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_DISPLAY_MODE,
  DISPLAY_BOOTSTRAP_SCRIPT,
  DISPLAY_STORAGE_KEY,
  applyDisplayMode,
  parseDisplayMode,
  readStoredDisplayMode,
  setDisplayMode,
  writeStoredDisplayMode,
  type DisplayMode,
} from './displayMode';

function fakeRoot() {
  const attrs = new Map<string, string>();
  return {
    attrs,
    root: {
      setAttribute: (name: string, value: string) => void attrs.set(name, value),
      removeAttribute: (name: string) => void attrs.delete(name),
    },
  };
}

function fakeStorage(initial?: string) {
  const store = new Map<string, string>();
  if (initial !== undefined) store.set(DISPLAY_STORAGE_KEY, initial);
  return {
    store,
    storage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    },
  };
}

describe('parseDisplayMode', () => {
  it('accepts every legal combination', () => {
    const mode: DisplayMode = { theme: 'dark', density: 'dense', contrast: 'high' };
    expect(parseDisplayMode(mode)).toEqual(mode);
  });

  it('falls back per axis, not wholesale', () => {
    // A theme from a newer build must not reset a valid density.
    expect(parseDisplayMode({ theme: 'midnight', density: 'compact' })).toEqual({
      theme: 'light',
      density: 'compact',
      contrast: 'normal',
    });
  });

  it('survives junk', () => {
    for (const junk of [null, undefined, 'dark', 42, [], true]) {
      expect(parseDisplayMode(junk)).toEqual(DEFAULT_DISPLAY_MODE);
    }
  });
});

describe('storage', () => {
  it('reads nothing as the default mode', () => {
    expect(readStoredDisplayMode(fakeStorage().storage)).toEqual(DEFAULT_DISPLAY_MODE);
  });

  it('round-trips through storage', () => {
    const { storage, store } = fakeStorage();
    const mode: DisplayMode = { theme: 'dark', density: 'compact', contrast: 'high' };
    writeStoredDisplayMode(mode, storage);
    expect(JSON.parse(store.get(DISPLAY_STORAGE_KEY)!)).toEqual(mode);
    expect(readStoredDisplayMode(storage)).toEqual(mode);
  });

  it('falls back when the stored value is corrupt', () => {
    expect(readStoredDisplayMode(fakeStorage('{not json').storage)).toEqual(DEFAULT_DISPLAY_MODE);
  });

  it('no-ops without storage', () => {
    expect(() => writeStoredDisplayMode(DEFAULT_DISPLAY_MODE, null)).not.toThrow();
    expect(readStoredDisplayMode(null)).toEqual(DEFAULT_DISPLAY_MODE);
  });
});

describe('applyDisplayMode', () => {
  it('writes only the non-default axes, so :root stays authoritative', () => {
    const { root, attrs } = fakeRoot();
    applyDisplayMode(DEFAULT_DISPLAY_MODE, root);
    expect(attrs.size).toBe(0);
  });

  it('sets the attributes for a non-default mode', () => {
    const { root, attrs } = fakeRoot();
    applyDisplayMode({ theme: 'dark', density: 'dense', contrast: 'high' }, root);
    expect(attrs.get('data-theme')).toBe('dark');
    expect(attrs.get('data-density')).toBe('dense');
    expect(attrs.get('data-contrast')).toBe('high');
  });

  it('clears an axis when it returns to default', () => {
    const { root, attrs } = fakeRoot();
    applyDisplayMode({ theme: 'dark', density: 'dense', contrast: 'high' }, root);
    applyDisplayMode(DEFAULT_DISPLAY_MODE, root);
    expect([...attrs.keys()]).toEqual([]);
  });

  it('is a no-op without a root', () => {
    expect(() => applyDisplayMode({ theme: 'dark', density: 'dense', contrast: 'high' }, null)).not.toThrow();
  });

  it('persists and applies together', () => {
    const { root, attrs } = fakeRoot();
    const { storage, store } = fakeStorage();
    const mode: DisplayMode = { theme: 'dark', density: 'comfortable', contrast: 'normal' };
    setDisplayMode(mode, root, storage);
    expect(attrs.get('data-theme')).toBe('dark');
    expect(attrs.has('data-density')).toBe(false);
    expect(store.get(DISPLAY_STORAGE_KEY)).toBe(JSON.stringify(mode));
  });
});

describe('DISPLAY_BOOTSTRAP_SCRIPT', () => {
  /** Execute the boot script against stubbed globals, as the browser would. */
  function runBootstrap(stored: string | null, themeColor = '#f7f8fa') {
    const attrs = new Map<string, string>([['content', themeColor]]);
    const root = {
      setAttribute: (name: string, value: string) => void attrs.set(name, value),
      removeAttribute: (name: string) => void attrs.delete(name),
    };
    const document = { documentElement: root, querySelector: () => ({ setAttribute: root.setAttribute }) };
    const localStorage = { getItem: () => stored };
    const run = new Function('localStorage', 'document', DISPLAY_BOOTSTRAP_SCRIPT);
    run(localStorage, document);
    return attrs;
  }

  it('applies a stored dark/dense preference before paint', () => {
    const attrs = runBootstrap(
      JSON.stringify({ theme: 'dark', density: 'dense', contrast: 'high' }),
    );
    expect(attrs.get('data-theme')).toBe('dark');
    expect(attrs.get('data-density')).toBe('dense');
    expect(attrs.get('data-contrast')).toBe('high');
    expect(attrs.get('content')).toBe('#0b0f17');
  });

  it('leaves the CSS defaults alone when nothing is stored', () => {
    expect(runBootstrap(null).size).toBe(1); // only the untouched theme-color
  });

  it('ignores unknown values instead of throwing', () => {
    const attrs = runBootstrap(JSON.stringify({ theme: 'solarized', density: 9 }));
    expect(attrs.has('data-theme')).toBe(false);
    expect(attrs.has('data-density')).toBe(false);
    expect(attrs.get('content')).toBe('#f7f8fa');
  });

  it('never throws on corrupt storage', () => {
    expect(() => runBootstrap('{{{')).not.toThrow();
  });

  it('agrees with parseDisplayMode on what the defaults are', () => {
    const attrs = runBootstrap(JSON.stringify(DEFAULT_DISPLAY_MODE));
    expect([...attrs.entries()]).toEqual([['content', '#f7f8fa']]);
  });
});

describe('storage errors', () => {
  it('does not break when storage throws', () => {
    const throwing = {
      getItem: vi.fn(() => {
        throw new Error('blocked');
      }),
      setItem: vi.fn(() => {
        throw new Error('blocked');
      }),
    };
    expect(readStoredDisplayMode(throwing)).toEqual(DEFAULT_DISPLAY_MODE);
    expect(() => writeStoredDisplayMode(DEFAULT_DISPLAY_MODE, throwing)).not.toThrow();
  });
});
