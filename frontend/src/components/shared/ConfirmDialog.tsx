'use client';

import React, { useEffect, useState } from 'react';
import { Modal } from './Modal';

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  requireTypedConfirmation?: string; // e.g. "CONFIRM" or "KILL"
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  destructive = false,
  requireTypedConfirmation,
}) => {
  const [typedInput, setTypedInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset all transient state whenever the dialog closes, including the
  // typed confirmation phrase — a later open must never inherit `KILL`.
  useEffect(() => {
    if (!isOpen) {
      setTypedInput('');
      setLoading(false);
      setError(null);
    }
  }, [isOpen]);

  const isConfirmed = requireTypedConfirmation
    ? typedInput.trim().toUpperCase() === requireTypedConfirmation.toUpperCase()
    : true;

  const handleConfirm = async () => {
    if (!isConfirmed || loading) return;
    setError(null);
    try {
      setLoading(true);
      await onConfirm();
      onClose();
    } catch (e) {
      setError(
        e instanceof Error && e.message
          ? e.message
          : 'The action did not complete. No confirmation was recorded.',
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      // While the async action runs, Escape/backdrop must not dismiss.
      closeDisabled={loading}
      onClose={onClose}
      title={title}
      maxWidth="md"
      footer={
        <>
          <button type="button" onClick={onClose} disabled={loading} className="btn">
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={!isConfirmed || loading}
            className={destructive ? 'btn btn-sell' : 'btn btn-primary'}
          >
            {loading ? 'Processing…' : confirmLabel}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="text-sm text-ink-2">{message}</div>

        {error ? (
          <p role="alert" className="text-xs text-down-strong font-mono">
            {error}
          </p>
        ) : null}

        {requireTypedConfirmation && (
          <div className="space-y-2 pt-2 border-t border-border">
            <label className="block text-xs font-mono text-ink-2" htmlFor="confirm-typed-input">
              Type <span className="font-bold text-warn-strong">{requireTypedConfirmation}</span> to
              continue:
            </label>
            <input
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
        )}
      </div>
    </Modal>
  );
};
