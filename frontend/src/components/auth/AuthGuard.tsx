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
        <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-card border border-border shadow-card">
          <Loader2 className="w-4 h-4 text-ink-2 animate-spin" />
          <span className="text-xs font-medium text-ink-2 tracking-wide">
            Verifying credentials...
          </span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return null;
  }

  return <>{children}</>;
}
