'use client';

/**
 * ConfirmDialog — explicit-intent confirmation for consequential actions
 * (EXECUTION_SAFETY.md §5, UI plan Phase 2.3).
 *
 * Built on the radix Dialog wrapper (focus trap, initial focus, Escape,
 * return focus, scroll lock). Two calling styles are supported:
 *
 *  - controlled: `open` / `onOpenChange` (radix kit)
 *  - legacy:     `isOpen` / `onClose` (shared kit) — after `onConfirm`
 *                resolves the dialog closes itself, exactly as before
 *
 * The legacy typed-confirmation challenge ("KILL"/"DELETE") and inline error
 * reporting live here too, so every confirmation shares one implementation.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { errorMessage as canonicalErrorMessage } from '@/lib/errors';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export type ConfirmIntentRow = {
  label: string;
  value: string;
};

export type ConfirmDialogProps = {
  /** Controlled open state (radix kit). */
  open?: boolean;
  /** Legacy open state (shared kit); pair with `onClose`. */
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Legacy close callback; pair with `isOpen`. */
  onClose?: () => void;
  /** Full action phrase, e.g. "Delete NIFTY 15m LONG signal?" */
  title: string;
  /** One line on consequence (radix kit). */
  description?: React.ReactNode;
  /** Legacy supporting copy; `description` wins when both are given. */
  message?: React.ReactNode;
  /** Intent block restated above the confirm button (execution actions). */
  intentRows?: ConfirmIntentRow[];
  confirmLabel?: string;
  cancelLabel?: string;
  /** danger = destructive (red confirm), primary = consequential but safe (blue). */
  tone?: 'danger' | 'primary';
  /** Legacy alias for `tone="danger"`. */
  destructive?: boolean;
  /** While the action runs after confirmation (externally managed busy state). */
  busy?: boolean;
  /** Typed challenge (e.g. "KILL", "DELETE"); confirm stays disabled until matched. */
  requireTypedConfirmation?: string;
  onConfirm: () => void | Promise<void>;
};

export function ConfirmDialog({
  open,
  isOpen,
  onOpenChange,
  onClose,
  title,
  description,
  message,
  intentRows,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone,
  destructive = false,
  busy = false,
  requireTypedConfirmation,
  onConfirm,
}: ConfirmDialogProps) {
  const isLegacy = isOpen !== undefined || (onClose !== undefined && onOpenChange === undefined);
  const resolvedOpen = open ?? isOpen ?? false;

  const [typedInput, setTypedInput] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const typedRef = useRef<HTMLInputElement>(null);

  // Reset all transient state whenever the dialog closes, including the
  // typed confirmation phrase — a later open must never inherit `KILL`.
  useEffect(() => {
    if (!resolvedOpen) {
      setTypedInput('');
      setPending(false);
      setError(null);
    }
  }, [resolvedOpen]);

  const effectiveBusy = busy || pending;
  const requiresTyped = Boolean(requireTypedConfirmation);
  const typedMatches = requiresTyped
    ? typedInput.trim().toUpperCase() === requireTypedConfirmation!.toUpperCase()
    : true;
  // Legacy default was primary (destructive=false); radix default is danger.
  const resolvedTone = destructive ? 'danger' : (tone ?? (isLegacy ? 'primary' : 'danger'));

  const requestClose = useCallback(
    (force = false) => {
      if (effectiveBusy && !force) return;
      if (onOpenChange) onOpenChange(false);
      else onClose?.();
    },
    [effectiveBusy, onOpenChange, onClose],
  );

  const handleConfirm = () => {
    if (!typedMatches || effectiveBusy) return;
    setError(null);

    let result: void | Promise<void>;
    try {
      result = onConfirm();
    } catch (e) {
      setError(canonicalErrorMessage(e, 'The action did not complete. No confirmation was recorded.'));
      return;
    }

    if (result && typeof (result as Promise<void>).then === 'function') {
      setPending(true);
      void (result as Promise<void>)
        .then(() => {
          if (isLegacy) requestClose(true);
        })
        .catch((e: unknown) => {
          setError(
            canonicalErrorMessage(e, 'The action did not complete. No confirmation was recorded.'),
          );
        })
        .finally(() => {
          setPending(false);
        });
    } else if (isLegacy) {
      // Legacy callers relied on the dialog closing itself after a sync confirm.
      requestClose(true);
    }
  };

  return (
    <Dialog
      open={resolvedOpen}
      onOpenChange={(next) => {
        if (!effectiveBusy) {
          if (onOpenChange) onOpenChange(next);
          else onClose?.();
        }
      }}
    >
      {/* Radix provides role=dialog, focus trap, initial focus and focus
          restore (ui/dialog.tsx adds aria-modal); while busy the
          onOpenChange guard blocks Escape/backdrop/X dismissal. */}
      <DialogContent
        className="max-w-md gap-3"
        aria-busy={effectiveBusy || undefined}
        onOpenAutoFocus={(event) => {
          if (requiresTyped) {
            event.preventDefault();
            typedRef.current?.focus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
          {!description && message ? (
            <DialogDescription asChild className="text-sm text-ink-2">
              <div>{message}</div>
            </DialogDescription>
          ) : null}
        </DialogHeader>

        {intentRows && intentRows.length > 0 ? (
          <div className="rounded-md border border-border bg-secondary/40 px-3 py-2">
            {intentRows.map((r) => (
              <div key={r.label} className="flex items-baseline justify-between gap-3 py-0.5">
                <span className="text-[11px] font-semibold tracking-wide text-muted-foreground">
                  {r.label}
                </span>
                <span className="num text-xs font-semibold text-foreground">{r.value}</span>
              </div>
            ))}
          </div>
        ) : null}

        {error ? (
          <p role="alert" className="text-xs text-down-strong font-mono">
            {error}
          </p>
        ) : null}

        {requiresTyped ? (
          <div className="space-y-2 pt-2 border-t border-border">
            <label className="block text-xs font-mono text-ink-2" htmlFor="confirm-typed-input">
              Type <span className="font-bold text-warn-strong">{requireTypedConfirmation}</span> to
              continue:
            </label>
            <input
              ref={typedRef}
              id="confirm-typed-input"
              data-autofocus
              type="text"
              value={typedInput}
              onChange={(e) => setTypedInput(e.target.value)}
              placeholder={requireTypedConfirmation}
              autoComplete="off"
              spellCheck={false}
              className="input font-mono"
            />
          </div>
        ) : null}

        <DialogFooter>
          <button
            type="button"
            className="btn"
            disabled={effectiveBusy}
            onClick={() => requestClose()}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={resolvedTone === 'danger' ? 'btn btn-sell' : 'btn btn-primary'}
            disabled={effectiveBusy || !typedMatches}
            onClick={handleConfirm}
          >
            {effectiveBusy ? (isLegacy ? 'Processing…' : 'Working…') : confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConfirmDialog;
