/**
 * Coercion helpers for loosely-typed API payloads. Pure functions only.
 */

export interface ToNumberOptions {
  /** Treat `''` as absent instead of `Number('') === 0`. */
  rejectEmptyString?: boolean;
  /** Treat whitespace-only strings as absent; implies `rejectEmptyString`. */
  rejectBlankString?: boolean;
  /** Parse non-string, non-number values with `Number()` (legacy strict coercers). */
  coerceNonString?: boolean;
}

/**
 * Finite number from a number | numeric string; `null` for anything else.
 * Without options, `''` coerces to `0` exactly as before; the flags reproduce
 * the legacy strict variants without changing the default.
 */
export function toNumber(value: unknown, options: ToNumberOptions = {}): number | null {
  const { rejectEmptyString = false, rejectBlankString = false, coerceNonString = false } =
    options;
  if (typeof value === 'string') {
    if (rejectBlankString && value.trim() === '') return null;
    if (rejectEmptyString && value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (coerceNonString && value !== null && value !== undefined) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
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
