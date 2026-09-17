import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || '';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

/**
 * Session persistence — accepted risk, documented.
 *
 * `createClient` defaults to `persistSession: true` with `localStorage`, so the
 * Supabase access + refresh JWTs survive reloads and are shared across tabs.
 * Consequence: any successful XSS on this origin can exfiltrate a long-lived
 * refresh token. The defaults are kept deliberately:
 *   - `sessionStorage` would break cross-tab session sharing and "stay signed
 *     in across restarts" (a product/UX decision, not this module's call);
 *   - cookie-based storage needs a server-side auth proxy, but this frontend is
 *     statically hosted while the API is a separate FastAPI origin.
 * Compensating controls in this codebase: no `dangerouslySetInnerHTML` on auth
 * surfaces, provider revocation on sign-out (AuthProvider.signOut), and a
 * fail-closed backend. Revisit with a CSP + cookie migration if the threat
 * model changes.
 */
export const supabase = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;
