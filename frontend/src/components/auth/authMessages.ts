/**
 * Human-readable auth messaging + one-shot session notices.
 *
 * Supabase and the browser surface transport-level strings ("Failed to fetch",
 * "Email not confirmed", "AuthRetryableFetchError: ..."). Those are never shown
 * verbatim: every known failure is mapped to operator-language copy, unknown
 * messages are stripped of technical prefixes, and empty input gets a stable
 * fallback. `writeAuthNotice`/`readAuthNotice` carry a failure across a hard
 * navigation (logout -> /login) so it is shown instead of being lost with the
 * unmounted component.
 */

export const SESSION_EXPIRED_REASON = 'session_expired';
export const AUTH_NOTICE_STORAGE_KEY = 'droid_auth_notice';

/** Notice lifetime — a stale notice must not surface in a later session. */
const NOTICE_TTL_MS = 60_000;

export type AuthNoticeKind = 'logout_incomplete' | 'session_expired';

export type AuthNotice = {
  kind: AuthNoticeKind;
  at: number;
};

export const AUTH_NOTICE_MESSAGES: Record<AuthNoticeKind, string> = {
  logout_incomplete:
    "You were signed out on this device, but the authentication provider could not be reached to revoke the remote session. Sign out again once you are back online.",
  session_expired: 'Your session expired or was revoked. Sign in again to continue.',
};

export const SESSION_EXPIRED_MESSAGE =
  'Your session expired or was revoked. Sign in again to continue.';

export const DEFAULT_AUTH_ERROR =
  'Authentication failed. Check your credentials and try again.';

type Rule = {
  pattern: RegExp;
  message: string | ((match: RegExpMatchArray) => string);
};

const RULES: Rule[] = [
  {
    pattern: /failed to fetch|networkerror|network error|load failed|fetch failed|network request failed/i,
    message: 'Cannot reach the authentication service. Check your connection and try again.',
  },
  {
    pattern: /email not confirmed|email_not_confirmed/i,
    message:
      'This email has not been verified yet. Open the confirmation link in your inbox, then sign in again.',
  },
  {
    pattern: /invalid login credentials|invalid credentials/i,
    message: 'Incorrect email or password.',
  },
  {
    pattern: /over_email_send_rate_limit|over_request_rate_limit|too many requests|rate limit|for security purposes/i,
    message: 'Too many attempts. Wait a minute, then try again.',
  },
  {
    pattern: /user already registered|already been registered/i,
    message: 'An account with this email already exists. Sign in instead.',
  },
  {
    pattern: /signups? (are )?not allowed|signup(s)? disabled/i,
    message: 'Account creation is disabled on this terminal. Contact an administrator.',
  },
  {
    pattern: /user not found/i,
    message: 'No account exists for this email address.',
  },
  {
    pattern: /email link is invalid or has expired|otp_expired|token has expired/i,
    message: 'That link is invalid or has expired. Request a new one.',
  },
  {
    pattern: /auth session missing|session_not_found|refresh token/i,
    message: 'Your session has expired. Sign in again to continue.',
  },
  {
    pattern: /email address .*invalid|invalid email/i,
    message: 'Enter a valid email address.',
  },
  {
    pattern: /password should be at least (\d+)/i,
    message: (match) => `Password must be at least ${match[1]} characters long.`,
  },
  {
    pattern: /weak password/i,
    message: 'Choose a stronger password (at least 6 characters).',
  },
];

/**
 * Map any thrown/returned auth failure to a human sentence. Safe to call twice
 * on already-mapped copy: every mapped string is a fixed point of the rules.
 */
function extractRawMessage(err: unknown): string {
  if (typeof err === 'string') return err;
  if (err instanceof Error) return err.message;
  if (err && typeof err === 'object') {
    const record = err as { message?: unknown; error_description?: unknown };
    if (typeof record.message === 'string') return record.message;
    if (typeof record.error_description === 'string') return record.error_description;
  }
  return '';
}

export function getAuthErrorMessage(err: unknown, fallback: string = DEFAULT_AUTH_ERROR): string {
  const message = extractRawMessage(err)
    .replace(/^(AuthApiError|AuthRetryableFetchError|AuthError|TypeError|Error):\s*/i, '')
    .trim();
  if (!message) return fallback;

  for (const rule of RULES) {
    const match = message.match(rule.pattern);
    if (match) {
      return typeof rule.message === 'function' ? rule.message(match) : rule.message;
    }
  }
  return message;
}

/** Persist a cross-navigation notice. Best-effort (private mode may refuse). */
export function writeAuthNotice(kind: AuthNoticeKind): void {
  if (typeof window === 'undefined') return;
  try {
    const notice: AuthNotice = { kind, at: Date.now() };
    sessionStorage.setItem(AUTH_NOTICE_STORAGE_KEY, JSON.stringify(notice));
  } catch {
    // Storage unavailable — the caller still throws/console.errors the failure.
  }
}

/** Read and clear a pending notice. Returns null when absent or stale. */
export function readAuthNotice(): AuthNoticeKind | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(AUTH_NOTICE_STORAGE_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(AUTH_NOTICE_STORAGE_KEY);
    const parsed = JSON.parse(raw) as Partial<AuthNotice> | null;
    if (!parsed || typeof parsed.kind !== 'string' || typeof parsed.at !== 'number') return null;
    if (Date.now() - parsed.at > NOTICE_TTL_MS) return null;
    return parsed.kind in AUTH_NOTICE_MESSAGES ? (parsed.kind as AuthNoticeKind) : null;
  } catch {
    return null;
  }
}
