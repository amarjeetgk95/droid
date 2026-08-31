'use client';

import * as React from 'react';
import { Plus, X, Star } from 'lucide-react';
import { api } from '@/lib/api';
import type { WatchlistItem } from '@/lib/types';
import { Panel } from './Panel';
import { EmptyState } from './EmptyState';
import { Skeleton } from './Skeleton';
import { useToast } from '@/lib/historical-intelligence/toast';

export function HiWatchlist() {
  const [items, setItems] = React.useState<WatchlistItem[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [adding, setAdding] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const { toast } = useToast();

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.getWatchlist();
      setItems(res.data);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, [load]);

  const add = async () => {
    const sym = adding.trim().toUpperCase();
    if (!sym) return;
    setBusy(true);
    try {
      await api.addToWatchlist(sym);
      setAdding('');
      toast({ tone: 'ok', title: `${sym} added` });
      await load();
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not add', description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (sym: string) => {
    setBusy(true);
    try {
      await api.removeFromWatchlist(sym);
      toast({ tone: 'info', title: `${sym} removed` });
      await load();
    } catch (err) {
      toast({ tone: 'danger', title: 'Could not remove', description: err instanceof Error ? err.message : 'Unknown error' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel
      title="Watchlist"
      description={`${items.length} symbols`}
      actions={
        <div className="flex gap-2">
          <input
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') add(); }}
            placeholder="Add symbol (e.g. NIFTY)"
            className="px-2 py-1.5 rounded-md border border-border bg-background text-xs w-44"
          />
          <button onClick={add} disabled={busy || !adding.trim()} className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-xs font-semibold disabled:opacity-50">
            <Plus className="w-3.5 h-3.5" /> Add
          </button>
        </div>
      }
    >
      {loading && items.length === 0 ? (
        <Skeleton className="h-32 w-full" />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Star className="w-6 h-6" />}
          title="No symbols tracked"
          action={<button onClick={add} className="text-primary text-xs hover:underline">Add NIFTY</button>}
        />
      ) : (
        <ul className="space-y-1">
          {items.map((w) => (
            <li key={w.symbol} className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-2 text-xs">
              <Star className="w-3.5 h-3.5 text-amber-500" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{w.display_name || w.symbol}</p>
                <p className="text-[10px] text-muted-foreground">
                  {w.symbol} · LTP {w.ltp.toFixed(2)} · {w.change_percent >= 0 ? '+' : ''}{w.change_percent.toFixed(2)}%
                  {w.active_pattern && ` · ${w.active_pattern}`}
                  {w.regime_state && ` · ${w.regime_state}`}
                </p>
              </div>
              <button
                onClick={() => remove(w.symbol)}
                disabled={busy}
                aria-label={`Remove ${w.symbol}`}
                className="p-1 rounded hover:bg-red-500/10 hover:text-red-500"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}