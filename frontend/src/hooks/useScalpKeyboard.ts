'use client';

import { useEffect, useRef } from 'react';

export interface ScalpKeyboardHandlers {
  onBuyCall?: () => void;
  onBuyPut?: () => void;
  onSetLots?: (lots: number) => void;
  onPanicSquareOff?: () => void;
  onToggleHelp?: () => void;
  onToggleFullscreen?: () => void;
}

/**
 * Single authoritative keyboard listener for Scalper Terminal.
 * Prevents duplicated window listeners across components.
 */
export function useScalpKeyboard(handlers: ScalpKeyboardHandlers) {
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }

      // Shift + Escape = Emergency Square Off All
      if (e.shiftKey && e.key === 'Escape') {
        e.preventDefault();
        handlersRef.current.onPanicSquareOff?.();
        return;
      }

      // Ignore if meta, ctrl, or alt is held down
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toLowerCase();

      if (key === 'c') {
        e.preventDefault();
        handlersRef.current.onBuyCall?.();
      } else if (key === 'p') {
        e.preventDefault();
        handlersRef.current.onBuyPut?.();
      } else if (key === '1') {
        e.preventDefault();
        handlersRef.current.onSetLots?.(1);
      } else if (key === '2') {
        e.preventDefault();
        handlersRef.current.onSetLots?.(2);
      } else if (key === '3') {
        e.preventDefault();
        handlersRef.current.onSetLots?.(4);
      } else if (key === '4') {
        e.preventDefault();
        handlersRef.current.onSetLots?.(10);
      } else if (e.key === '?') {
        e.preventDefault();
        handlersRef.current.onToggleHelp?.();
      } else if (key === 'f') {
        e.preventDefault();
        handlersRef.current.onToggleFullscreen?.();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);
}
