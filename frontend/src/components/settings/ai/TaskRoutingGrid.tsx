'use client';
import React from 'react';
import { GitBranch } from 'lucide-react';
import type { AISettings, AITaskId, AIRoutingMode } from '@/lib/settings';
import { TASK_LABELS } from './constants';

interface Props {
  settings: AISettings;
  onChange: (updated: Partial<AISettings>) => void;
}

export function TaskRoutingGrid({ settings, onChange }: Props) {
  const routingMode: AIRoutingMode = (settings as unknown as { routingMode: AIRoutingMode }).routingMode || 'Task Optimized';
  const handleTaskModel = (task: AITaskId, model: string) => {
    const current = (settings as unknown as { taskModels: Record<string, string> }).taskModels || {};
    onChange({ taskModels: { ...current, [task]: model } } as unknown as Partial<AISettings>);
  };

  return (
    <div className="bg-card border border-border rounded-xl p-5 space-y-3 shadow-xs">
      <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
        <GitBranch className="w-4 h-4 text-primary" />
        Task-Specific Model Routing
        <span className="text-[10px] px-2 py-0.5 rounded bg-secondary border font-mono">6 TASKS</span>
        <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 font-mono">{routingMode}</span>
      </h3>
      <p className="text-xs text-muted-foreground">Different models for different tasks. Routing mode determines selection strategy. Manual = explicit per-task; Task Optimized (default) = auto per category; Best Available = highest rank free; Cost Optimized = fastest cheapest free.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {(Object.keys(TASK_LABELS) as AITaskId[]).map((task) => (
          <div key={task} className="bg-secondary/30 border border-border/60 rounded-lg p-3 space-y-1.5">
            <div className="text-xs font-semibold text-foreground">{TASK_LABELS[task].label}</div>
            <div className="text-[11px] text-muted-foreground">{TASK_LABELS[task].hint}</div>
            <input type="text" value={(settings as unknown as { taskModels: Record<string, string> }).taskModels?.[task] || 'auto'} onChange={(e) => handleTaskModel(task, e.target.value)} placeholder="auto or model id" className="w-full bg-card border border-border rounded-lg px-2 py-1.5 text-xs font-mono" />
            <div className="text-[10px] text-muted-foreground">Use <span className="font-mono">auto</span> for best free {TASK_LABELS[task].hint}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
