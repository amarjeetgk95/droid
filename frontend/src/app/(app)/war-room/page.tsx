'use client';

import { WarRoomDesk } from '@/components/war-room/WarRoomDesk';
import { WarRoomErrorBoundary } from '@/components/war-room/WarRoomErrorBoundary';
import { PaperTradingProvider } from '@/context/PaperTradingContext';

export default function WarRoomPage() {
  return (
    <PaperTradingProvider pollIntervalMs={15000}>
      <WarRoomErrorBoundary>
        <WarRoomDesk />
      </WarRoomErrorBoundary>
    </PaperTradingProvider>
  );
}
