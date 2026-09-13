'use client';

import { Suspense } from 'react';
import { SwingDesk } from '@/components/swing/SwingDesk';

export default function SwingPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-xs text-muted-foreground">Loading Swing Trading Desk...</div>}>
      <SwingDesk />
    </Suspense>
  );
}
