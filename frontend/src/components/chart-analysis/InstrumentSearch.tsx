'use client';
import { useState, useEffect } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { useInstrumentSearch } from '@/hooks/useInstrumentSearch';

// Fixed 7-derivative selector — no dynamic discovery outside these 7
const FIXED_INSTRUMENTS: Array<{ symbol: string; display_name: string; note: string }> = [
  { symbol: 'NIFTY', display_name: 'NIFTY 50', note: 'INDEX • NSE' },
  { symbol: 'BANKNIFTY', display_name: 'NIFTY Bank', note: 'INDEX • NSE' },
  { symbol: 'FINNIFTY', display_name: 'NIFTY Financial Services', note: 'INDEX • NSE' },
  { symbol: 'SENSEX', display_name: 'BSE SENSEX', note: 'INDEX • BSE' },
  { symbol: 'BTC', display_name: 'Bitcoin', note: 'CRYPTO • BINANCE' },
  { symbol: 'ETH', display_name: 'Ethereum', note: 'CRYPTO • BINANCE' },
  { symbol: 'SOL', display_name: 'Solana', note: 'CRYPTO • BINANCE' },
];

interface Props {
  onSelect: (symbol: string) => void;
  initialQuery?: string;
}

export function InstrumentSearch({ onSelect, initialQuery = '' }: Props) {
  const { results, loading, search } = useInstrumentSearch();
  const [input, setInput] = useState(initialQuery);
  const [show, setShow] = useState(false);
  const [showFixed, setShowFixed] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      if (input.trim().length > 0) {
        search(input);
        setShow(true);
      } else {
        setShow(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [input, search]);

  const q = input.trim().toLowerCase();
  const filteredFixed = FIXED_INSTRUMENTS.filter(
    (f) => !q || f.symbol.toLowerCase().includes(q) || f.display_name.toLowerCase().includes(q)
  );

  return (
    <div className="relative w-full">
      <div className="flex items-center gap-2 border border-border rounded-lg bg-card px-3 py-2">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => { if (input.trim()) setShow(true); setShowFixed(true); }}
          onBlur={() => setTimeout(() => setShowFixed(false), 200)}
          placeholder="Select instrument — NIFTY, BANKNIFTY, FINNIFTY, SENSEX, BTC, ETH, SOL"
          className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
        />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
        <button
          type="button"
          onMouseDown={(e) => { e.preventDefault(); setShowFixed((s) => !s); }}
          className="text-xs px-2 py-1 border rounded bg-muted hover:bg-accent"
          title="Show fixed 7 instruments"
        >
          ▾ 7
        </button>
      </div>

      {/* Fixed 7-instrument selector — always authoritative */}
      {showFixed && (
        <div className="absolute z-30 mt-2 w-full bg-card border border-border rounded-lg shadow-lg max-h-72 overflow-auto">
          <div className="px-3 py-2 text-xs font-semibold text-muted-foreground border-b">Approved derivatives (7 fixed) — no other instruments</div>
          {filteredFixed.map((r) => (
            <button
              key={r.symbol}
              onMouseDown={(e) => { e.preventDefault(); onSelect(r.symbol); setInput(r.symbol); setShowFixed(false); setShow(false); }}
              className="w-full text-left px-4 py-2 hover:bg-accent flex flex-col gap-0.5"
            >
              <span className="text-sm font-medium">{r.symbol} — {r.display_name}</span>
              <span className="text-xs text-muted-foreground">{r.note}</span>
            </button>
          ))}
          {filteredFixed.length === 0 && (
            <div className="px-4 py-3 text-sm text-muted-foreground">No match in the 7 approved derivatives. Allowed: NIFTY, BANKNIFTY, FINNIFTY, SENSEX, BTC, ETH, SOL.</div>
          )}
        </div>
      )}

      {/* Search results (restricted registry is also 7 only, so this is redundant but kept for UX) */}
      {show && results.length > 0 && !showFixed && (
        <div className="absolute z-20 mt-2 w-full bg-card border border-border rounded-lg shadow-lg max-h-72 overflow-auto">
          {results.map((r) => (
            <button
              key={r.symbol}
              onClick={() => { onSelect(r.symbol); setInput(r.symbol); setShow(false); }}
              className="w-full text-left px-4 py-2 hover:bg-accent flex flex-col gap-0.5"
            >
              <span className="text-sm font-medium">{r.symbol} — {r.display_name}</span>
              <span className="text-xs text-muted-foreground">{r.asset_class} • {r.exchange} • {r.instrument_type} {r.fno_available ? '• F&O' : ''}</span>
            </button>
          ))}
        </div>
      )}
      {show && !loading && results.length === 0 && input.trim().length > 0 && !showFixed && (
        <div className="absolute z-20 mt-2 w-full bg-card border border-border rounded-lg shadow p-4 text-sm text-muted-foreground">
          &quot;{input}&quot; is not part of the 7 approved derivatives. Select: NIFTY, BANKNIFTY, FINNIFTY, SENSEX, BTC, ETH, SOL. If data is unavailable, you will see &quot;Data unavailable&quot; — no substitution.
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-1">Chart Analysis universe (fixed 7): NIFTY • BANKNIFTY • FINNIFTY • SENSEX • BTC • ETH • SOL — No other instruments. Timeframes: 1m • 5m • 15m • 1h • 4h • 1D</p>
    </div>
  );
}
