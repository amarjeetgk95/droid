'use client';

import { memo, useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import {
  Activity,
  ArrowRight,
  Bell,
  Radio,
  Sparkles,
  Volume2,
  VolumeX,
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { api } from '@/lib/api';
import { cn, safeNum } from '@/lib/utils';

const AUDIO_ALERTS_KEY = 'droid:audio:alerts';

interface RawTrade {
  signal_id?: string;
  id?: string;
  underlying?: string;
  symbol?: string;
  direction?: string;
  action?: string;
  strategy?: string;
  strategy_name?: string;
  entry_price?: number;
  price?: number;
  spot_price?: number;
  created_at?: string;
  timestamp?: string;
  timestamp_ms?: number;
}

interface RecentSignalItem {
  id: string;
  underlying: string;
  direction: 'LONG' | 'SHORT' | 'BUY' | 'SELL';
  strategy: string;
  price?: number;
  timeAgo: string;
}

function getStoredSound(): boolean {
  if (typeof window === 'undefined') return true;
  try {
    const stored = localStorage.getItem(AUDIO_ALERTS_KEY);
    return stored !== null ? stored === '1' : true;
  } catch {
    return true;
  }
}

export function HeaderNotifications() {
  const [signalCount, setSignalCount] = useState<number>(0);
  const [recentSignals, setRecentSignals] = useState<RecentSignalItem[]>([]);
  const [soundEnabled, setSoundEnabled] = useState<boolean>(getStoredSound);
  const [isOpen, setIsOpen] = useState<boolean>(false);

  const toggleSound = useCallback(() => {
    setSoundEnabled((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(AUDIO_ALERTS_KEY, next ? '1' : '0');
      } catch {}
      return next;
    });
  }, []);

  // Fetch signal count periodically
  useEffect(() => {
    let mounted = true;
    const fetchStatus = async () => {
      try {
        const res = await api.getSignalsStatus();
        if (mounted) {
          setSignalCount(res.active_count ?? 0);
        }
      } catch {
        if (mounted) setSignalCount(0);
      }
    };

    void fetchStatus();
    const intervalId = setInterval(fetchStatus, 30000); // 30s poll
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  // Fetch recent signal audit items
  const fetchRecentSignals = useCallback(async () => {
    try {
      const res = await api.getSignalsAudit({ limit: 4 });
      if (res && Array.isArray(res.trades)) {
        const mapped: RecentSignalItem[] = res.trades.slice(0, 4).map((t: RawTrade, idx: number) => {
          const timestamp = t.created_at || t.timestamp || t.timestamp_ms || Date.now();
          const diffSec = Math.max(1, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000));
          const timeAgo =
            diffSec < 60
              ? 'Just now'
              : diffSec < 3600
              ? `${Math.floor(diffSec / 60)}m ago`
              : `${Math.floor(diffSec / 3600)}h ago`;

          const dir = (t.direction || t.action || 'LONG').toUpperCase();
          const validDir: 'LONG' | 'SHORT' | 'BUY' | 'SELL' =
            dir === 'SHORT' || dir === 'SELL' ? dir : 'LONG';

          return {
            id: t.signal_id || t.id || `sig-${idx}`,
            underlying: (t.underlying || t.symbol || 'NIFTY').toUpperCase(),
            direction: validDir,
            strategy: t.strategy || t.strategy_name || 'Alpha Momentum',
            price: Number(t.entry_price || t.price || t.spot_price) || undefined,
            timeAgo,
          };
        });
        setRecentSignals(mapped);
      }
    } catch {
      setRecentSignals([]);
    }
  }, []);

  const handleOpenChange = useCallback(
    (open: boolean) => {
      setIsOpen(open);
      if (open) {
        void fetchRecentSignals();
      }
    },
    [fetchRecentSignals],
  );

  return (
    <DropdownMenu open={isOpen} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="relative inline-flex items-center justify-center h-8 w-8 rounded-lg border border-border/80 bg-card hover:bg-secondary text-muted-foreground hover:text-foreground transition-all cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring shadow-2xs"
          title={signalCount > 0 ? `${signalCount} active signals detected` : 'Active signals & notifications'}
          aria-label="Signals and notifications"
        >
          <Bell className="w-4 h-4" />
          {signalCount > 0 && (
            <span className="absolute -top-1 -right-1 min-w-[17px] h-[17px] px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-bold leading-[17px] text-center tabular-nums ring-2 ring-card shadow-2xs animate-in zoom-in-75 duration-150">
              {signalCount > 99 ? '99+' : signalCount}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-80 bg-card border-border shadow-xl p-2.5">
        {/* Header with Title & Audio Sound Toggle */}
        <DropdownMenuLabel className="font-normal px-1 py-1">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className={cn('w-2 h-2 rounded-full', signalCount > 0 ? 'bg-emerald-500 animate-live' : 'bg-slate-400')} />
              <span className="text-xs font-bold text-foreground">Signals & Market Alerts</span>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleSound();
                }}
                className={cn(
                  'p-1 rounded-md text-[11px] transition-colors cursor-pointer border',
                  soundEnabled
                    ? 'bg-secondary text-foreground border-border hover:bg-secondary/80'
                    : 'bg-muted/50 text-muted-foreground border-transparent hover:text-foreground',
                )}
                title={soundEnabled ? 'Audio alerts enabled' : 'Audio alerts muted'}
                aria-label="Toggle notification chime"
              >
                {soundEnabled ? <Volume2 className="w-3.5 h-3.5 text-primary" /> : <VolumeX className="w-3.5 h-3.5" />}
              </button>

              <span
                className={cn(
                  'text-[10px] font-mono px-1.5 py-0.5 rounded font-semibold border',
                  signalCount > 0
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                    : 'bg-secondary text-muted-foreground border-border',
                )}
              >
                {signalCount > 0 ? `${signalCount} ACTIVE` : 'STANDBY'}
              </span>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">
            Real-time alpha triggers, options flow & regime alerts.
          </p>
        </DropdownMenuLabel>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Live Recent Signals List (if any) */}
        {recentSignals.length > 0 ? (
          <div className="space-y-1 my-1">
            <div className="px-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Recent Triggers</div>
            {recentSignals.map((sig) => {
              const isLong = sig.direction === 'LONG' || sig.direction === 'BUY';
              return (
                <Link
                  key={sig.id}
                  href="/signals"
                  className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 hover:bg-secondary border border-border/40 transition-colors text-xs"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-foreground">{sig.underlying}</span>
                      <span
                        className={cn(
                          'text-[9px] font-bold px-1.5 py-0.2 rounded border',
                          isLong
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-rose-50 text-rose-700 border-rose-200',
                        )}
                      >
                        {sig.direction}
                      </span>
                      {sig.price && (
                        <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                          @{safeNum(sig.price)}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-muted-foreground truncate mt-0.5">{sig.strategy}</p>
                  </div>
                  <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums ml-2">{sig.timeAgo}</span>
                </Link>
              );
            })}
          </div>
        ) : (
          /* Empty / Idle State: Quick Launchers */
          <div className="space-y-0.5">
            <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
              <Link href="/signals">
                <div className="p-1.5 rounded-md bg-emerald-50 text-emerald-600 border border-emerald-200 shrink-0 mt-0.5">
                  <Radio className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">Active Alpha Signals</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    Momentum, breakout & mean-reversion scanner
                  </p>
                </div>
              </Link>
            </DropdownMenuItem>

            <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
              <Link href="/options">
                <div className="p-1.5 rounded-md bg-blue-50 text-blue-600 border border-blue-200 shrink-0 mt-0.5">
                  <Activity className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">Options Greeks & Flow</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    PCR shifts, Max Pain migration & institutional OI
                  </p>
                </div>
              </Link>
            </DropdownMenuItem>

            <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-start gap-2.5 hover:bg-secondary">
              <Link href="/ai-analysis">
                <div className="p-1.5 rounded-md bg-purple-50 text-purple-600 border border-purple-200 shrink-0 mt-0.5">
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-foreground">AI Intelligence Briefing</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    Probabilistic model synthesis & multi-TF bias
                  </p>
                </div>
              </Link>
            </DropdownMenuItem>
          </div>
        )}

        <DropdownMenuSeparator className="bg-border my-1.5" />

        {/* Footer Link */}
        <DropdownMenuItem asChild className="cursor-pointer p-2 rounded-lg flex items-center justify-between text-xs font-semibold text-primary hover:bg-primary/10">
          <Link href="/signals">
            <span>Open Signal Centre</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const MemoizedHeaderNotifications = memo(HeaderNotifications);
