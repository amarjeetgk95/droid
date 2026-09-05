'use client';
import React, { memo, useCallback } from 'react';
import { GitBranch } from 'lucide-react';
import type { AISettings, AITaskId, AIRoutingMode } from '@/lib/settings';
import { TASK_LABELS } from './constants';
import { SettingSection } from '../ui/SettingPrimitives';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export const TaskRoutingGrid = memo(function TaskRoutingGrid({ settings, onChange }: Props) {
  const routingMode: AIRoutingMode = (settings as unknown as { routingMode: AIRoutingMode }).routingMode || 'Task Optimized';
  const handleTaskModel = useCallback((task: AITaskId, model: string) => {
    const current = (settings as unknown as { taskModels: Record<string, string> }).taskModels || {};
    onChange({ taskModels: { ...current, [task]: model } } as unknown as Partial<AISettings>);
  }, [settings, onChange]);

  return (
    <SettingSection
      title="Task-Specific Model Routing"
      description="Different models for different tasks. Manual = explicit per-task; Task Optimized (default) = auto per category; Best Available = highest rank free; Cost Optimized = fastest cheapest free."
      icon={GitBranch}
      action={
        <span className="text-[10px] px-2 py-0.5 rounded-md bg-secondary border border-border/60 font-mono text-muted-foreground">
          {routingMode} · 6 tasks
        </span>
      }
    >
      <div className="p-5">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(Object.keys(TASK_LABELS) as AITaskId[]).map((task) => (
            <div key={task} className="bg-secondary/30 border border-border/40 rounded-lg p-3 space-y-1.5">
              <div className="text-xs font-medium text-foreground">{TASK_LABELS[task].label}</div>
              <div className="text-[11px] text-muted-foreground">{TASK_LABELS[task].hint}</div>
              <input type="text" value={(settings as unknown as { taskModels: Record<string, string> }).taskModels?.[task] || 'auto'} onChange={(e) => handleTaskModel(task, e.target.value)} placeholder="auto or model id" className="w-full bg-card border border-border/70 rounded-md px-2 py-1.5 text-xs font-mono focus:outline-hidden focus:border-ring" />
              <div className="text-[10px] text-muted-foreground">Use <span className="font-mono">auto</span> for best free {TASK_LABELS[task].hint}</div>
            </div>
          ))}
        </div>
      </div>
    </SettingSection>
  );
});
