'use client';

import * as React from 'react';
import { Database, Layers, LineChart, TrendingUp, CalendarDays, Star, ClipboardList, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

export type HiSectionId = 'overview' | 'analogs' | 'datasets' | 'patterns' | 'shifts' | 'seasonality' | 'watchlist' | 'audit';

interface NavDef {
  id: HiSectionId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  description: string;
}

const NAV: NavDef[] = [
  { id: 'overview', label: 'Overview', icon: Database, description: 'Storage, coverage, activity' },
  { id: 'analogs', label: 'Fractals & S/R', icon: Sparkles, description: 'Empirical analog similarity & S/R map' },
  { id: 'datasets', label: 'Datasets', icon: Layers, description: 'Derivatives, categories, retention' },
  { id: 'patterns', label: 'Patterns', icon: LineChart, description: 'Similarity setups and outcomes' },
  { id: 'shifts', label: 'Shifts', icon: TrendingUp, description: 'Multi-session regime shifts' },
  { id: 'seasonality', label: 'Seasonality', icon: CalendarDays, description: 'Day-of-week behaviour' },
  { id: 'watchlist', label: 'Watchlist', icon: Star, description: 'Symbols you are tracking' },
  { id: 'audit', label: 'Audit', icon: ClipboardList, description: 'Deletion and labelling log' },
];

interface Props {
  active: HiSectionId;
  onSelect: (id: HiSectionId) => void;
}

export function HiSectionNav({ active, onSelect }: Props) {
  return (
    <nav aria-label="Historical Intelligence sections" className="w-full lg:w-56 shrink-0">
      <ul className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible pb-1 lg:pb-0">
        {NAV.map((item) => {
          const Icon = item.icon;
          const isActive = active === item.id;
          return (
            <li key={item.id} className="shrink-0">
              <button
                type="button"
                onClick={() => onSelect(item.id)}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'group flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors whitespace-nowrap w-full text-left',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                )}
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="flex-1 truncate">{item.label}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function hiSectionMeta(id: HiSectionId): NavDef {
  return NAV.find((n) => n.id === id) ?? NAV[0];
}