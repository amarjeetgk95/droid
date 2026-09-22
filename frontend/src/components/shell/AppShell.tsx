'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import {
  ArrowLeftRight,
  Bot,
  ChartCandlestick,
  CircleUser,
  FlaskConical,
  Landmark,
  LayoutDashboard,
  LogOut,
  Menu,
  Radio,
  Settings as SettingsIcon,
  TrendingUp,
  Wrench,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSignalEvents } from '@/context/AppStreamContext';
import { useMarketSession } from '@/context/MarketSessionContext';
import { MODULE_NAV, isActivePath } from './nav';
import { InstrumentPicker } from './InstrumentPicker';
import { BrokerAuthControl } from './BrokerAuthControl';
import { AudioControl } from './AudioControl';
import { scalpAudio } from '@/lib/scalpAudio';
import { SESSION_PHASE_LABELS } from './status';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/': LayoutDashboard,
  '/signals': Radio,
  '/swing': TrendingUp,
  '/options': ChartCandlestick,
  '/trade': ArrowLeftRight,
  '/intel': Landmark,
  '/lab': FlaskConical,
  '/copilot': Bot,
  '/ops': Wrench,
  '/settings': SettingsIcon,
};

const SYSTEM_HREFS = new Set(['/ops', '/settings']);
const MAIN_NAV = MODULE_NAV.filter((item) => !SYSTEM_HREFS.has(item.href));
const SYSTEM_NAV = MODULE_NAV.filter((item) => SYSTEM_HREFS.has(item.href));

function NavList({ items, label }: { items: typeof MODULE_NAV; label: string }) {
  const pathname = usePathname();

  return (
    <nav className="rail-nav" aria-label={label}>
      {items.map((item) => {
        const active = isActivePath(pathname, item.href);
        const Icon = NAV_ICONS[item.href];
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.description}
            aria-current={active ? 'page' : undefined}
            className="rail-nav__item"
          >
            {Icon ? <Icon size={14} /> : null}
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function shortNextLabel(next: string): string {
  return next
    .replace(/\s*IST\s*$/, '')
    .replace('Monday', 'Mon')
    .replace('Tuesday', 'Tue')
    .replace('Wednesday', 'Wed')
    .replace('Thursday', 'Thu')
    .replace('Friday', 'Fri')
    .replace('Opens next trading day', 'Next')
    .replace('Market Open in', 'Opens in');
}

function shortClockLabel(sessionTimeIST: string): string {
  const t = sessionTimeIST.replace(/\s*IST$/, '');
  if (t.startsWith('--')) return '--:--';
  return t.slice(0, 5);
}

/**
 * Market-hours status for the top rail.
 *
 * Session chip + IST clock + next change only. Feed health used to sit here
 * as a second green pill next to the broker pill and ate the room the index
 * deck needs — it now lives in tooltips / the ops module instead.
 */
function RailStatus() {
  const { phase, isOpen, sessionTimeIST, nextSessionChange } = useMarketSession();

  const sessionTone = isOpen ? 'on' : phase === 'PRE_OPEN' || phase === 'POST_CLOSE' ? 'warn' : 'idle';
  const clockShort = shortClockLabel(sessionTimeIST);
  const nextShort = shortNextLabel(nextSessionChange);

  return (
    <div className="rail-meta" aria-label="Market session status">
      <span
        className={`rail-chip rail-chip--${sessionTone}`}
        title={`Session ${SESSION_PHASE_LABELS[phase]} · ${nextSessionChange}`}
      >
        <i aria-hidden="true" />
        <span className="rail-chip__label">{SESSION_PHASE_LABELS[phase]}</span>
      </span>
      <span className="rail-meta__clock" title={sessionTimeIST}>
        {clockShort}
        <span className="rail-meta__suffix"> IST</span>
      </span>
      <span className="rail-meta__next" title={nextSessionChange}>
        → {nextShort}
      </span>
    </div>
  );
}

function SideContent() {
  return (
    <div className="rail-group">
      <div className="rail-group__label">Navigation</div>
      <NavList items={MAIN_NAV} label="Modules" />
      <div className="rail-group__label rail-group__label--div">System</div>
      <NavList items={SYSTEM_NAV} label="System" />
    </div>
  );
}

function NavDrawer({
  open,
  onClose,
  closeButtonRef,
}: {
  open: boolean;
  onClose: () => void;
  closeButtonRef: RefObject<HTMLButtonElement | null>;
}) {
  if (!open) return null;

  return (
    <div className="rail-ovl" id="app-nav-drawer" role="presentation" onClick={onClose}>
      <div
        className="rail-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="rail-drawer__hd">
          <span className="micro-label">DROID F&amp;O Terminal</span>
          <button
            ref={closeButtonRef}
            type="button"
            className="btn icon-btn"
            aria-label="Close navigation"
            onClick={onClose}
          >
            <X size={15} />
          </button>
        </div>
        <SideContent />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!navOpen) return;
    const menuButton = menuButtonRef.current;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
      menuButton?.focus();
    };
  }, [navOpen]);

  useSignalEvents((payload) => {
    const eventName = (payload?.event || '').toUpperCase();
    const dataObj = typeof payload?.data === 'object' && payload?.data !== null ? (payload.data as Record<string, unknown>) : null;
    const toState = dataObj && typeof dataObj.to_state === 'string' ? dataObj.to_state.toUpperCase() : '';

    if (eventName.includes('TARGET') || toState.includes('TARGET')) {
      scalpAudio.target();
    } else if (eventName.includes('STOP') || toState.includes('STOP')) {
      scalpAudio.stop();
    } else if (eventName.includes('CONFIRM') || toState.includes('CONFIRM')) {
      scalpAudio.confirmed();
    } else if (eventName.includes('KILL') || toState.includes('KILL')) {
      scalpAudio.kill();
    }
  });

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="app-rail" role="banner">
        <div className="app-rail__inner">
          <div className="rail-left">
            <button
              ref={menuButtonRef}
              type="button"
              className="btn icon-btn rail-menu"
              aria-label="Open navigation"
              aria-expanded={navOpen}
              aria-controls="app-nav-drawer"
              onClick={() => setNavOpen(true)}
            >
              <Menu size={16} />
            </button>

            <Link href="/" className="rail-brand" aria-label="DROID F&O Terminal — dashboard">
              <span className="rail-brand__mark" aria-hidden="true">
                D
              </span>
              <span className="rail-brand__text">
                <span className="rail-brand__name">DROID</span>
                <span className="rail-brand__sub">F&amp;O Terminal</span>
              </span>
            </Link>
          </div>

          <div className="rail-deck">
            <InstrumentPicker />
          </div>

          <div className="rail-right">
            <RailStatus />
            <div className="rail-actions">
              <BrokerAuthControl />
              <AudioControl />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="btn icon-btn rail-account"
                    aria-label="Account menu"
                    title={user?.email ?? 'Account'}
                  >
                    <CircleUser size={15} />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-60">
                  <DropdownMenuLabel className="truncate text-xs text-ink-2">
                    {user?.email ?? 'Local operator'}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onSelect={() => void signOut()}>
                    <LogOut size={13} />
                    Sign out
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </div>
      </header>

      <div className="app-body">
        <aside className="rail-side" aria-label="Desk navigation">
          <SideContent />
        </aside>
        <main className="app-main">{children}</main>
      </div>

      <NavDrawer open={navOpen} onClose={() => setNavOpen(false)} closeButtonRef={closeButtonRef} />
    </div>
  );
}
