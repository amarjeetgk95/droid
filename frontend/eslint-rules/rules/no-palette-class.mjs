/**
 * droid/no-palette-class
 *
 * Bans raw Tailwind palette utilities anywhere in `src/**` string literals —
 * class attributes, `cn(...)`/`cva(...)` maps, plain string maps. The design
 * system is token-only: `up`/`down`/`warn`/`accent` (each with `-wash`,
 * `-line`, `-strong`, `-ink`), plus the ink/surface/border tokens.
 *
 * `text-white` / `text-black` are intentionally allowed (primary-button ink),
 * as are arbitrary values (`bg-[var(--ds-bull)]`, `bg-[#...]` is handled by
 * `droid/no-raw-hex`).
 *
 * Examples of violations:
 *   "bg-slate-100"                 "hover:text-emerald-700"
 *   "data-[state=open]:bg-blue-50" "bg-red-500/50"
 *   "bg-white" (surface)           "border-black"
 * Examples that pass:
 *   "bg-up-wash"  "text-ink-3"  "border-border-subtle"  "text-white"
 */

import { findPaletteTokens } from '../lib/classes.mjs';

export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow raw Tailwind palette utilities; use design tokens / semantic utilities.',
    },
    schema: [],
    messages: {
      palette:
        'Raw palette class "{{token}}" is banned. Use a design token or a semantic utility ' +
        '(up / down / warn / accent, each with -wash / -line / -strong / -ink; or ' +
        'ink-*, surface-*, border-*), or an arbitrary token value such as bg-[var(--ds-bull)].',
    },
  },

  create(context) {
    const check = (node, text) => {
      const hits = findPaletteTokens(text);
      if (hits.length === 0) return;
      context.report({
        node,
        messageId: 'palette',
        data: { token: hits.join(', ') },
      });
    };

    return {
      Literal(node) {
        if (typeof node.value === 'string') check(node, node.value);
      },
      TemplateElement(node) {
        check(node, node.value.raw);
      },
    };
  },
};
