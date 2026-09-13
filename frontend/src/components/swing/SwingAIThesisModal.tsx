'use client';

import { useState, useEffect } from 'react';
import { Bot, Copy, Check, X, ShieldAlert, Sparkles, AlertCircle } from 'lucide-react';
import { api } from '@/lib/api';
import type { SwingSetupDTO } from '@/lib/api/swing';

export type SwingAIThesisModalProps = {
  setup: SwingSetupDTO | null;
  isOpen: boolean;
  onClose: () => void;
};

export function SwingAIThesisModal({ setup, isOpen, onClose }: SwingAIThesisModalProps) {
  const [loading, setLoading] = useState(false);
  const [thesisData, setThesisData] = useState<any>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isOpen && setup) {
      setLoading(true);
      api
        .getSwingThesis(setup.setup_id)
        .then((res) => {
          if (res?.data) {
            setThesisData(res.data);
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false));
    } else {
      setThesisData(null);
    }
  }, [isOpen, setup]);

  if (!isOpen || !setup) return null;

  const handleCopy = () => {
    if (thesisData?.structured_prompt) {
      navigator.clipboard.writeText(thesisData.structured_prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-card text-card-foreground shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/30">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 text-primary">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-semibold text-foreground">
                  AI Swing Thesis: {setup.symbol}
                </h3>
                <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-primary/20 text-primary border border-primary/30">
                  {setup.strategy.replace(/_/g, ' ')}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Read-only advisory trade briefing (§57) — strictly constrained to deterministic levels
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 text-sm">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-3">
              <Sparkles className="w-6 h-6 animate-spin text-primary" />
              <span>Generating structured trade thesis...</span>
            </div>
          ) : (
            <>
              {/* Setup Snapshot Box */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-lg bg-muted/40 border border-border/60 text-xs">
                <div>
                  <div className="text-muted-foreground">Trigger Entry</div>
                  <div className="font-semibold text-foreground text-sm">₹{setup.trigger_price}</div>
                  <div className="text-[10px] text-muted-foreground">Max chase: ₹{setup.max_chase_price}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Invalidation Stop</div>
                  <div className="font-semibold text-destructive text-sm">₹{setup.stop_price}</div>
                  <div className="text-[10px] text-muted-foreground">ATR floor: ₹{setup.atr_floor}</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Target 1 & 2</div>
                  <div className="font-semibold text-emerald-500 text-sm">₹{setup.target_1} / ₹{setup.target_2}</div>
                  <div className="text-[10px] text-muted-foreground">1.5R & 3.0R Multiples</div>
                </div>
                <div>
                  <div className="text-muted-foreground">Score & Expected Hold</div>
                  <div className="font-semibold text-foreground text-sm">{setup.score.total}/100</div>
                  <div className="text-[10px] text-muted-foreground">{setup.expected_holding_days} trading days</div>
                </div>
              </div>

              {/* Confirmations */}
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Technical Confirmations
                </h4>
                <ul className="space-y-1.5 text-xs text-foreground/90">
                  {setup.technical_reasons.map((r, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-emerald-500 mt-0.5">•</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Risks & Invalidation */}
              <div>
                <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Key Risks & Invalidation Criteria
                </h4>
                <div className="space-y-2">
                  <div className="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5 text-amber-600 dark:text-amber-400 text-xs space-y-1">
                    {setup.risk_reasons.map((r, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>

                  <div className="p-3 rounded-lg border border-destructive/20 bg-destructive/5 text-destructive text-xs space-y-1">
                    {setup.invalidation_rules.map((r, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                        <span>{r}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Raw Prompt Preview / Export */}
              <div className="pt-2 border-t border-border">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    Deterministic Copilot Prompt Payload
                  </span>
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 text-foreground transition-colors"
                  >
                    {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copied ? 'Copied' : 'Copy Prompt'}</span>
                  </button>
                </div>
                <pre className="p-3 rounded-lg bg-black/40 border border-border text-[11px] text-muted-foreground whitespace-pre-wrap font-mono max-h-36 overflow-y-auto">
                  {thesisData?.structured_prompt || 'Loading prompt...'}
                </pre>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-border bg-muted/20">
          <span className="text-[11px] text-muted-foreground">
            Non-negotiable rule §1.2: AI is read-only and may never adjust stops or risk.
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
