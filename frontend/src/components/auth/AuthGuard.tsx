'use client';

import { useEffect, ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from './AuthProvider';
import { sanitizeReturnUrl } from './returnUrl';
import { Shield, Loader2 } from 'lucide-react';

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading, isAuthenticated } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loading || isAuthenticated) return;

    // Preserve the full deep link — path, query and hash — so an expired
    // session returns the operator to the exact desk view they were on.
    // `useSearchParams` is deliberately not used here: this guard lives in a
    // layout and reading it would force the shell into a Suspense boundary.
    // `window.location` is only touched inside the effect (client-only).
    const current =
      typeof window !== 'undefined'
        ? `${pathname || '/'}${window.location.search}${window.location.hash}`
        : pathname || '/';
    const returnUrl = encodeURIComponent(sanitizeReturnUrl(current, '/'));
    router.replace(`/login?returnUrl=${returnUrl}`);
  }, [loading, isAuthenticated, router, pathname]);

  if (loading) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background text-foreground">
        <div className="flex flex-col items-center gap-4 p-8 rounded-xl bg-card/60 border border-border shadow-sm">
          <div className="relative">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center border border-primary/30">
              <Shield className="w-6 h-6 text-primary animate-pulse" />
            </div>
            <Loader2 className="w-12 h-12 text-primary animate-spin absolute -inset-0 opacity-70" />
          </div>
          <div className="text-center">
            <p className="text-sm font-semibold tracking-wider uppercase text-foreground">DROID Terminal</p>
            <p className="text-xs text-muted-foreground mt-1">Verifying credentials &amp; session...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return null;
  }

  return <>{children}</>;
}
