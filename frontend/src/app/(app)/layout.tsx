'use client';

import type { ReactNode } from 'react';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { AppShell } from '@/components/shell/AppShell';

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
