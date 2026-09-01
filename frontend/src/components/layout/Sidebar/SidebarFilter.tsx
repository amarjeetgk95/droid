'use client';

import { useState, useRef, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { Search, X, CornerDownLeft, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ALL_NAV_ITEMS, NavItem } from '../nav-config';

interface SidebarFilterProps {
  collapsed: boolean;
  onNavigate?: () => void;
  onExpand?: () => void;
}

export function SidebarFilter({ collapsed, onNavigate, onExpand }: SidebarFilterProps) {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Global `/` shortcut to focus search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        !['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)
      ) {
        e.preventDefault();
        if (collapsed && onExpand) {
          onExpand();
        }
        setTimeout(() => {
          inputRef.current?.focus();
          setIsOpen(true);
        }, 50);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [collapsed, onExpand]);

  // Click outside to close results dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return ALL_NAV_ITEMS.filter((item) => {
      if (item.label.toLowerCase().includes(q)) return true;
      if (item.description?.toLowerCase().includes(q)) return true;
      if (item.keywords?.some((k) => k.toLowerCase().includes(q))) return true;
      return false;
    });
  }, [query]);

  if (collapsed) {
    return (
      <div className="px-2 py-1 flex justify-center">
        <button
          type="button"
          onClick={() => {
            if (onExpand) onExpand();
            setTimeout(() => inputRef.current?.focus(), 100);
          }}
          title="Search tools (/)"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        >
          <Search className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative px-3 py-1.5">
      <div className="relative flex items-center">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Jump to tool..."
          className={cn(
            'w-full h-8 pl-8 pr-12 rounded-lg bg-secondary/50 border border-border/60 text-xs text-foreground placeholder:text-muted-foreground/70',
            'transition-all duration-150 focus:bg-background focus:border-primary/50 focus:outline-none focus:ring-2 focus:ring-primary/20',
          )}
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {query ? (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setIsOpen(false);
              }}
              className="p-0.5 text-muted-foreground hover:text-foreground rounded"
            >
              <X className="w-3 h-3" />
            </button>
          ) : (
            <kbd className="hidden sm:inline-flex h-4 items-center justify-center px-1 rounded bg-muted border border-border text-[9px] font-mono text-muted-foreground">
              /
            </kbd>
          )}
        </div>
      </div>

      {/* Floating search results overlay */}
      {isOpen && query.trim().length > 0 && (
        <div className="absolute left-3 right-3 top-full mt-1.5 z-50 max-h-60 overflow-y-auto rounded-lg bg-popover border border-border shadow-xl p-1 animate-in fade-in-50 zoom-in-95">
          {results.length > 0 ? (
            <div className="flex flex-col gap-0.5">
              {results.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => {
                      setIsOpen(false);
                      setQuery('');
                      if (onNavigate) onNavigate();
                    }}
                    className={cn(
                      'group flex items-center justify-between gap-2 px-2.5 py-2 rounded-md text-xs transition-colors',
                      'hover:bg-primary/10 hover:text-primary focus:bg-primary/10 focus:text-primary focus:outline-none',
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <Icon className="w-3.5 h-3.5 shrink-0 text-muted-foreground group-hover:text-primary" />
                      <div className="flex flex-col min-w-0">
                        <span className="font-medium truncate text-foreground group-hover:text-primary">
                          {item.label}
                        </span>
                        {item.description && (
                          <span className="text-[10px] text-muted-foreground truncate">
                            {item.description}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {item.shortcut && (
                        <kbd className="text-[9px] font-mono px-1 py-0.5 rounded bg-muted border text-muted-foreground">
                          {item.shortcut}
                        </kbd>
                      )}
                      <ArrowRight className="w-3 h-3 opacity-0 group-hover:opacity-100 text-primary transition-opacity" />
                    </div>
                  </Link>
                );
              })}
            </div>
          ) : (
            <div className="p-3 text-center text-xs text-muted-foreground">
              No matching tools found for "{query}"
            </div>
          )}
        </div>
      )}
    </div>
  );
}
