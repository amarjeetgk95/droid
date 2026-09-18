'use client';

import { createContext, useContext, useEffect, useRef, useState, ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabase';
import { api } from '@/lib/api';
import {
  SESSION_EXPIRED_REASON,
  getAuthErrorMessage,
  writeAuthNotice,
} from './authMessages';
import { sanitizeReturnUrl } from './returnUrl';

export interface AuthUser {
  id: string;
  email: string | null;
  role?: string;
  lastSignInAt?: string;
}

export interface SignUpResult {
  requiresVerification: boolean;
  message: string;
}

export interface AuthContextType {
  user: AuthUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  isConfigured: boolean;
  isDemoMode: boolean;
  /** True while Supabase reports a PASSWORD_RECOVERY session (reset link opened). */
  isPasswordRecovery: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
  /** Sends a Supabase password-reset email; the link returns to /login. */
  sendPasswordReset: (email: string) => Promise<void>;
  /** Sets a new password for the recovery session. */
  updatePassword: (newPassword: string) => Promise<void>;
  /** Abandons the recovery session and returns the UI to sign-in. */
  clearPasswordRecovery: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAuthenticated: false,
  isConfigured: false,
  isDemoMode: false,
  isPasswordRecovery: false,
  signIn: async () => {},
  signUp: async () => ({ requiresVerification: false, message: '' }),
  signOut: async () => {},
  sendPasswordReset: async () => {},
  updatePassword: async () => {},
  clearPasswordRecovery: () => {},
});

const NOT_CONFIGURED_MESSAGE =
  'Authentication is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in frontend/.env.local, then restart the dev server.';

type SupabaseUserLike = {
  id: string;
  email?: string | null;
  role?: string;
  last_sign_in_at?: string;
};

function toAuthUser(user: SupabaseUserLike): AuthUser {
  return {
    id: user.id,
    email: user.email ?? null,
    role: user.role || 'user',
    lastSignInAt: user.last_sign_in_at,
  };
}

/**
 * Drop every locally cached artifact of the ending session: the API bearer
 * token and the broker-auth markers. There is no broker revoke endpoint on the
 * backend (see report), so stale local state must not survive into the next
 * sign-in.
 */
function clearSessionLocalState(): void {
  api.setToken(null);
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('droid_last_auth_time');
    localStorage.removeItem('droid_last_auth_provider');
  } catch {
    // Storage unavailable (private mode) — nothing to clear.
  }
}

type UnauthorizedDetail = { url?: string; kind?: 'session' | 'broker' } | undefined;

export function AuthProvider({ children }: { children: ReactNode }) {
  const isConfigured = !!supabase;
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [isPasswordRecovery, setIsPasswordRecovery] = useState(false);
  const handlingUnauthorizedRef = useRef(false);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      setLoading(false);
    };

    // Deadlock guard: getSession() must never freeze the app on
    // "Verifying credentials & session...". If it neither resolves nor
    // rejects within the timeout, enter the controlled unauthenticated
    // state (AuthGuard redirects to /login) instead of hanging forever.
    const guard = setTimeout(() => {
      console.error('Supabase session check timed out; continuing unauthenticated.');
      api.setToken(null);
      finish();
    }, 10000);

    // Check existing Supabase session on mount
    supabase.auth.getSession().then(({ data: { session }, error }) => {
      if (error) {
        console.error('Error fetching Supabase session:', error);
      }
      if (session?.user) {
        setUser(toAuthUser(session.user));
        api.setToken(session.access_token);
      } else {
        setUser(null);
        api.setToken(null);
      }
      clearTimeout(guard);
      finish();
    }).catch((err) => {
      console.error('Supabase session check failed:', err);
      setUser(null);
      api.setToken(null);
      clearTimeout(guard);
      finish();
    });

    // Listen for auth state changes (sign in, sign out, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'PASSWORD_RECOVERY') {
        setIsPasswordRecovery(true);
      }
      if (event === 'SIGNED_OUT') {
        setIsPasswordRecovery(false);
      }
      if (session?.user) {
        // A fresh authenticated session opens a new expiry cycle.
        handlingUnauthorizedRef.current = false;
        setUser(toAuthUser(session.user));
        api.setToken(session.access_token);
      } else {
        setUser(null);
        api.setToken(null);
      }
      clearTimeout(guard);
      finish();
    });

    return () => {
      clearTimeout(guard);
      subscription.unsubscribe();
    };
  }, []);

  // Backend 401s dispatch `auth:unauthorized` on window. Without a listener the
  // app keeps polling with a dead token (silent infinite 401 loop). End the
  // local session and bounce to /login with an explicit "session expired"
  // reason. Guards below make a redirect loop impossible: never react while
  // already on /login, never react without a loaded token, and collapse bursts.
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const handleUnauthorized = (event: Event) => {
      const detail = (event as CustomEvent<UnauthorizedDetail>).detail;

      // Broker-token expiry is a gateway concern, not a platform-session
      // concern: sign the operator out of the broker, not the terminal.
      // (The API client currently dispatches only `{ url }`; it must add
      // `kind: 'broker'` for this branch to fire — see report.)
      if (detail?.kind === 'broker') {
        window.dispatchEvent(new CustomEvent('broker:session-expired'));
        return;
      }

      if (window.location.pathname.startsWith('/login')) return;
      if (!api.getToken()) return;
      if (handlingUnauthorizedRef.current) return;
      handlingUnauthorizedRef.current = true;

      void (async () => {
        console.warn('Backend rejected the session token (401); signing out locally.');
        try {
          await supabase?.auth.signOut({ scope: 'local' });
        } catch (err) {
          console.error('Failed to clear the expired Supabase session locally:', err);
        }
        setUser(null);
        clearSessionLocalState();

        const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
        const returnUrl = sanitizeReturnUrl(current, '/');
        // The query reason is for hard loads; the stored notice survives the
        // AuthGuard redirect that races this navigation and would drop it.
        writeAuthNotice('session_expired');
        router.replace(
          `/login?reason=${SESSION_EXPIRED_REASON}&returnUrl=${encodeURIComponent(returnUrl)}`,
        );
      })();
    };

    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, [router]);

  const signIn = async (email: string, password: string) => {
    if (!supabase) {
      throw new Error(NOT_CONFIGURED_MESSAGE);
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      throw new Error('Please provide both Email ID and Password.');
    }

    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email: trimmedEmail,
        password,
      });
      if (error) throw new Error(getAuthErrorMessage(error.message));
      if (data.session) {
        setUser(toAuthUser(data.session.user));
        api.setToken(data.session.access_token);
      }
    } catch (err) {
      throw new Error(getAuthErrorMessage(err));
    }
  };

  const signUp = async (email: string, password: string): Promise<SignUpResult> => {
    if (!supabase) {
      throw new Error(NOT_CONFIGURED_MESSAGE);
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      throw new Error('Please provide both Email ID and Password.');
    }

    if (password.length < 6) {
      throw new Error('Password must be at least 6 characters long.');
    }

    try {
      const { data, error } = await supabase.auth.signUp({
        email: trimmedEmail,
        password,
      });
      if (error) throw new Error(getAuthErrorMessage(error.message));

      if (data.session) {
        setUser(toAuthUser(data.session.user));
        api.setToken(data.session.access_token);
        return {
          requiresVerification: false,
          message: 'Account created and logged in successfully!',
        };
      }

      return {
        requiresVerification: true,
        message: 'Account created! Please check your email to verify and activate your account before logging in.',
      };
    } catch (err) {
      throw new Error(getAuthErrorMessage(err));
    }
  };

  const sendPasswordReset = async (email: string) => {
    if (!supabase) {
      throw new Error(NOT_CONFIGURED_MESSAGE);
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      throw new Error('Enter your account email address first.');
    }

    try {
      const redirectTo =
        typeof window !== 'undefined' ? `${window.location.origin}/login` : undefined;
      const { error } = await supabase.auth.resetPasswordForEmail(
        trimmedEmail,
        redirectTo ? { redirectTo } : undefined,
      );
      if (error) throw new Error(getAuthErrorMessage(error.message));
    } catch (err) {
      throw new Error(getAuthErrorMessage(err));
    }
  };

  const updatePassword = async (newPassword: string) => {
    if (!supabase) {
      throw new Error(NOT_CONFIGURED_MESSAGE);
    }
    if (!newPassword) {
      throw new Error('Enter a new password.');
    }
    if (newPassword.length < 6) {
      throw new Error('Password must be at least 6 characters long.');
    }

    try {
      const { data, error } = await supabase.auth.updateUser({ password: newPassword });
      if (error) throw new Error(getAuthErrorMessage(error.message));
      if (data.user) {
        setUser(toAuthUser(data.user));
      }
      setIsPasswordRecovery(false);
    } catch (err) {
      throw new Error(getAuthErrorMessage(err));
    }
  };

  const clearPasswordRecovery = () => {
    setIsPasswordRecovery(false);
    setUser(null);
    clearSessionLocalState();
    if (supabase) {
      void supabase.auth.signOut({ scope: 'local' }).catch((err) => {
        console.warn('Failed to clear the recovery session locally:', err);
      });
    }
  };

  const signOut = async () => {
    let providerError: string | null = null;

    if (supabase) {
      try {
        const { error } = await supabase.auth.signOut();
        if (error) providerError = error.message;
      } catch (err) {
        providerError = err instanceof Error ? err.message : String(err);
      }

      if (providerError) {
        console.error('Supabase sign out failed:', providerError);
        // Fail closed on this device: clear the local session even when the
        // provider could not revoke the refresh token.
        try {
          await supabase.auth.signOut({ scope: 'local' });
        } catch (err) {
          console.error('Local Supabase session clear also failed:', err);
        }
      }
    }

    setUser(null);
    setIsPasswordRecovery(false);
    clearSessionLocalState();

    if (providerError) {
      // Visible failure handling across the navigation the caller performs.
      writeAuthNotice('logout_incomplete');
      throw new Error(
        'Signed out on this device, but the authentication provider could not be reached to revoke the remote session.',
      );
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        isConfigured,
        isDemoMode: !isConfigured,
        isPasswordRecovery,
        signIn,
        signUp,
        signOut,
        sendPasswordReset,
        updatePassword,
        clearPasswordRecovery,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
