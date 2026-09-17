'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  SESSION_EXPIRED_REASON,
  SESSION_EXPIRED_MESSAGE,
  AUTH_NOTICE_MESSAGES,
  getAuthErrorMessage,
  readAuthNotice,
} from '@/components/auth/authMessages';
import { sanitizeReturnUrl } from '@/components/auth/returnUrl';
import {
  Shield,
  Lock,
  Mail,
  Eye,
  EyeOff,
  LogIn,
  AlertCircle,
  Loader2,
  Cpu,
  Zap,
  KeyRound,
  ArrowLeft,
} from 'lucide-react';

type AuthMode = 'signin' | 'forgot';

const EMAIL_INPUT_ID = 'login-email';
const PASSWORD_INPUT_ID = 'login-password';
const ERROR_REGION_ID = 'login-error';

function LoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const {
    isAuthenticated,
    loading: authLoading,
    isDemoMode,
    isPasswordRecovery,
    signIn,
    sendPasswordReset,
    updatePassword,
    clearPasswordRecovery,
  } = useAuth();

  const [mode, setMode] = useState<AuthMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [recoveryHint, setRecoveryHint] = useState(false);

  // A recovery session (reset link opened) always wins the UI. The provider's
  // PASSWORD_RECOVERY event is authoritative; the URL sniff covers flow types
  // where the event arrives late or not at all.
  const isRecovery = isPasswordRecovery || recoveryHint;
  const effectiveMode: AuthMode | 'recovery' = isRecovery ? 'recovery' : mode;

  // Sanitize the return URL for EVERY navigation path. The query value is
  // attacker-controlled and Next.js executes `javascript:` URLs passed to
  // router.push/replace if they are not validated.
  const requestedReturnUrl = sanitizeReturnUrl(searchParams.get('returnUrl'));
  const returnUrl =
    requestedReturnUrl === '/login' ||
    requestedReturnUrl.startsWith('/login?') ||
    requestedReturnUrl.startsWith('/login#')
      ? '/'
      : requestedReturnUrl;

  // ---------------------------------------------------------------------------
  // Message shown after a session-expiry redirect or a failed remote sign-out.
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (searchParams.get('reason') === SESSION_EXPIRED_REASON) {
      setNotice(SESSION_EXPIRED_MESSAGE);
    }
    const stored = readAuthNotice();
    if (stored) {
      setNotice(AUTH_NOTICE_MESSAGES[stored]);
    }
    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    if (hash.includes('type=recovery') || searchParams.get('type') === 'recovery') {
      setRecoveryHint(true);
    }
  }, [searchParams]);

  // ---------------------------------------------------------------------------
  // Single authoritative navigation path: when the provider reports an
  // authenticated user, leave /login. The submit handlers below never navigate
  // themselves (previously both did, causing a double push).
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (authLoading || !isAuthenticated || isRecovery) return;
    router.replace(returnUrl);
  }, [authLoading, isAuthenticated, isRecovery, router, returnUrl]);

  const clearFeedback = () => {
    setError(null);
    setInfo(null);
  };

  const handleSignInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearFeedback();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError('Please enter your Email / Terminal ID.');
      return;
    }
    if (!password) {
      setError('Please enter your Password.');
      return;
    }

    try {
      setSubmitting(true);
      await signIn(trimmedEmail, password);
      // Navigation is owned by the isAuthenticated effect above.
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleForgotSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearFeedback();

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError('Enter your account email address first.');
      return;
    }

    try {
      setSubmitting(true);
      await sendPasswordReset(trimmedEmail);
      setInfo(
        `If an account exists for ${trimmedEmail}, a password-reset link is on its way. Open it to set a new password.`,
      );
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRecoverySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearFeedback();

    if (newPassword.length < 6) {
      setError('Password must be at least 6 characters long.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('The two passwords do not match.');
      return;
    }

    try {
      setSubmitting(true);
      await updatePassword(newPassword);
      setInfo('Password updated. Signing you in…');
    } catch (err: unknown) {
      setError(getAuthErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancelRecovery = () => {
    clearFeedback();
    setRecoveryHint(false);
    clearPasswordRecovery();
  };

  const switchToForgot = () => {
    clearFeedback();
    setMode('forgot');
  };

  const switchToSignIn = () => {
    clearFeedback();
    setMode('signin');
  };

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="w-5 h-5 animate-spin text-primary" />
          <span className="text-sm">Connecting to DROID Terminal...</span>
        </div>
      </div>
    );
  }

  const heading =
    effectiveMode === 'recovery'
      ? 'Set a new password'
      : effectiveMode === 'forgot'
        ? 'Reset your password'
        : 'Login to Droid';

  const subheading =
    effectiveMode === 'recovery'
      ? 'Choose a new password for your account'
      : effectiveMode === 'forgot'
        ? 'We will email you a secure reset link'
        : 'F&O Market Analytics & Intelligence Terminal';

  const submitLabel =
    effectiveMode === 'recovery' ? (
      <>
        <KeyRound className="w-4 h-4" />
        <span>Set new password</span>
      </>
    ) : effectiveMode === 'forgot' ? (
      <>
        <Mail className="w-4 h-4" />
        <span>Send reset link</span>
      </>
    ) : (
      <>
        <LogIn className="w-4 h-4" />
        <span>Log in</span>
      </>
    );

  const submitBusyLabel =
    effectiveMode === 'recovery' ? 'Updating…' : effectiveMode === 'forgot' ? 'Sending…' : 'Authenticating…';

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background p-4 relative">
      <div className="w-full max-w-[380px] relative z-10">
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center h-10 w-10 rounded-[4px] bg-primary text-white font-bold text-lg mb-3 shadow-xs">
            <span>D</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">{heading}</h1>
          <p className="text-xs text-muted-foreground mt-1">{subheading}</p>
        </div>

        {/* Auth Card */}
        <div className="bg-card border border-border rounded-[4px] shadow-[0_1px_2px_rgba(0,0,0,0.04)] p-6 sm:p-7">
          {isDemoMode && (
            <div
              role="status"
              aria-live="polite"
              className="mb-4 p-3 rounded-[3px] bg-warn-wash border border-warn-line text-warn-ink text-xs flex items-start gap-2"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-warn" />
              <div className="leading-relaxed">
                <span className="font-semibold">Authentication is not configured (demo mode).</span>{' '}
                Set{' '}
                <code className="bg-warn-wash px-1 py-0.5 rounded-[2px] text-[11px]">
                  NEXT_PUBLIC_SUPABASE_URL
                </code>{' '}
                and{' '}
                <code className="bg-warn-wash px-1 py-0.5 rounded-[2px] text-[11px]">
                  NEXT_PUBLIC_SUPABASE_ANON_KEY
                </code>{' '}
                in <code className="bg-warn-wash px-1 py-0.5 rounded-[2px] text-[11px]">frontend/.env.local</code>{' '}
                and restart the dev server. Until then sign-in is disabled because credentials cannot be verified.
              </div>
            </div>
          )}

          {/* Session / lifecycle notices (session expired, failed remote revoke) */}
          {notice && (
            <div
              role="status"
              aria-live="polite"
              className="mb-4 p-3 rounded-[3px] bg-warn-wash border border-warn-line text-warn-ink text-xs flex items-start gap-2.5"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="leading-relaxed">{notice}</div>
            </div>
          )}

          {/* Errors — announced by assistive tech the moment they appear */}
          {error && (
            <div
              id={ERROR_REGION_ID}
              role="alert"
              aria-live="assertive"
              className="mb-4 p-3 rounded-[3px] bg-down-wash border border-down-line text-down text-xs flex items-start gap-2.5"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="leading-relaxed">{error}</div>
            </div>
          )}

          {/* Success / informational feedback */}
          {info && (
            <div
              role="status"
              aria-live="polite"
              className="mb-4 p-3 rounded-[3px] bg-up-wash border border-up-line text-up-strong text-xs flex items-start gap-2.5"
            >
              <Shield className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="leading-relaxed">{info}</div>
            </div>
          )}

          {effectiveMode === 'signin' && (
            // noValidate: validation copy comes from the handler below, so the
            // same message is used by every browser and by assistive tech.
            <form onSubmit={handleSignInSubmit} noValidate className="space-y-4">
              {/* Email / ID Input */}
              <div>
                <label
                  htmlFor={EMAIL_INPUT_ID}
                  className="block text-xs font-medium text-foreground mb-1"
                >
                  User ID / Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    id={EMAIL_INPUT_ID}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="trader@droid.terminal"
                    required
                    autoFocus
                    autoComplete="username"
                    disabled={isDemoMode}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? ERROR_REGION_ID : undefined}
                    className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors disabled:opacity-50"
                  />
                </div>
              </div>

              {/* Password Input */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label
                    htmlFor={PASSWORD_INPUT_ID}
                    className="block text-xs font-medium text-foreground"
                  >
                    Password
                  </label>
                  <button
                    type="button"
                    onClick={switchToForgot}
                    disabled={isDemoMode}
                    className="text-[11px] font-medium text-primary hover:text-primary/80 disabled:opacity-50 cursor-pointer"
                  >
                    Forgot password?
                  </button>
                </div>
                <div className="relative">
                  <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    id={PASSWORD_INPUT_ID}
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    autoComplete="current-password"
                    disabled={isDemoMode}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? ERROR_REGION_ID : undefined}
                    className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-10 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors disabled:opacity-50"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((visible) => !visible)}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    aria-pressed={showPassword}
                    title={showPassword ? 'Hide password' : 'Show password'}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-[2px] text-muted-foreground hover:text-foreground transition-colors cursor-pointer focus-visible:ring-1 focus-visible:ring-ring"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={submitting || isDemoMode}
                className="w-full mt-2 h-10 px-4 rounded-[4px] bg-primary text-white text-xs font-semibold hover:bg-primary/90 active:bg-primary/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{submitBusyLabel}</span>
                  </>
                ) : (
                  submitLabel
                )}
              </button>
            </form>
          )}

          {effectiveMode === 'forgot' && (
            <form onSubmit={handleForgotSubmit} noValidate className="space-y-4">
              <div>
                <label
                  htmlFor={EMAIL_INPUT_ID}
                  className="block text-xs font-medium text-foreground mb-1"
                >
                  Account Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    id={EMAIL_INPUT_ID}
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="trader@droid.terminal"
                    required
                    autoFocus
                    autoComplete="username"
                    disabled={isDemoMode}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? ERROR_REGION_ID : undefined}
                    className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors disabled:opacity-50"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting || isDemoMode}
                className="w-full mt-2 h-10 px-4 rounded-[4px] bg-primary text-white text-xs font-semibold hover:bg-primary/90 active:bg-primary/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{submitBusyLabel}</span>
                  </>
                ) : (
                  submitLabel
                )}
              </button>

              <button
                type="button"
                onClick={switchToSignIn}
                className="w-full h-8 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to sign in</span>
              </button>
            </form>
          )}

          {effectiveMode === 'recovery' && (
            <form onSubmit={handleRecoverySubmit} noValidate className="space-y-4">
              <div>
                <label
                  htmlFor="login-new-password"
                  className="block text-xs font-medium text-foreground mb-1"
                >
                  New password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    id="login-new-password"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="At least 6 characters"
                    required
                    autoFocus
                    minLength={6}
                    autoComplete="new-password"
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? ERROR_REGION_ID : undefined}
                    className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                  />
                </div>
              </div>

              <div>
                <label
                  htmlFor="login-confirm-password"
                  className="block text-xs font-medium text-foreground mb-1"
                >
                  Confirm new password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    id="login-confirm-password"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Repeat the new password"
                    required
                    minLength={6}
                    autoComplete="new-password"
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? ERROR_REGION_ID : undefined}
                    className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full mt-2 h-10 px-4 rounded-[4px] bg-primary text-white text-xs font-semibold hover:bg-primary/90 active:bg-primary/80 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{submitBusyLabel}</span>
                  </>
                ) : (
                  submitLabel
                )}
              </button>

              <button
                type="button"
                onClick={handleCancelRecovery}
                className="w-full h-8 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Cancel and sign in again</span>
              </button>
            </form>
          )}
        </div>

        {/* Security & System Footer */}
        <div className="mt-5 flex items-center justify-center gap-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <Shield className="w-3.5 h-3.5 text-up" />
            <span>Supabase Auth</span>
          </div>
          <span>•</span>
          <div className="flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-warn" />
            <span>JWT Secured</span>
          </div>
          <span>•</span>
          <div className="flex items-center gap-1">
            <Cpu className="w-3.5 h-3.5 text-primary" />
            <span>FastAPI Backend</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background text-foreground">
          <div className="flex items-center gap-3 text-muted-foreground">
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
            <span className="text-sm">Loading login terminal...</span>
          </div>
        </div>
      }
    >
      <LoginContent />
    </Suspense>
  );
}
