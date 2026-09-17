/**
 * droid/no-raw-hex
 *
 * Bans `#rgb` / `#rgba` / `#rrggbb` / `#rrggbbaa` literals in `.tsx` files at
 * the two places a component can hardcode colour:
 *   1. JSX `className` strings (incl. arbitrary values: `bg-[#ff0000]`)
 *   2. inline `style` colour values (`style={{ color: '#f00' }}`,
 *      `style={{ border: '1px solid #e2e8f0' }}`)
 *
 * CSS files (`globals.css`) own the raw token values and are not linted.
 *
 * Violations:
 *   <div className="bg-[#fff]" />
 *   <div style={{ color: '#dc2626' }} />
 * Passes:
 *   <div className="bg-down" />
 *   <div style={{ color: 'var(--ds-bear)' }} />
 */

const HEX_RE =
  /#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])/;

const COLOR_KEY_RE =
  /(colou?r|background|border|outline|fill|stroke|shadow|caret|accent|decoration)/i;

const SKIP_KEYS = new Set(['parent', 'loc', 'range', 'start', 'end']);

/** Visit every string literal / template quasi below `node`. */
function forEachString(node, visit) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const child of node) forEachString(child, visit);
    return;
  }
  if (node.type === 'Literal' && typeof node.value === 'string') {
    visit(node, node.value);
    return;
  }
  if (node.type === 'TemplateElement') {
    visit(node, node.value.raw);
    return;
  }
  for (const key of Object.keys(node)) {
    if (SKIP_KEYS.has(key)) continue;
    forEachString(node[key], visit);
  }
}

export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow raw hex colour literals in JSX className strings and inline style colour values.',
    },
    schema: [],
    messages: {
      hex:
        'Raw hex colour "{{hex}}" is banned. Use a design token ' +
        '(var(--ds-*)), a semantic utility (up / down / warn / accent, ink-*, surface-*), ' +
        'or --color-* theme value instead.',
    },
  },

  create(context) {
    const report = (node, text) => {
      const match = HEX_RE.exec(text);
      if (!match) return;
      context.report({
        node,
        messageId: 'hex',
        data: { hex: match[0] },
      });
    };

    const scanStyleValue = (node) => {
      forEachString(node, report);
    };

    const scanStyleObject = (node) => {
      if (!node) return;
      if (node.type === 'ObjectExpression') {
        for (const prop of node.properties) {
          if (prop.type === 'SpreadElement') {
            scanStyleObject(prop.argument);
            continue;
          }
          if (prop.type !== 'Property') continue;
          const key = prop.key;
          const name =
            key.type === 'Identifier'
              ? key.name
              : key.type === 'Literal'
                ? String(key.value)
                : null;
          if (name && COLOR_KEY_RE.test(name)) scanStyleValue(prop.value);
        }
        return;
      }
      if (node.type === 'TSAsExpression' || node.type === 'TSSatisfiesExpression') {
        scanStyleObject(node.expression);
        return;
      }
      if (node.type === 'ConditionalExpression') {
        scanStyleObject(node.consequent);
        scanStyleObject(node.alternate);
      }
    };

    return {
      JSXAttribute(node) {
        const attr = node.name && node.name.type === 'JSXIdentifier' ? node.name.name : '';
        if (attr === 'className' || attr === 'class') {
          forEachString(node.value, report);
          return;
        }
        if (attr !== 'style') return;
        const value = node.value;
        if (!value) return;
        if (value.type === 'Literal') {
          report(value, value.value);
          return;
        }
        const expression = value.type === 'JSXExpressionContainer' ? value.expression : value;
        scanStyleObject(expression);
      },
    };
  },
};
