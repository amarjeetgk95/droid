'use client';

import React, { useEffect, useRef } from 'react';
import { Search, X } from 'lucide-react';
import {
  getTabDef,
  searchTabs,
  type SettingsTabDef,
  type SettingsTabId,
} from './registry';

interface Props {
  activeTab: SettingsTabId;
  onTabChange: (id: SettingsTabId) => void;
  query: string;
  onQueryChange: (q: string) => void;
  dirtySections?: Record<string, boolean>;
  errorCounts?: Record<string, number>;
}

/**
 * Left rail: searchable settings navigation.
 *
 * Replaces the old single-row segmented control, which overflowed on mobile
 * and gave no way to find a setting by name.
 */
export function SettingsSidebar({
  activeTab,
  onTabChange,
  query,
  onQueryChange,
  dirtySections = {},
  errorCounts = {},
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const results = searchTabs(query);
  const isFiltering = query.trim().length > 0;

  // "/" focuses search, Escape clears it — matches the desk's shortcut feel.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable);
      if (e.key === '/' && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && typing) {
        onQueryChange('');
        inputRef.current?.blur();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onQueryChange]);

  const renderItem = (tab: SettingsTabDef) => {
    const Icon = tab.icon;
    const isActive = activeTab === tab.id;
    const isDirty = !!dirtySections[tab.id];
    const errors = errorCounts[tab.id] ?? 0;

    return (
      <button
        key={tab.id}
        type="button"
        role="tab"
        aria-selected={isActive}
        title={tab.description}
        onClick={() => onTabChange(tab.id)}
        className={`w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-xs transition-colors cursor-pointer text-left ${
          isActive
            ? 'bg-[var(--ds-selected)] text-[var(--ds-ink)] font-medium'
            : 'text-[var(--ds-ink-2)] hover:bg-[var(--ds-hover)] hover:text-[var(--ds-ink)]'
        }`}
      >
        <Icon className={`w-3.5 h-3.5 shrink-0 ${isActive ? 'text-[var(--ds-accent)]' : 'text-[var(--ds-ink-3)]'}`} />
        <span className="truncate flex-1">{tab.label}</span>

        {errors > 0 && (
          <span
            className="badge b-bear shrink-0"
            style={{ fontSize: '9px', padding: '0 4px' }}
            title={`${errors} validation error(s)`}
          >
            {errors}
          </span>
        )}
        {isDirty && errors === 0 && (
          <span
            className="w-1.5 h-1.5 rounded-full bg-[var(--ds-warn)] shrink-0"
            title="Unsaved changes"
          />
        )}
      </button>
    );
  };

  return (
    <nav
      className="card card-pad space-y-2 lg:sticky lg:top-4 self-start"
      role="tablist"
      aria-label="Settings navigation"
      aria-orientation="vertical"
    >
      <div className="relative">
        <Search className="w-3.5 h-3.5 text-[var(--ds-ink-3)] absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Search settings…"
          aria-label="Search settings"
          className="w-full bg-[var(--ds-surface)] border border-[var(--ds-border-strong)] rounded-[var(--radius-md)] pl-8 pr-7 py-1.5 text-xs text-[var(--ds-ink)] placeholder:text-[var(--ds-ink-3)] transition-colors focus:outline-none focus:border-[var(--ds-accent)] focus:ring-1 focus:ring-[var(--ds-accent)]"
        />
        {isFiltering ? (
          <button
            type="button"
            onClick={() => onQueryChange('')}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--ds-ink-3)] hover:text-[var(--ds-ink)] cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        ) : (
          <kbd className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] font-mono text-[var(--ds-ink-4)] pointer-events-none">
            /
          </kbd>
        )}
      </div>

      <div className="flex flex-col gap-0.5">
        {results.map(renderItem)}
      </div>

      {isFiltering && results.length === 0 && (
        <p className="text-[11px] text-[var(--ds-ink-3)] px-1 py-2">
          No settings match “{query}”.
        </p>
      )}

      <p className="text-[11px] text-[var(--ds-ink-3)] leading-normal px-1 pt-1 border-t border-[var(--ds-border-subtle)] hidden lg:block">
        {getTabDef(activeTab).description}
      </p>
    </nav>
  );
}
