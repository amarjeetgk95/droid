'use client';

import { WarRoomDesk } from '@/components/war-room/WarRoomDesk';
import { WarRoomErrorBoundary } from '@/components/war-room/WarRoomErrorBoundary';

export default function WarRoomPage() {
  return (
    <WarRoomErrorBoundary>
      <WarRoomDesk />
    </WarRoomErrorBoundary>
  );
}
