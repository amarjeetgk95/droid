/**
 * Local ESLint plugin: `droid/*` design-system guardrails.
 *
 * Wired up in `eslint.config.mjs` for source TypeScript files. The design gate
 * (`scripts/check-design-rules.mjs`) fails only on `droid/*` findings.
 */

import noPaletteClass from './rules/no-palette-class.mjs';
import noRawHex from './rules/no-raw-hex.mjs';

export default {
  meta: {
    name: 'droid',
    version: '1.0.0',
  },
  rules: {
    'no-palette-class': noPaletteClass,
    'no-raw-hex': noRawHex,
  },
};
