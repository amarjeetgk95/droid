/**
 * Return-URL sanitizer.
 *
 * Every `returnUrl` (login query string, AuthGuard redirect, session-expiry
 * bounce) is attacker-controlled input that eventually reaches
 * `router.push` / `router.replace`. Next.js explicitly documents that
 * unsanitized URLs can execute `javascript:` payloads, and a scheme-relative
 * `//evil.example` navigates off-site without warning. Only same-origin
 * relative paths are allowed here; anything else collapses to the fallback.
 */

const FALLBACK = '/';

/** Opaque base used to parse relative input. Never navigated to. */
const PARSE_BASE = 'https://droid.invalid';

export function sanitizeReturnUrl(
  raw: string | null | undefined,
  fallback: string = FALLBACK,
): string {
  if (typeof raw !== 'string') return fallback;
  const value = raw.trim();
  if (!value) return fallback;

  // Must be a path — never a scheme (`javascript:`, `https:`), a
  // scheme-relative host (`//evil.example`) or a backslash trick
  // (`/\evil.example`) that browsers normalise to `//evil.example`.
  if (value[0] !== '/') return fallback;
  if (value[1] === '/' || value[1] === '\\') return fallback;
  if (/[\u0000-\u001f\u007f]/.test(value)) return fallback;

  try {
    const parsed = new URL(value, PARSE_BASE);
    if (parsed.origin !== PARSE_BASE) return fallback;

    // Rebuild from the parser so dot-segments and backslashes are normalised
    // (search + hash preserved). Normalisation itself can produce a
    // protocol-relative path, e.g. `/..//evil` -> `//evil`, so re-check.
    const sanitized = `${parsed.pathname}${parsed.search}${parsed.hash}`;
    if (!sanitized.startsWith('/')) return fallback;
    if (sanitized.startsWith('//') || sanitized.startsWith('/\\')) return fallback;
    return sanitized;
  } catch {
    return fallback;
  }
}
