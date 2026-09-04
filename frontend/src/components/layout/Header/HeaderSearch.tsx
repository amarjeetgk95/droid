'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';
import { cn } from '@/lib/utils';

interface HeaderSearchProps {
  onOpen: () => void;
  className?: string;
}

function getPlatformShortcut(): string {
  if (typeof window === 'undefined') return 'Ctrl+K';
  const isMac = /(Mac|iPhone|iPod|iPad)/i.test(navigator.userAgent);
  return isMac ? '⌘K' : 'Ctrl+K';
}

export function HeaderSearch({ onOpen, className }: HeaderSearchProps) {
  const [shortcutLabel] = useState<string>(getPlatformShortcut);

  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'group flex items-center gap-2 h-8 px-2.5 rounded-lg border border-border/80 bg-secondary/50 hover:bg-secondary hover:border-border text-muted-foreground hover:text-foreground transition-all text-left cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring select-none shadow-2xs',
        'w-36 sm:w-48 md:w-56 lg:w-64',
        className,
      )}
      title={`Quick Search & Command Palette (${shortcutLabel})`}
      aria-label="Open command palette search"
      aria-haspopup="dialog"
    >
      <Search className="w-3.5 h-3.5 shrink-0 text-muted-foreground group-hover:text-primary transition-colors" />
      <span className="hidden sm:inline flex-1 truncate text-xs text-muted-foreground group-hover:text-foreground">
        Search instruments, pages…
      </span>
      <span className="sm:hidden flex-1 truncate text-xs text-muted-foreground group-hover:text-foreground">
        Search…
      </span>
      <kbd className="hidden sm:inline-flex items-center text-[10px] font-mono font-medium px-1.5 py-0.5 rounded border border-border/70 bg-card text-muted-foreground group-hover:text-foreground group-hover:border-border transition-colors shadow-2xs">
        {shortcutLabel}
      </kbd>
    </button>
  );
}
