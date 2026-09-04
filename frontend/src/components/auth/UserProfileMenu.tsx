'use client';

import { useAuth } from './AuthProvider';
import { useRouter } from 'next/navigation';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { LogOut, Settings, BarChart2, ShieldCheck, ChevronDown } from 'lucide-react';

export function UserProfileMenu() {
  const { user, signOut } = useAuth();
  const router = useRouter();

  const handleSignOut = async () => {
    await signOut();
    router.push('/login');
  };

  const emailDisplay = user?.email || 'Logged In User';
  const initial = emailDisplay.charAt(0).toUpperCase();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className="flex items-center gap-1.5 h-8 px-2 rounded-md hover:bg-secondary border border-border bg-card transition-colors text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring"
          title="User Profile & Session"
          aria-label="User profile and account settings"
        >
          <div className="w-5 h-5 rounded-full bg-primary/10 text-primary border border-primary/25 flex items-center justify-center text-[10px] font-bold shrink-0">
            {initial}
          </div>
          <span className="hidden lg:inline text-xs font-medium max-w-[120px] truncate text-foreground">
            {emailDisplay}
          </span>
          <ChevronDown className="w-3 h-3 text-muted-foreground opacity-60 shrink-0" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56 bg-card border-border shadow-xl">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col space-y-1">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <p className="text-xs font-semibold text-foreground">Authenticated Access</p>
            </div>
            <p className="text-xs text-muted-foreground truncate" title={emailDisplay}>
              {emailDisplay}
            </p>
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator className="bg-border" />

        <DropdownMenuItem
          onClick={() => router.push('/settings')}
          className="cursor-pointer text-xs flex items-center gap-2 py-2"
        >
          <Settings className="w-3.5 h-3.5 text-muted-foreground" />
          <span>Terminal Settings</span>
        </DropdownMenuItem>

        <DropdownMenuItem
          onClick={() => router.push('/paper-trading')}
          className="cursor-pointer text-xs flex items-center gap-2 py-2"
        >
          <BarChart2 className="w-3.5 h-3.5 text-muted-foreground" />
          <span>Paper Trading Portfolio</span>
        </DropdownMenuItem>

        <DropdownMenuSeparator className="bg-border" />

        <DropdownMenuItem
          onClick={handleSignOut}
          variant="destructive"
          className="cursor-pointer text-xs flex items-center gap-2 py-2 text-destructive focus:bg-destructive/10"
        >
          <LogOut className="w-3.5 h-3.5" />
          <span>Log Out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
