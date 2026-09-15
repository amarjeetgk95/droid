'use client';

import { Suspense } from 'react';
import { WarRoomDesk } from '@/components/war-room/WarRoomDesk';

export default function WarRoomPage() {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center font-mono text-sm text-[var(--ds-text-muted)]">Loading War Room Desk…</div>}>
      <WarRoomDesk />
    </Suspense>
  );
}
