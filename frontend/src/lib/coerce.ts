/**
 * Coercion helpers for loosely-typed API payloads. Pure functions only.
 */

/** Finite number from a number | numeric string; `null` for anything else. */
export function toNumber(value: unknown): number | null {
  const n = typeof value === 'string' ? Number(value) : value;
  return typeof n === 'number' && Number.isFinite(n) ? n : null;
}

/**
 * First non-nullish alias wins, exactly like `a ?? b ?? c`.
 *
 * Selection happens BEFORE any coercion, so a present-but-invalid primary key
 * still wins and later fails coercion instead of silently falling through to
 * an alias. Callers keep their existing key precedence — only the repeated
 * `??` chain is centralized here.
 */
export function pickFirst<T>(...candidates: Array<T | null | undefined>): T | null {
  for (const candidate of candidates) {
    if (candidate !== null && candidate !== undefined) return candidate;
  }
  return null;
}
