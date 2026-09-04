'use client';

import { memo, useMemo, useState, useEffect } from 'react';
import { Clock } from '../Clock';
import { MarketStatusResponse } from '@/lib/types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Calendar, ChevronDown, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderMarketSessionProps {
  marketStatus: MarketStatusResponse | null;
}

/**
 * Calculates countdown and market phase according to Indian Standard Time (IST)
 */
function getMarketCountdown(now: Date, isTradingDay: boolean) {
  // Convert current time to IST components
  const istFormatter = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: 'numeric',
    hour12: false,
    weekday: 'short',
  });

  const parts = istFormatter.formatToParts(now);
  let hour = 0;
  let minute = 0;
  let weekday = '';

  for (const part of parts) {
    if (part.type === 'hour') hour = parseInt(part.value, 10);
    if (part.type === 'minute') minute = parseInt(part.value, 10);
    if (part.type === 'weekday') weekday = part.value;
  }

  const isWeekend = weekday === 'Sat' || weekday === 'Sun';
  const totalMinutes = hour * 60 + minute;

  // Timings in minutes from 00:00 IST
  const PRE_OPEN = 9 * 60; // 09:00
  const MARKET_OPEN = 9 * 60 + 15; // 09:15
  const MARKET_CLOSE = 15 * 60 + 30; // 15:30
  const POST_CLOSE_END = 16 * 60; // 16:00

  if (!isTradingDay || isWeekend) {
    return {
      phase: 'CLOSED',
      label: 'Closed',
      detail: isWeekend ? 'Weekend' : 'Exchange Holiday',
      badgeTone: 'closed' as const,
      countdown: 'Opens Mon 09:15',
    };
  }

  if (totalMinutes < PRE_OPEN) {
    const diffMin = PRE_OPEN - totalMinutes;
    const hrs = Math.floor(diffMin / 60);
    const mins = diffMin % 60;
    return {
      phase: 'PRE_MARKET',
      label: 'Pre-Market',
      detail: 'Opens at 09:00',
      badgeTone: 'amber' as const,
      countdown: hrs > 0 ? `Opens in ${hrs}h ${mins}m` : `Opens in ${mins}m`,
    };
  }

  if (totalMinutes >= PRE_OPEN && totalMinutes < MARKET_OPEN) {
    const diffMin = MARKET_OPEN - totalMinutes;
    return {
      phase: 'PRE_OPEN',
      label: 'Pre-Open Call',
      detail: 'Order collection & discovery',
      badgeTone: 'amber' as const,
      countdown: `Open in ${diffMin}m`,
    };
  }

  if (totalMinutes >= MARKET_OPEN && totalMinutes < MARKET_CLOSE) {
    const diffMin = MARKET_CLOSE - totalMinutes;
    const hrs = Math.floor(diffMin / 60);
    const mins = diffMin % 60;
    return {
      phase: 'OPEN',
      label: 'NSE • OPEN',
      detail: 'Regular Trading Hours',
      badgeTone: 'live' as const,
      countdown: hrs > 0 ? `Closes in ${hrs}h ${mins}m` : `Closes in ${mins}m`,
    };
  }

  if (totalMinutes >= MARKET_CLOSE && totalMinutes < POST_CLOSE_END) {
    return {
      phase: 'POST_CLOSE',
      label: 'Post-Close',
      detail: 'Closing price settlement',
      badgeTone: 'amber' as const,
      countdown: 'Closes 16:00',
    };
  }

  // Evening / After market
  const minutesUntilNextDay = 24 * 60 - totalMinutes + MARKET_OPEN;
  const nextHrs = Math.floor(minutesUntilNextDay / 60);
  const nextMins = minutesUntilNextDay % 60;

  return {
    phase: 'CLOSED',
    label: 'Market Closed',
    detail: 'Orders queued for AMO',
    badgeTone: 'closed' as const,
    countdown: `Opens in ${nextHrs}h ${nextMins}m`,
  };
}

function HeaderMarketSessionInner({ marketStatus }: HeaderMarketSessionProps) {
  const [now, setNow] = useState<Date>(() => new Date());

  // Update countdown minute ticker
  useEffect(() => {
    const timer = setInterval(() => {
      setNow(new Date());
    }, 15000); // 15-second refresh for countdown precision
    return () => clearInterval(timer);
  }, []);

  const isTradingDay = marketStatus?.is_trading_day !== false;
  const countdownInfo = useMemo(() => getMarketCountdown(now, isTradingDay), [now, isTradingDay]);

  // World clocks
  const utcTime = now.toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false });
  const estTime = now.toLocaleTimeString('en-US', { timeZone: 'America/New_York', hour12: false });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="hidden md:flex items-center gap-2 h-8 px-2.5 rounded-lg border border-border/70 bg-card hover:bg-secondary/70 transition-all text-xs cursor-pointer select-none outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs"
          title="Market session schedule & world clocks"
          aria-label={`Market state: ${countdownInfo.label}, ${countdownInfo.countdown}`}
        >
          {/* Live Clock */}
          <div className="flex items-center gap-1.5 font-mono">
            <Clock />
          </div>

          <span className="text-border/80 text-[10px]">•</span>

          {/* Session Pill */}
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                'w-1.5 h-1.5 rounded-full shrink-0',
                countdownInfo.badgeTone === 'live' && 'bg-emerald-500 animate-live',
                countdownInfo.badgeTone === 'amber' && 'bg-amber-500',
                countdownInfo.badgeTone === 'closed' && 'bg-slate-400',
              )}
            />
            <span
              className={cn(
                'font-semibold text-xs',
                countdownInfo.badgeTone === 'live' && 'text-emerald-700',
                countdownInfo.badgeTone === 'amber' && 'text-amber-700',
                countdownInfo.badgeTone === 'closed' && 'text-muted-foreground',
              )}
            >
              {countdownInfo.label}
            </span>

            <span className="hidden lg:inline text-[11px] text-muted-foreground font-normal tabular-nums">
              ({countdownInfo.countdown})
            </span>
          </div>

          <ChevronDown className="w-3 h-3 text-muted-foreground/60 shrink-0 ml-0.5" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="center" className="w-80 bg-card border-border shadow-xl p-2.5">
        <DropdownMenuLabel className="font-normal px-2 py-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-primary" />
              Indian Market Session
            </span>
            <span
              className={cn(
                'text-[10px] font-bold px-1.5 py-0.2 rounded border',
                countdownInfo.badgeTone === 'live' && 'bg-emerald-50 text-emerald-700 border-emerald-200',
                countdownInfo.badgeTone === 'amber' && 'bg-amber-50 text-amber-800 border-amber-200',
                countdownInfo.badgeTone === 'closed' && 'bg-secondary text-muted-foreground border-border',
              )}
            >
              {countdownInfo.label}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            {countdownInfo.detail} • <span className="font-medium text-foreground">{countdownInfo.countdown}</span>
          </p>
        </DropdownMenuLabel>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Schedule Grid */}
        <div className="px-2 py-1 space-y-2 text-[11px]">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Exchange Timetable (IST)</div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Pre-Open Session</span>
              <span className="font-mono font-medium text-foreground">09:00 – 09:15</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-foreground font-semibold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                Regular Trading
              </span>
              <span className="font-mono font-bold text-foreground">09:15 – 15:30</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Post-Close Settlement</span>
              <span className="font-mono font-medium text-foreground">15:40 – 16:00</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">MCX Commodities</span>
              <span className="font-mono font-medium text-foreground">09:00 – 23:30</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Crypto Derivatives</span>
              <span className="font-mono font-medium text-emerald-600">24 / 7 Live</span>
            </div>
          </div>
        </div>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Multi-Timezone Reference */}
        <div className="px-2 py-1 space-y-1.5 text-[11px]">
          <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
            <Globe className="w-3 h-3 text-muted-foreground" />
            Global Clocks
          </div>
          <div className="grid grid-cols-2 gap-2 pt-0.5">
            <div className="p-1.5 rounded-md bg-secondary/50 border border-border/50">
              <div className="text-[10px] text-muted-foreground">UTC (Crypto / Macro)</div>
              <div className="font-mono font-bold text-foreground text-xs">{utcTime}</div>
            </div>
            <div className="p-1.5 rounded-md bg-secondary/50 border border-border/50">
              <div className="text-[10px] text-muted-foreground">New York (EST/EDT)</div>
              <div className="font-mono font-bold text-foreground text-xs">{estTime}</div>
            </div>
          </div>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const HeaderMarketSession = memo(HeaderMarketSessionInner);
