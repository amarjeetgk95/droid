/**
 * droid/no-component-polling
 *
 * Bans interval-based data polling in `src/components/**` so the P3
 * stream conversion cannot regress (docs/FRONTEND_OVERHAUL_PLAN.md P3-2/P3-3):
 * components consume the unified app stream via props/context; only the
 * allowlisted clocks and pending-legacy desks below may still poll.
 *
 * Flags CallExpressions to:
 *   - `setInterval(...)` (incl. `window.setInterval`, `globalThis.setInterval`)
 *   - `usePolling(...)`
 *   - `useSmartInterval(...)`
 *
 * Scope:
 *   - Only files under `src/components/` are checked.
 *   - `*.test.*` / `*.spec.*` / `__tests__/` files are exempt (tests may
 *     exercise hooks with fake timers).
 *   - Type-only references such as `ReturnType<typeof setInterval>` are not
 *     CallExpressions and are never flagged.
 *
 * The exception list is an explicit, auditable allowlist of exact paths
 * relative to `src/components/`. To convert a desk: remove its polling,
 * then remove its entry here — the design gate fails on any non-allowlisted
 * polling call.
 */

// Exception allowlist: exact paths relative to `frontend/src/components/`.
// Only a 1s visual clock remains; every data-bearing component consumes the
// unified app stream (context) or a hook under `src/hooks/**`.
const PENDING_POLLERS = new Set([
  'common/FreshnessClock.tsx', // clock-only: 1s visual clock, no data fetch
]);

const POLLING_CALLS = new Set(['setInterval', 'usePolling', 'useSmartInterval']);

const COMPONENTS_MARKER = 'src/components/';

function getFilename(context) {
  if (typeof context.getPhysicalFilename === 'function') {
    try {
      const physical = context.getPhysicalFilename();
      if (typeof physical === 'string' && physical) return physical;
    } catch {
      // fall through to context.filename
    }
  }
  if (typeof context.filename === 'string') return context.filename;
  if (typeof context.getFilename === 'function') {
    try {
      return context.getFilename();
    } catch {
      return '';
    }
  }
  return '';
}

function isTestFile(normalized) {
  return /(^|\/)__tests__\//.test(normalized) || /\.(test|spec)\.[^.]+$/.test(normalized);
}

/** Extract the called name for `Ident(...)` and `obj.Ident` / `obj['Ident']`. */
function getCalledName(callee) {
  if (!callee || typeof callee !== 'object') return null;
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression') {
    const prop = callee.property;
    if (!callee.computed && prop && prop.type === 'Identifier') return prop.name;
    if (callee.computed && prop && prop.type === 'Literal' && typeof prop.value === 'string') {
      return prop.value;
    }
  }
  return null;
}

export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow interval-based data polling (setInterval / usePolling / useSmartInterval) in src/components/**; consume the unified app stream instead.',
    },
    schema: [],
    messages: {
      polling:
        '"{{name}}" polling is banned in src/components/** by P3-3. Consume the unified app stream ' +
        'via props/context instead of intervals (visual clocks excepted). ' +
        'If this is a legacy desk awaiting conversion, add its exact path to PENDING_POLLERS with a reason; otherwise remove the call.',
    },
  },

  create(context) {
    const raw = getFilename(context);
    const normalized = String(raw).replace(/\\/g, '/');
    const markerIndex = normalized.indexOf(COMPONENTS_MARKER);
    // Not a component file: out of scope.
    if (markerIndex === -1) return {};
    // Test files legitimately exercise hooks with fake timers.
    if (isTestFile(normalized)) return {};
    const relative = normalized.slice(markerIndex + COMPONENTS_MARKER.length);
    // Explicit, auditable exceptions (clocks + pending conversions).
    if (PENDING_POLLERS.has(relative)) return {};

    return {
      CallExpression(node) {
        const name = getCalledName(node.callee);
        if (name && POLLING_CALLS.has(name)) {
          context.report({ node, messageId: 'polling', data: { name } });
        }
      },
    };
  },
};
