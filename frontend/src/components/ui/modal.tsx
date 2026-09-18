'use client';

/*
 * Modal — prop-based dialog adapter on top of the radix Dialog primitive.
 *
 * Preserves the legacy shared-kit Modal API (isOpen/onClose/title/footer/
 * maxWidth/closeDisabled) while delegating focus trap, initial focus, focus
 * restore, Escape handling and scroll lock to radix (see ui/dialog.tsx).
 */

import React, { useId, useRef } from 'react';
import { Dialog as DialogPrimitive } from 'radix-ui';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '4xl';
  /**
   * While true, Escape and backdrop clicks do not dismiss the modal
   * (e.g. an async confirmation is in flight). The labelled close button is
   * disabled too.
   */
  closeDisabled?: boolean;
}

const maxWidthClasses = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '4xl': 'max-w-4xl',
};

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = 'lg',
  closeDisabled = false,
}: ModalProps) {
  const titleId = useId();
  const contentRef = useRef<HTMLDivElement>(null);

  return (
    <DialogPrimitive.Root
      open={isOpen}
      onOpenChange={(next) => {
        // While an action is in flight, Escape / backdrop must not dismiss.
        if (!next && !closeDisabled) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-scrim backdrop-blur-xs data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <DialogPrimitive.Content
            ref={contentRef}
            aria-modal="true"
            aria-labelledby={titleId}
            onOpenAutoFocus={(event) => {
              // Prefer an explicit opt-in target, like the legacy Modal did.
              const target = contentRef.current?.querySelector<HTMLElement>('[data-autofocus]');
              if (target) {
                event.preventDefault();
                target.focus();
              }
            }}
            className={`relative w-full ${maxWidthClasses[maxWidth]} bg-card border border-border rounded-xl shadow-2xl overflow-hidden z-10 animate-in fade-in-0 zoom-in-95 duration-150`}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border-subtle bg-surface-subtle/80">
              <div id={titleId} className="text-base font-semibold text-foreground">
                {title}
              </div>
              <DialogPrimitive.Close
                disabled={closeDisabled}
                aria-label="Close dialog"
                className="text-ink-4 hover:text-ink-2 transition-colors p-1 rounded-lg hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
              >
                ✕
              </DialogPrimitive.Close>
            </div>

            <div className="p-5 max-h-[80vh] overflow-y-auto text-foreground">{children}</div>

            {footer && (
              <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-border-subtle bg-surface-subtle/60">
                {footer}
              </div>
            )}
          </DialogPrimitive.Content>
        </div>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
