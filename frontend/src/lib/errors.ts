export interface ErrorMessageOptions {
  /** Ignore an `Error.message` that is only whitespace. */
  rejectBlankErrorMessage?: boolean;
  /** Also accept a non-empty `message` string on a thrown plain object. */
  objectMessage?: boolean;
}

/**
 * Canonical extraction of a human-readable message from an unknown thrown
 * value. Precedence (superset of every previous local copy):
 *
 *   1. non-empty `Error.message`
 *   2. a non-blank string thrown directly
 *   3. `fallback`
 *
 * Callers that previously relied on a component-specific fallback must pass it
 * as the second argument so user-visible text stays unchanged. The options
 * reproduce stricter legacy variants without changing the default.
 */
export function errorMessage(
  err: unknown,
  fallback = 'Unexpected error',
  options: ErrorMessageOptions = {},
): string {
  const { rejectBlankErrorMessage = false, objectMessage = false } = options;
  if (err instanceof Error && err.message && (!rejectBlankErrorMessage || err.message.trim())) {
    return err.message;
  }
  if (typeof err === 'string' && err.trim()) return err;
  if (objectMessage && err !== null && typeof err === 'object') {
    const message = (err as { message?: unknown }).message;
    if (typeof message === 'string' && message.length > 0) return message;
  }
  return fallback;
}
