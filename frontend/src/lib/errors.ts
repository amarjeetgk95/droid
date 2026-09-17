/**
 * Canonical extraction of a human-readable message from an unknown thrown
 * value. Precedence (superset of every previous local copy):
 *
 *   1. non-empty `Error.message`
 *   2. a non-blank string thrown directly
 *   3. `fallback`
 *
 * Callers that previously relied on a component-specific fallback must pass it
 * as the second argument so user-visible text stays unchanged.
 */
export function errorMessage(err: unknown, fallback = 'Unexpected error'): string {
  if (err instanceof Error && err.message) return err.message;
  if (typeof err === 'string' && err.trim()) return err;
  return fallback;
}
