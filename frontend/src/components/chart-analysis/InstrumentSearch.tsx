'use client';
import { useState, useEffect } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { useInstrumentSearch } from '@/hooks/useInstrumentSearch';

interface Props {
  onSelect: (symbol: string) => void;
  initialQuery?: string;
}

export function InstrumentSearch({ onSelect, initialQuery = '' }: Props) {
  const { results, loading, search } = useInstrumentSearch();
  const [input, setInput] = useState(initialQuery);
  const [show, setShow] = useState(false);

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

  return (
    <div className="relative w-full">
      <div className="flex items-center gap-2 border border-border rounded-lg bg-card px-3 py-2">
        <Search className="w-4 h-4 text-muted-foreground" />
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => input.trim() && setShow(true)}
          placeholder="Search instrument — e.g. BANKNIFTY, SENSEX, BITCOIN, NIFTY"
          className="flex-1 bg-transparent outline-none text-sm placeholder:text-muted-foreground"
        />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />}
      </div>
      {show && results.length > 0 && (
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
      {show && !loading && results.length === 0 && input.trim().length > 0 && (
        <div className="absolute z-20 mt-2 w-full bg-card border border-border rounded-lg shadow p-4 text-sm text-muted-foreground">
          No supported instrument found for “{input}”. Try BANKNIFTY, SENSEX, BITCOIN, NIFTY, or another configured symbol.
        </div>
      )}
      <p className="text-xs text-muted-foreground mt-1">Suggestions: BANKNIFTY, SENSEX, BITCOIN, NIFTY, RELIANCE, BTCUSDT</p>
    </div>
  );
}
