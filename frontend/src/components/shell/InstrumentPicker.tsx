'use client';

import { useCallback, useMemo, useRef, type KeyboardEvent } from 'react';
import { useCommandSection } from '@/context/AppStreamContext';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import { findInstrumentCard } from '@/lib/symbols';
import type { IndexCard } from '@/lib/types';

const OPTIONS: Array<{ id: SupportedInstrument; label: string; name: string }> = [
  { id: 'NIFTY', label: 'NIFTY', name: 'NIFTY 50' },
  { id: 'BANKNIFTY', label: 'BANKNIFTY', name: 'NIFTY Bank' },
  { id: 'SENSEX', label: 'SENSEX', name: 'BSE Sensex' },
];

const quoteFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function marketCards(value: unknown): IndexCard[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const cards = (value as { cards?: unknown }).cards;
  return Array.isArray(cards) ? (cards as IndexCard[]) : [];
}

export function InstrumentPicker() {
  const { instrument, setInstrument } = useInstrument();
  const marketSection = useCommandSection('market');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const cards = useMemo(() => marketCards(marketSection?.value), [marketSection?.value]);

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
      let next = -1;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % OPTIONS.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + OPTIONS.length) % OPTIONS.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = OPTIONS.length - 1;
      if (next === -1) return;
      event.preventDefault();
      setInstrument(OPTIONS[next].id);
      tabRefs.current[next]?.focus();
    },
    [setInstrument],
  );

  return (
    <div className="instrument-tabs" role="tablist" aria-label="Instrument">
      {OPTIONS.map((option, index) => {
        const active = instrument === option.id;
        const card = findInstrumentCard(cards, option.id);
        const changeClass = card
          ? card.change_percent >= 0
            ? 'v-bull'
            : 'v-bear'
          : undefined;
        return (
          <button
            key={option.id}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            className="instrument-tab"
            title={`${option.name} — switch the whole terminal`}
            onClick={() => setInstrument(option.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            <span className="instrument-tab__sym">{option.label}</span>
            {card ? (
              <span className="instrument-tab__quote" aria-hidden="true">
                <span>{quoteFormat.format(card.ltp)}</span>
                <span className={changeClass}>
                  {card.change_percent >= 0 ? '+' : ''}
                  {card.change_percent.toFixed(2)}%
                </span>
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
