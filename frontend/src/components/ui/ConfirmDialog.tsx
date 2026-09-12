'use client';

/**
 * ConfirmDialog — explicit-intent confirmation for consequential actions
 * (EXECUTION_SAFETY.md §5, UI plan Phase 2.3).
 *
 * Built on the existing radix Dialog wrapper (focus trap, Escape, return
 * focus, scroll lock come for free). The confirmation copy must identify the
 * exact target — never a generic "Are you sure?" — and, for executions,
 * restate the intent block so the operator confirms what they actually saw.
 */

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
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Full action phrase, e.g. "Delete NIFTY 15m LONG signal?" */
  title: string;
  /** One line on consequence, e.g. "This removes the signal from the active desk." */
  description?: string;
  /** Intent block restated above the confirm button (execution actions). */
  intentRows?: ConfirmIntentRow[];
  confirmLabel?: string;
  cancelLabel?: string;
  /** danger = destructive (red confirm), primary = consequential but safe (blue). */
  tone?: 'danger' | 'primary';
  /** While the action runs after confirmation (button busy state). */
  busy?: boolean;
  onConfirm: () => void;
};

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  intentRows,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next); }}>
      <DialogContent className="max-w-md gap-3">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>

        {intentRows && intentRows.length > 0 ? (
          <div className="rounded-md border border-border bg-secondary/40 px-3 py-2">
            {intentRows.map((r) => (
              <div key={r.label} className="flex items-baseline justify-between gap-3 py-0.5">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {r.label}
                </span>
                <span className="num text-xs font-semibold text-foreground">{r.value}</span>
              </div>
            ))}
          </div>
        ) : null}

        <DialogFooter>
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={() => onOpenChange(false)}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={tone === 'danger' ? 'btn btn-sell' : 'btn btn-primary'}
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? 'Working…' : confirmLabel}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ConfirmDialog;
