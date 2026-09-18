import { describe, expect, it } from 'vitest';
import { Linter } from 'eslint';
// @ts-ignore - local .mjs rule ships without type declarations
import rule from '../../eslint-rules/rules/no-component-polling.mjs';

const linter = new Linter();

// Flat-config wrapper: the `files` glob is required so Linter.verify() maps
// the synthetic `filename` to this config (mirrors eslint.config.mjs scope).
const config = [
  {
    files: ['**/*.ts', '**/*.tsx'],
    plugins: { droid: { rules: { 'no-component-polling': rule } } },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: { 'droid/no-component-polling': 'error' },
  },
] as unknown as Linter.Config[];

const COMPONENT_FILE = 'E:/Droid/frontend/src/components/war-room/NewWidget.tsx';
const COMPONENT_TEST_FILE = 'E:/Droid/frontend/src/components/war-room/NewWidget.test.tsx';
const ALLOWLISTED_FILE = 'E:/Droid/frontend/src/components/common/FreshnessClock.tsx';
const HOOK_FILE = 'E:/Droid/frontend/src/hooks/useFoo.ts';

function pollingErrors(code: string, filename: string) {
  return linter
    .verify(code, config, { filename })
    .filter((message) => message.ruleId === 'droid/no-component-polling');
}

describe('droid/no-component-polling (P3-3)', () => {
  it('flags setInterval in a components file', () => {
    const messages = pollingErrors('setInterval(() => {}, 1000);', COMPONENT_FILE);
    expect(messages).toHaveLength(1);
    expect(messages[0].severity).toBe(2);
  });

  it('flags usePolling in a components file', () => {
    expect(pollingErrors('usePolling(load, 5000);', COMPONENT_FILE)).toHaveLength(1);
  });

  it('flags useSmartInterval in a components file', () => {
    expect(pollingErrors('useSmartInterval(callback, 1000);', COMPONENT_FILE)).toHaveLength(1);
  });

  it('flags window.setInterval in a components file', () => {
    expect(pollingErrors('window.setInterval(() => {}, 1000);', COMPONENT_FILE)).toHaveLength(1);
  });

  it('stays silent for test files (fake timers are legitimate)', () => {
    expect(pollingErrors('setInterval(() => {}, 1000);', COMPONENT_TEST_FILE)).toHaveLength(0);
    expect(pollingErrors('usePolling(load, 5000);', COMPONENT_TEST_FILE)).toHaveLength(0);
    expect(
      pollingErrors('useSmartInterval(callback, 1000);', COMPONENT_TEST_FILE),
    ).toHaveLength(0);
  });

  it('stays silent for allowlisted clocks/pending desks', () => {
    expect(pollingErrors('setInterval(() => {}, 1000);', ALLOWLISTED_FILE)).toHaveLength(0);
  });

  it('stays silent outside src/components', () => {
    expect(pollingErrors('setInterval(() => {}, 1000);', HOOK_FILE)).toHaveLength(0);
  });

  it('stays silent for components code that does not poll', () => {
    expect(pollingErrors('const now = Date.now();', COMPONENT_FILE)).toHaveLength(0);
    expect(pollingErrors('const kind = typeof setInterval;', COMPONENT_FILE)).toHaveLength(0);
  });
});
