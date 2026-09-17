'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { getAuthErrorMessage } from './authMessages';
import { LogOut, Settings, ShieldCheck, ChevronDown, AlertCircle } from 'lucide-react';

/**
 * Shell-compatible account menu (no props). The sign-out action is
 * destructive, so it is confirmed; the pending state and any failure are
 * rendered here. Never touches the Supabase client directly, so it renders
 * and stays interactive even when the env is missing (demo mode).
 */
export function UserProfileMenu() {
  const { user, signOut, isConfigured } = useAuth();
  const router = useRouter();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const emailDisplay = user?.email || (isConfigured ? 'Signed-in operator' : 'Authentication not configured');
  const roleDisplay = user?.role ? user.role.toUpperCase() : null;
  const initial = emailDisplay.charAt(0).toUpperCase();

  const handleSignOut = async () => {
    setSigningOut(true);
    setError(null);
    try {
      await signOut();
      setConfirmOpen(false);
      router.replace('/login');
    } catch (err) {
      // signOut() always clears the local session; the throw only reports that
      // the remote revoke failed. Surface it instead of navigating silently.
      setConfirmOpen(false);
      setError(
        getAuthErrorMessage(
          err,
          'Sign-out could not be completed. Check your connection and try again.',
        ),
      );
    } finally {
      setSigningOut(false);
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="flex items-center gap-1.5 h-8 px-2 rounded-md hover:bg-secondary border border-border bg-card transition-colors text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title={`User Profile & Session: ${emailDisplay}`}
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
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <ShieldCheck className="w-3.5 h-3.5 text-up shrink-0" />
                  <p className="text-xs font-semibold text-foreground truncate">
                    {isConfigured ? 'Authenticated Access' : 'Demo Mode — No Auth'}
                  </p>
                </div>
                {roleDisplay ? (
                  <span className="text-[10px] font-semibold text-muted-foreground shrink-0">
                    {roleDisplay}
                  </span>
                ) : null}
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

          <DropdownMenuSeparator className="bg-border" />

          <DropdownMenuItem
            onClick={() => setConfirmOpen(true)}
            variant="destructive"
            className="cursor-pointer text-xs flex items-center gap-2 py-2 text-destructive focus:bg-destructive/10"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Log Out</span>
          </DropdownMenuItem>

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="mt-1 flex items-start gap-1.5 rounded-[2px] border border-down-line bg-down-wash px-2 py-1.5 text-[11px] text-down"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-px" />
              <span className="leading-snug">{error}</span>
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Sign out of DROID Terminal?"
        description="This ends your session on this device and clears cached market data. You will need to sign in again."
        confirmLabel="Sign out"
        cancelLabel="Stay signed in"
        tone="danger"
        busy={signingOut}
        onConfirm={handleSignOut}
      />
    </>
  );
}

export default UserProfileMenu;
