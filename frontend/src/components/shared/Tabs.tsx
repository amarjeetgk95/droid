'use client';

import React from 'react';

export interface TabItem {
  id: string;
  label: React.ReactNode;
  badge?: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (tabId: string) => void;
  variant?: 'pills' | 'underline';
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  activeTab,
  onChange,
  variant = 'pills',
  className = '',
}) => {
  return (
    <div
      className={`flex items-center gap-1 ${
        variant === 'underline' ? 'border-b border-border' : 'bg-muted p-1 rounded-lg border border-border'
      } ${className}`}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            disabled={tab.disabled}
            onClick={() => !tab.disabled && onChange(tab.id)}
            className={`inline-flex items-center gap-2 px-3 py-1.5 text-xs font-mono font-medium rounded-md transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed ${
              variant === 'underline'
                ? isActive
                  ? 'text-primary border-b-2 border-primary rounded-none -mb-px font-semibold'
                  : 'text-ink-3 hover:text-foreground'
                : isActive
                ? 'bg-card text-primary shadow-xs border border-border font-semibold'
                : 'text-ink-2 hover:text-foreground hover:bg-muted-strong/60'
            }`}
          >
            {tab.icon && <span>{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.badge && <span>{tab.badge}</span>}
          </button>
        );
      })}
    </div>
  );
};
