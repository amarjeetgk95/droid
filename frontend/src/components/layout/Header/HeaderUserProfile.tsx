'use client';

import { memo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { BarChart2, ChevronDown, LogOut, Settings } from 'lucide-react';

export function HeaderUserProfile() {
  const { user, signOut } = useAuth();
  const router = useRouter();

  const handleSignOut = async () => {
    try {
      await signOut();
      router.push('/login');
    } catch {
      router.push('/login');
    }
  };

  const emailDisplay = user?.email || 'Active Trader';
  const initial = emailDisplay.charAt(0).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex items-center gap-1.5 h-8 px-2 rounded-lg hover:bg-secondary border border-border/80 bg-card transition-all text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring select-none shadow-2xs"
          title="User Account & Terminal Session"
          aria-label="User account and profile menu"
        >
          {/* Avatar initial with active green indicator */}
          <div className="relative flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-primary border border-primary/20 text-[10px] font-bold shrink-0">
            <span>{initial}</span>
            <span className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-emerald-500 ring-1 ring-card" />
          </div>

          <span className="hidden xl:inline text-xs font-medium max-w-[110px] truncate text-foreground">
            {emailDisplay}
          </span>

          <span className="hidden sm:inline text-[9px] font-bold uppercase tracking-wider px-1 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
            PRO
          </span>

          <ChevronDown className="w-3 h-3 text-muted-foreground/60 shrink-0 ml-0.5" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-60 bg-card border-border shadow-xl p-2">
        <DropdownMenuLabel className="font-normal px-2 py-1.5">
          <div className="flex flex-col space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-foreground">Account & Session</span>
              <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                ACTIVE
              </span>
            </div>
            <p className="text-xs text-muted-foreground truncate" title={emailDisplay}>
              {emailDisplay}
            </p>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        <DropdownMenuItem
          onClick={() => router.push('/settings')}
          className="cursor-pointer text-xs flex items-center gap-2 py-2 rounded-md hover:bg-secondary"
        >
          <Settings className="w-3.5 h-3.5 text-muted-foreground" />
          <span>Terminal & Broker Settings</span>
        </DropdownMenuItem>

        <DropdownMenuItem
          onClick={() => router.push('/paper-trading')}
          className="cursor-pointer text-xs flex items-center gap-2 py-2 rounded-md hover:bg-secondary"
        >
          <BarChart2 className="w-3.5 h-3.5 text-muted-foreground" />
          <span>Paper Trading Portfolio</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator className="bg-border my-1.5" />

        <DropdownMenuItem
          onClick={handleSignOut}
          variant="destructive"
          className="cursor-pointer text-xs flex items-center gap-2 py-2 rounded-md text-destructive focus:bg-destructive/10"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span>Log Out of Terminal</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const MemoizedHeaderUserProfile = memo(HeaderUserProfile);
