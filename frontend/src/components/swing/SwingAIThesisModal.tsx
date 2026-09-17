'use client';

import { useState, useEffect } from 'react';
import { Bot, Copy, Check, ShieldAlert, Sparkles, AlertCircle, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import type { SwingSetupDTO } from '@/lib/api/swing';
import { Modal } from '@/components/shared/Modal';
import { fmtINR, fmtNum } from '@/components/ui/desk';

export type SwingAIThesisModalProps = {
  setup: SwingSetupDTO | null;
  isOpen: boolean;
  onClose: () => void;
};

type ThesisPayload = {
  setup_id: string;
  contract: string;
  context: Record<string, unknown>;
  structured_prompt: string;
} | null;

export function SwingAIThesisModal({ setup, isOpen, onClose }: SwingAIThesisModalProps) {
  const [loading, setLoading] = useState(false);
  const [thesisData, setThesisData] = useState<ThesisPayload>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setCopyError(null);
    if (!isOpen || !setup) {
      setThesisData(null);
      setFetchError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setFetchError(null);
    setThesisData(null);

    api
      .getSwingThesis(setup.setup_id)
      .then((res) => {
        if (!cancelled) setThesisData(res?.data ?? null);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setFetchError(
            err instanceof Error && err.message
              ? err.message
              : 'Thesis generation failed — the prompt payload is unavailable.',
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, setup, reloadKey]);

  if (!isOpen || !setup) return null;

  const prompt = thesisData?.structured_prompt ?? null;

  const handleCopy = async () => {
    if (!prompt) return;
    setCopyError(null);
    const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined;
    if (!clipboard?.writeText) {
      setCopyError('The clipboard is unavailable in this browser context.');
      return;
    }
    try {
      await clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      setCopyError(
        err instanceof Error && err.message ? `Copy failed: ${err.message}` : 'Copy failed.',
      );
    }
  };

  const delta = setup.greeks?.delta ?? 0;
  const thetaDay = setup.greeks?.theta_day ?? 0;
  const ivPct = Number.isFinite(setup.iv) ? fmtNum(setup.iv * 100, 1) : null;
  const ivRank = Number.isFinite(setup.iv_percentile) ? fmtNum(setup.iv_percentile, 0) : null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      maxWidth="2xl"
      title={
        <span className="flex items-center gap-2 flex-wrap">
          <Bot className="w-4 h-4 text-primary" />
          AI Options Thesis: {setup.underlying} {setup.strike} {setup.option_type}
          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-primary/20 text-primary border border-primary/30 font-mono">
            {setup.expiry_date} ({setup.dte} DTE)
          </span>
        </span>
      }
      footer={
        <>
          <span className="flex-1 text-[11px] text-muted-foreground">
            Non-negotiable rule §1.2: AI is read-only and may never adjust stops or risk.
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            Close
          </button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        {/* Setup Snapshot Box */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3 rounded-lg bg-muted/40 border border-border/60 text-xs">
          <div>
            <div className="text-muted-foreground text-[10px] uppercase font-semibold">Entry Premium</div>
            <div className="font-semibold text-foreground text-sm font-mono">{fmtINR(setup.entry_premium)}</div>
            <div className="text-[10px] text-muted-foreground">Spot: {fmtINR(setup.spot_price)}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px] uppercase font-semibold">Option Stop</div>
            <div className="font-semibold text-destructive text-sm font-mono">{fmtINR(setup.stop_premium)}</div>
            <div className="text-[10px] text-muted-foreground font-mono">Spot Stop: {fmtINR(setup.spot_stop)}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px] uppercase font-semibold">Targets (1.5R / 3R)</div>
            <div className="font-semibold text-up text-sm font-mono">{fmtINR(setup.target_premium_1)}</div>
            <div className="text-[10px] text-muted-foreground font-mono">T2: {fmtINR(setup.target_premium_2)}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[10px] uppercase font-semibold">Greeks & IV</div>
            <div className="font-semibold text-foreground text-xs font-mono">
              Δ {fmtNum(delta)} | Θ -{fmtINR(Math.abs(thetaDay))}
            </div>
            <div className="text-[10px] text-muted-foreground">
              IV: {ivPct === null ? '—' : `${ivPct}%`} ({ivRank === null ? '—' : `${ivRank}%`})
            </div>
          </div>
        </div>

        {/* Confirmations */}
        <div>
          <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
            Technical & Volatility Confirmations
          </h4>
          <ul className="space-y-1.5 text-xs text-foreground/90">
            {(setup.technical_reasons ?? []).map((r, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-up mt-0.5">•</span>
                <span>{r}</span>
              </li>
            ))}
            {(setup.options_reasons ?? []).map((r, i) => (
              <li key={`opt-${i}`} className="flex items-start gap-2">
                <span className="text-accent mt-0.5">•</span>
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
            <div className="p-3 rounded-lg border border-warn/20 bg-warn/5 text-warn text-xs space-y-1">
              {(setup.risk_reasons ?? []).map((r, i) => (
                <div key={i} className="flex items-start gap-2">
                  <AlertCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  <span>{r}</span>
                </div>
              ))}
            </div>

            <div className="p-3 rounded-lg border border-destructive/20 bg-destructive/5 text-destructive text-xs space-y-1">
              {(setup.invalidation_rules ?? []).map((r, i) => (
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
          <div className="flex items-center justify-between mb-2 gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Deterministic Copilot Prompt Payload
            </span>
            <div className="flex items-center gap-2">
              {fetchError && !loading && (
                <button
                  type="button"
                  onClick={() => setReloadKey((k) => k + 1)}
                  className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md border border-border bg-background hover:bg-muted text-foreground transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span>Retry</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => void handleCopy()}
                disabled={!prompt}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md bg-muted hover:bg-muted/80 text-foreground transition-colors disabled:opacity-50"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-up" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'Copied' : 'Copy Prompt'}</span>
              </button>
            </div>
          </div>

          {copyError && (
            <p role="alert" className="mb-2 text-[11px] text-down font-mono">
              {copyError}
            </p>
          )}

          {loading ? (
            <div className="flex items-center justify-center gap-2 p-6 rounded-lg bg-muted/40 border border-border text-xs text-muted-foreground">
              <Sparkles className="w-4 h-4 animate-spin text-primary" />
              <span>Generating structured trade thesis…</span>
            </div>
          ) : fetchError ? (
            <div
              role="alert"
              className="flex items-start gap-2 p-3 rounded-lg border border-down/30 bg-down/5 text-xs"
            >
              <AlertCircle className="w-4 h-4 text-down mt-0.5 shrink-0" />
              <div className="min-w-0">
                <div className="font-semibold text-down">Thesis unavailable</div>
                <p className="text-muted-foreground break-words">{fetchError}</p>
              </div>
            </div>
          ) : (
            <pre className="p-3 rounded-lg bg-muted border border-border text-[11px] text-muted-foreground whitespace-pre-wrap font-mono max-h-36 overflow-y-auto">
              {prompt ?? 'Prompt payload unavailable.'}
            </pre>
          )}
        </div>
      </div>
    </Modal>
  );
}
