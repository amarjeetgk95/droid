'use client';

import { memo, useSyncExternalStore, useMemo } from 'react';

function subscribe(callback: () => void): () => void {
  const id = setInterval(callback, 1000);
  return () => clearInterval(id);
}

function getSnapshot(): number {
  return Date.now();
}

function getServerSnapshot(): number {
  return Date.now();
}

function ClockInner() {
  const nowMs = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const now = useMemo(() => new Date(nowMs), [nowMs]);
  const timeStr = useMemo(
    () => now.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }),
    [now]
  );
  const dateStr = useMemo(
    () =>
      now.toLocaleDateString('en-IN', {
        timeZone: 'Asia/Kolkata',
        weekday: 'short',
        day: '2-digit',
        month: 'short',
      }),
    [now]
  );

  return (
    <>
      <span className="text-[13px] font-bold tabular-nums tracking-tight text-foreground">{timeStr}</span>
      <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground">IST</span>
      {/* second line handled by caller for layout, but we expose dateStr via data attribute if needed */}
      <span className="hidden" aria-hidden data-date-str={dateStr} />
    </>
  );
}

// Memoized wrapper — re-renders only when time string changes, parent TopHeader no longer thrashes
export const Clock = memo(ClockInner);

// Separate date display that also uses the same external store but isolated
function ClockDateInner() {
  const nowMs = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const now = useMemo(() => new Date(nowMs), [nowMs]);
  const dateStr = useMemo(
    () =>
      now.toLocaleDateString('en-IN', {
        timeZone: 'Asia/Kolkata',
        weekday: 'short',
        day: '2-digit',
        month: 'short',
      }),
    [now]
  );
  const timeStr = useMemo(
    () => now.toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour12: false }),
    [now]
  );
  return (
    <div className="flex flex-col leading-none">
      <div className="flex items-baseline gap-1.5">
        <span className="text-[13px] font-bold tabular-nums tracking-tight text-foreground">{timeStr}</span>
        <span className="hidden sm:inline text-[11px] font-semibold text-muted-foreground">IST</span>
      </div>
      <span className="hidden sm:inline text-[11px] font-medium text-muted-foreground tabular-nums">
        {dateStr} • IST
      </span>
      <span className="sm:hidden text-[10px] font-medium text-muted-foreground">IST • {dateStr}</span>
    </div>
  );
}

export const ClockDate = memo(ClockDateInner);
