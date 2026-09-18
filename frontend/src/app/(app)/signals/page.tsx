'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { SignalsDesk } from '@/components/signals/SignalsDesk';

function SignalsDeskWithParams() {
  const searchParams = useSearchParams();
  const rawTab = searchParams.get('tab');
  const initialTab =
    rawTab === 'scanner' || rawTab === 'forge'
      ? 'scanner'
      : rawTab === 'engines' || rawTab === 'performance' || rawTab === 'history'
        ? rawTab
        : undefined;

  return <SignalsDesk initialTab={initialTab} />;
}

export default function SignalsPage() {
  return (
    <Suspense fallback={null}>
      <SignalsDeskWithParams />
    </Suspense>
  );
}
