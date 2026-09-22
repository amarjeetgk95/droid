'use client';

import { useCallback, useMemo, useRef, type KeyboardEvent } from 'react';
import { useCommandSection } from '@/context/AppStreamContext';
import { useMarketTicks } from '@/context/MarketTicksContext';
import { useInstrument, type SupportedInstrument } from '@/context/InstrumentContext';
import type { TimestampedTick } from '@/hooks/useMarketStream';
import { resolveIndexSymbol, type IndexQuoteSymbol } from '@/lib/symbols';
import type { IndexCard } from '@/lib/types';

/** WS ticks arrive at most ~20s old — older means the feed went stale. */
const WS_TICK_FRESH_MS = 20_000;

type StripItem = {
  id: IndexQuoteSymbol;
  label: string;
  name: string;
  /** Terminal instruments get a switchable tab; the rest are quote readouts. */
  selectable: SupportedInstrument | null;
  /** VIX-up is not "bullish" — its change stays neutral like the price. */
  directionTone: boolean;
};

/** The four indices shown on the rail. Only the switchable three get tabs. */
const INDEX_STRIP: StripItem[] = [
  { id: 'NIFTY', label: 'NIFTY', name: 'NIFTY 50', selectable: 'NIFTY', directionTone: true },
  { id: 'BANKNIFTY', label: 'BANKNIFTY', name: 'NIFTY Bank', selectable: 'BANKNIFTY', directionTone: true },
  { id: 'SENSEX', label: 'SENSEX', name: 'BSE Sensex', selectable: 'SENSEX', directionTone: true },
  { id: 'INDIAVIX', label: 'INDIAVIX', name: 'India VIX', selectable: null, directionTone: false },
];

const TABS = INDEX_STRIP.filter(
  (item): item is StripItem & { selectable: SupportedInstrument } => item.selectable !== null,
);
// Readouts render after the tablist so `role="tablist"` owns tabs only.
const QUOTE_READOUTS = INDEX_STRIP.filter((item) => item.selectable === null);

const quoteFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

type IndexQuote = {
  ltp: number;
  changePercent: number | null;
  /** True while the price came from a fresh WS tick, not the SSE card. */
  live: boolean;
};

function marketCards(value: unknown): IndexCard[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const cards = (value as { cards?: unknown }).cards;
  return Array.isArray(cards) ? (cards as IndexCard[]) : [];
}

function formatChange(changePercent: number): string {
  return `${changePercent >= 0 ? '+' : ''}${changePercent.toFixed(2)}%`;
}

/**
 * Change % straight off a WS tick (ltp vs previous close). The SSE card also
 * carries it, but arrives seconds later — deriving it here keeps the strip
 * complete from the first tick instead of popping the % in on card hydration.
 */
function tickChangePercent(tick: TimestampedTick): number | null {
  const previousClose = typeof tick.close === 'number' && tick.close > 0 ? tick.close : null;
  if (previousClose === null || typeof tick.ltp !== 'number') return null;
  return ((tick.ltp - previousClose) / previousClose) * 100;
}

/**
 * Merge the REST card snapshot with the fresh WS tick map into one quote per
 * canonical index. Only current sources are admitted: cards with a positive
 * LTP, ticks inside the freshness window. Unknown symbols are dropped instead
 * of being bucketed into NIFTY.
 */
function buildIndexQuotes(
  cards: IndexCard[],
  latestTicks: Record<string, TimestampedTick>,
  ticksFresh: boolean,
): Map<IndexQuoteSymbol, IndexQuote> {
  const quotes = new Map<IndexQuoteSymbol, IndexQuote>();
  for (const card of cards) {
    const id = resolveIndexSymbol(card.symbol);
    if (!id || typeof card.ltp !== 'number' || !(card.ltp > 0)) continue;
    quotes.set(id, {
      ltp: card.ltp,
      changePercent: typeof card.change_percent === 'number' ? card.change_percent : null,
      live: false,
    });
  }
  if (!ticksFresh) return quotes;
  const now = Date.now();
  for (const tick of Object.values(latestTicks)) {
    if (!tick || typeof tick.ltp !== 'number' || !(tick.ltp > 0)) continue;
    if (typeof tick.received_at !== 'number' || now - tick.received_at > WS_TICK_FRESH_MS) continue;
    const id = resolveIndexSymbol(tick.symbol);
    if (!id) continue;
    quotes.set(id, {
      ltp: tick.ltp,
      changePercent: quotes.get(id)?.changePercent ?? tickChangePercent(tick),
      live: true,
    });
  }
  return quotes;
}

export function InstrumentPicker() {
  const { instrument, setInstrument } = useInstrument();
  const marketSection = useCommandSection('market');
  const { latestTicks, ticksFresh } = useMarketTicks();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const cards = useMemo(() => marketCards(marketSection?.value), [marketSection?.value]);
  const quotes = useMemo(
    () => buildIndexQuotes(cards, latestTicks, ticksFresh),
    [cards, latestTicks, ticksFresh],
  );

  const handleKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
      let next = -1;
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = (index + 1) % TABS.length;
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = (index - 1 + TABS.length) % TABS.length;
      else if (event.key === 'Home') next = 0;
      else if (event.key === 'End') next = TABS.length - 1;
      if (next === -1) return;
      event.preventDefault();
      setInstrument(TABS[next].selectable);
      tabRefs.current[next]?.focus();
    },
    [setInstrument],
  );

  return (
    <>
      <div className="instrument-tabs" role="tablist" aria-label="Instrument">
        {TABS.map((tab, index) => {
          const active = instrument === tab.selectable;
          const quote = quotes.get(tab.id);
          const changeClass = quote?.changePercent != null
            ? quote.changePercent >= 0
              ? 'v-bull'
              : 'v-bear'
            : undefined;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              ref={(node) => {
                tabRefs.current[index] = node;
              }}
              className="instrument-tab"
              title={`${tab.name} — switch the whole terminal`}
              onClick={() => setInstrument(tab.selectable)}
              onKeyDown={(event) => handleKeyDown(event, index)}
            >
              <span className="instrument-tab__sym">{tab.label}</span>
              <span className="instrument-tab__quote" aria-hidden="true">
                <span
                  title={quote?.live ? 'Live tick via websocket' : undefined}
                  data-live={quote?.live ? 'ws' : undefined}
                >
                  {quote ? quoteFormat.format(quote.ltp) : '—'}
                </span>
                {quote?.changePercent != null ? (
                  <span className={changeClass}>{formatChange(quote.changePercent)}</span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>
      {QUOTE_READOUTS.map((item) => {
        const quote = quotes.get(item.id);
        const changeClass = item.directionTone && quote?.changePercent != null
          ? quote.changePercent >= 0
            ? 'v-bull'
            : 'v-bear'
          : undefined;
        return (
          <span
            key={item.id}
            className="instrument-quote"
            title={`${item.name} — index quote (display only, does not switch the terminal)`}
          >
            <span className="instrument-tab__sym">{item.label}</span>
            <span className="instrument-tab__quote">
              <span
                title={quote?.live ? 'Live tick via websocket' : undefined}
                data-live={quote?.live ? 'ws' : undefined}
              >
                {quote ? quoteFormat.format(quote.ltp) : '—'}
              </span>
              {quote?.changePercent != null ? (
                <span className={changeClass}>{formatChange(quote.changePercent)}</span>
              ) : null}
            </span>
          </span>
        );
      })}
    </>
  );
}
