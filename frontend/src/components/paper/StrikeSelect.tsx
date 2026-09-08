'use client';

import { useMemo, useState } from 'react';
import type { ChainStrike } from '@/hooks/useOptionChain';

const WINDOW = 7; // strikes above/below ATM shown before "Show all"

function distanceLabel(strike: number, atm: number | null): string {
  if (atm === null) return '';
  const d = Math.round(strike - atm);
  if (d === 0) return 'ATM';
  return `${d > 0 ? '+' : '−'}${Math.abs(d)}`;
}

function optionLabel(s: ChainStrike, atm: number | null): string {
  const dist = distanceLabel(s.strike, atm);
  const ltp =
    s.ceLtp !== null || s.peLtp !== null
      ? ` · CE ₹${s.ceLtp ?? '—'} / PE ₹${s.peLtp ?? '—'}`
      : '';
  return `${s.strike} — ${dist || (s.isAtm ? 'ATM' : '')}${ltp}`;
}

export function StrikeSelect({
  value,
  onChange,
  strikes,
  atm,
  disabled,
  ariaLabel = 'Strike price',
  id,
}: {
  value: number;
  onChange: (strike: number) => void;
  strikes: ChainStrike[];
  atm: number | null;
  disabled?: boolean;
  ariaLabel?: string;
  id?: string;
}) {
  const [showAll, setShowAll] = useState(false);

  const visible = useMemo(() => {
    if (showAll || strikes.length === 0) return strikes;
    const atmIdx = Math.max(
      0,
      strikes.findIndex((s) => (atm !== null ? s.strike === atm : s.isAtm)),
    );
    const anchor = atmIdx >= 0 ? atmIdx : strikes.findIndex((s) => s.strike >= value);
    const center = anchor >= 0 ? anchor : Math.floor(strikes.length / 2);
    return strikes.slice(Math.max(0, center - WINDOW), center + WINDOW + 1);
  }, [showAll, strikes, atm, value]);

  // Selected strike may sit outside the window (e.g. retry-prefill from the
  // order book) — always keep it selectable instead of blanking the control.
  const options = useMemo(() => {
    if (visible.some((s) => s.strike === value)) return visible;
    const extra: ChainStrike[] = [{ strike: value, isAtm: value === atm, ceLtp: null, peLtp: null }];
    return [...extra, ...visible].sort((a, b) => a.strike - b.strike);
  }, [visible, value, atm]);

  return (
    <div className="space-y-1">
      <select
        id={id}
        value={String(value)}
        disabled={disabled || options.length === 0}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={ariaLabel}
        className="w-full bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground font-mono font-semibold focus:outline-hidden cursor-pointer"
      >
        {options.length === 0 && <option value="">Loading…</option>}
        {options.map((s) => (
          <option key={s.strike} value={s.strike}>
            {optionLabel(s, atm)}
          </option>
        ))}
      </select>
      {strikes.length > visible.length && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="text-[10px] font-bold text-primary hover:underline cursor-pointer"
        >
          {showAll ? 'Show near-ATM only' : `Show all ${strikes.length} strikes`}
        </button>
      )}
    </div>
  );
}
