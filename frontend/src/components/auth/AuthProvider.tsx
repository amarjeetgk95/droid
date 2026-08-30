'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { supabase } from '@/lib/supabase';
import { api } from '@/lib/api';

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
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  isAuthenticated: false,
  isConfigured: false,
  isDemoMode: false,
  signIn: async () => {},
  signUp: async () => ({ requiresVerification: false, message: '' }),
  signOut: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const isConfigured = !!supabase;
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!supabase) {
      setLoading(false);
      return;
    }

    // Check existing Supabase session on mount
    supabase.auth.getSession().then(({ data: { session }, error }) => {
      if (error) {
        console.error('Error fetching Supabase session:', error);
      }
      if (session?.user) {
        setUser({
          id: session.user.id,
          email: session.user.email ?? null,
          role: session.user.role || 'user',
          lastSignInAt: session.user.last_sign_in_at,
        });
        api.setToken(session.access_token);
      } else {
        setUser(null);
        api.setToken(null);
      }
      setLoading(false);
    });

    // Listen for auth state changes (sign in, sign out, token refresh)
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session?.user) {
        setUser({
          id: session.user.id,
          email: session.user.email ?? null,
          role: session.user.role || 'user',
          lastSignInAt: session.user.last_sign_in_at,
        });
        api.setToken(session.access_token);
      } else {
        setUser(null);
        api.setToken(null);
      }
      setLoading(false);
    });

    return () => {
      subscription.unsubscribe();
    };
  }, []);

  const signIn = async (email: string, password: string) => {
    if (!supabase) {
      throw new Error('Supabase authentication is not configured in .env.local');
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      throw new Error('Please provide both Email ID and Password.');
    }

    const { data, error } = await supabase.auth.signInWithPassword({
      email: trimmedEmail,
      password,
    });

    if (error) {
      throw new Error(error.message || 'Failed to sign in. Please check your credentials.');
    }

    if (data.session) {
      setUser({
        id: data.session.user.id,
        email: data.session.user.email ?? null,
        role: data.session.user.role || 'user',
        lastSignInAt: data.session.user.last_sign_in_at,
      });
      api.setToken(data.session.access_token);
    }
  };

  const signUp = async (email: string, password: string): Promise<SignUpResult> => {
    if (!supabase) {
      throw new Error('Supabase authentication is not configured in .env.local');
    }

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      throw new Error('Please provide both Email ID and Password.');
    }

    if (password.length < 6) {
      throw new Error('Password must be at least 6 characters long.');
    }

    const { data, error } = await supabase.auth.signUp({
      email: trimmedEmail,
      password,
    });

    if (error) {
      throw new Error(error.message || 'Failed to register account.');
    }

    if (data.session) {
      setUser({
        id: data.session.user.id,
        email: data.session.user.email ?? null,
        role: data.session.user.role || 'user',
      });
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
  };

  const signOut = async () => {
    if (supabase) {
      try {
        await supabase.auth.signOut();
      } catch (err) {
        console.error('Supabase sign out error:', err);
      }
    }
    setUser(null);
    api.setToken(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        isConfigured,
        isDemoMode: !isConfigured,
        signIn,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
