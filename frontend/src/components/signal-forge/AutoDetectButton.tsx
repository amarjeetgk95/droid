'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { errorMessage } from './forgeLogic';
import type { AutoDetectCandidate } from '@/lib/api/signals';

interface AutoDetectButtonProps {
  underlying: string;
  strategy?: string;
  timeframe?: string;
  onDetected: (candidate: AutoDetectCandidate, detected: boolean, message: string) => void;
  onUnavailable: (message: string) => void;
}

/**
 * Requests a server-side setup detection. On any failure the parent form is
 * left untouched and told why — no demo levels are ever synthesized here.
 */
export const AutoDetectButton: React.FC<AutoDetectButtonProps> = ({
  underlying,
  strategy,
  timeframe,
  onDetected,
  onUnavailable,
}) => {
  const [detecting, setDetecting] = useState(false);

  const handleAutoDetect = async () => {
    if (detecting) return;
    setDetecting(true);
    try {
      const res = await api.autoDetectSignal({
        underlying,
        ...(strategy ? { strategy } : {}),
        ...(timeframe ? { timeframe } : {}),
      });
      const candidate = res?.candidate;
      if (!candidate || typeof candidate !== 'object') {
        onUnavailable(res?.message || 'no candidate payload returned');
        return;
      }
      onDetected(candidate, Boolean(res?.detected), res?.message || '');
    } catch (e) {
      onUnavailable(errorMessage(e, 'request failed'));
    } finally {
      setDetecting(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleAutoDetect}
      disabled={detecting}
      aria-busy={detecting}
      className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-primary hover:bg-accent-strong text-white font-mono text-xs font-semibold shadow-sm transition-all duration-150 disabled:opacity-50"
    >
      <span aria-hidden="true">{detecting ? '…' : '⚡'}</span>
      <span>{detecting ? 'Detecting Pattern…' : 'Auto-Detect Setup'}</span>
    </button>
  );
};
