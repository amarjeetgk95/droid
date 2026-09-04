'use client';

import { memo, useSyncExternalStore } from 'react';

// Stable module-level external store for wall-clock time.
// getSnapshot MUST return a stable value until an external update occurs;
// calling Date.now() directly inside getSnapshot creates an infinite re-render
// loop (React error #185) because every snapshot check returns a different timestamp.
let currentTime = typeof window !== 'undefined' ? Date.now() : 0;
const listeners = new Set<() => void>();
let timerId: ReturnType<typeof setInterval> | null = null;

function subscribe(callback: () => void): () => void {
  listeners.add(callback);
  if (!timerId && typeof window !== 'undefined') {
    timerId = setInterval(() => {
      currentTime = Date.now();
      listeners.forEach((listener) => listener());
    }, 1000);
  }
  return () => {
    listeners.delete(callback);
    if (listeners.size === 0 && timerId) {
      clearInterval(timerId);
      timerId = null;
    }
  };
}

function getSnapshot(): number {
  return currentTime;
}

function getServerSnapshot(): number {
  return 0;
}

function formatISTTime(ms: number): string {
  if (!ms) return '--:--:--';
  return new Date(ms).toLocaleTimeString('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour12: false,
  });
}

function formatISTDate(ms: number): string {
  if (!ms) return '---, -- ---';
  return new Date(ms).toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    weekday: 'short',
    day: '2-digit',
    month: 'short',
  });
}

function ClockInner() {
  const nowMs = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const timeStr = formatISTTime(nowMs);
  const dateStr = formatISTDate(nowMs);

  return (
    <>
      <span className="text-[13px] font-bold tabular-nums tracking-tight text-foreground" suppressHydrationWarning>
        {timeStr}
      </span>
      <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground">IST</span>
      <span className="hidden" aria-hidden data-date-str={dateStr} />
    </>
  );
}

// Memoized wrapper — re-renders only when time string changes, parent TopHeader no longer thrashes
export const Clock = memo(ClockInner);

// Separate date display that also uses the same external store but isolated
function ClockDateInner() {
  const nowMs = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const timeStr = formatISTTime(nowMs);
  const dateStr = formatISTDate(nowMs);

  return (
    <div className="flex flex-col leading-none">
      <div className="flex items-baseline gap-1.5">
        <span className="text-[13px] font-bold tabular-nums tracking-tight text-foreground" suppressHydrationWarning>
          {timeStr}
        </span>
        <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground">IST</span>
      </div>
      <span className="hidden sm:inline text-[11px] font-medium text-muted-foreground tabular-nums" suppressHydrationWarning>
        {dateStr} • IST
      </span>
      <span className="sm:hidden text-[10px] font-medium text-muted-foreground" suppressHydrationWarning>
        IST • {dateStr}
      </span>
    </div>
  );
}

export const ClockDate = memo(ClockDateInner);
