'use client';

import { StrategyTemplate } from '@/lib/types';
import { Sparkles } from 'lucide-react';

export function TemplateSelector({
  templates,
  selectedTemplateId,
  onSelectTemplate,
}: {
  templates: StrategyTemplate[];
  selectedTemplateId: string | null;
  onSelectTemplate: (templateId: string) => void;
}) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <h3 className="font-bold text-sm text-foreground">Pre-Built Institutional Templates</h3>
        </div>
        <span className="text-xs text-muted-foreground">Quick Setup</span>
      </div>

      <div className="flex flex-wrap gap-2">
        {templates.map((tmpl) => {
          const isSelected = selectedTemplateId === tmpl.id;
          return (
            <button
              key={tmpl.id}
              onClick={() => onSelectTemplate(tmpl.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer border ${
                isSelected
                  ? 'bg-primary text-primary-foreground border-primary shadow-xs'
                  : 'bg-secondary hover:bg-secondary/80 text-muted-foreground hover:text-foreground border-border'
              }`}
            >
              {tmpl.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
