'use client';

import React, { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
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
} from 'lucide-react';

function LoginContent() {
 const router = useRouter();
 const searchParams = useSearchParams();
 const returnUrl = searchParams.get('returnUrl') || '/';

 const { signIn, isAuthenticated, loading: authLoading, isConfigured } = useAuth();

 const [email, setEmail] = useState('');
 const [password, setPassword] = useState('');
 const [showPassword, setShowPassword] = useState(false);
 const [submitting, setSubmitting] = useState(false);
 const [error, setError] = useState<string | null>(null);

 // If already authenticated, redirect to destination
 useEffect(() => {
 if (!authLoading && isAuthenticated) {
  router.replace(returnUrl);
 }
 }, [authLoading, isAuthenticated, router, returnUrl]);

 const handleAuthSubmit = async (e: React.FormEvent) => {
 e.preventDefault();
 setError(null);

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
  router.push(returnUrl);
 } catch (err: unknown) {
  const msg = err instanceof Error ? err.message : 'Authentication failed. Please check your credentials.';
  setError(msg);
 } finally {
  setSubmitting(false);
 }
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

 return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background p-4 relative">
      <div className="w-full max-w-[380px] relative z-10">
        {/* Brand Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center h-10 w-10 rounded-[4px] bg-primary text-white font-bold text-lg mb-3 shadow-xs">
            <span>D</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Login to Droid
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            F&O Market Analytics & Intelligence Terminal
          </p>
        </div>

        {/* Auth Card */}
        <div className="bg-card border border-border rounded-[4px] shadow-[0_1px_2px_rgba(0,0,0,0.04)] p-6 sm:p-7">
          {!isConfigured && (
            <div className="mb-4 p-3 rounded-[3px] bg-[#fff8e8] border border-[rgba(245,158,11,0.3)] text-amber-800 text-xs flex items-start gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
              <div>
                <span className="font-semibold">Configuration Warning:</span> Supabase environment variables are missing in{' '}
                <code className="bg-amber-100 px-1 py-0.5 rounded-[2px] text-[11px]">.env.local</code>.
              </div>
            </div>
          )}

          {/* Alerts */}
          {error && (
            <div className="mb-4 p-3 rounded-[3px] bg-[#fdf0ef] border border-[rgba(223,81,76,0.3)] text-[#c62828] text-xs flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="leading-relaxed">{error}</div>
            </div>
          )}

          {/* ID & Password Form */}
          <form onSubmit={handleAuthSubmit} className="space-y-4">
            {/* Email / ID Input */}
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                User ID / Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="trader@droid.terminal"
                  required
                  autoFocus
                  autoComplete="username"
                  className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
              </div>
            </div>

            {/* Password Input */}
            <div>
              <label className="block text-xs font-medium text-foreground mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  className="w-full h-10 bg-card border border-border rounded-[4px] pl-9 pr-10 text-xs text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  tabIndex={-1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting || !isConfigured}
              className="w-full mt-2 h-10 px-4 rounded-[4px] bg-primary text-white text-xs font-semibold hover:bg-[#2a6fc0] active:bg-[#245fa5] disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 cursor-pointer shadow-xs"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Authenticating…</span>
                </>
              ) : (
                <>
                  <LogIn className="w-4 h-4" />
                  <span>Log in</span>
                </>
              )}
            </button>
          </form>
        </div>

        {/* Security & System Footer */}
        <div className="mt-5 flex items-center justify-center gap-3 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <Shield className="w-3.5 h-3.5 text-emerald-600" />
            <span>Supabase Auth</span>
          </div>
          <span>•</span>
          <div className="flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-amber-600" />
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
