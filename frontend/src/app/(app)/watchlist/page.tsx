'use client';

import { useState, useEffect, useCallback } from 'react';
import { api } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import {
  WatchlistResponse,
  WatchlistItemResponse,
} from '@/lib/types';
import { Bookmark, Plus, Trash2, TrendingUp, TrendingDown, RefreshCw, ChevronDown, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function WatchlistPage() {
  const { isDemoMode } = useAuth();
  const [watchlists, setWatchlists] = useState<WatchlistResponse[]>([]);
  const [selectedWatchlist, setSelectedWatchlist] = useState<WatchlistResponse | null>(null);
  const [items, setItems] = useState<WatchlistItemResponse[]>([]);
  const [newSymbol, setNewSymbol] = useState('');
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showWatchlistDropdown, setShowWatchlistDropdown] = useState(false);

  const loadWatchlists = useCallback(async () => {
    try {
      if (isDemoMode) {
        const demoWl = { id: 'demo', user_id: 'dev-user', name: 'My F&O', created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
        setWatchlists([demoWl]);
        setSelectedWatchlist(demoWl);
        setItems([
          { id: '1', watchlist_id: 'demo', instrument_id: null, symbol: 'NIFTY', display_order: 0, created_at: new Date().toISOString() },
          { id: '2', watchlist_id: 'demo', instrument_id: null, symbol: 'BANKNIFTY', display_order: 1, created_at: new Date().toISOString() },
          { id: '3', watchlist_id: 'demo', instrument_id: null, symbol: 'FINNIFTY', display_order: 2, created_at: new Date().toISOString() },
        ]);
        return;
      }
      const wls = await api.listWatchlists();
      setWatchlists(wls);
      if (wls.length > 0) {
        setSelectedWatchlist(wls[0]);
      } else {
        // Create default watchlist
        const created = await api.createWatchlist('My F&O');
        setWatchlists([created]);
        setSelectedWatchlist(created);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load watchlists');
    }
  }, [isDemoMode]);

  const loadItems = useCallback(async (watchlistId: string) => {
    try {
      if (isDemoMode) return;
      const data = await api.listWatchlistItems(watchlistId);
      setItems(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load watchlist items');
    }
  }, [isDemoMode]);

  useEffect(() => {
    loadWatchlists().finally(() => setLoading(false));
  }, [loadWatchlists]);

  useEffect(() => {
    if (selectedWatchlist) {
      loadItems(selectedWatchlist.id);
    }
  }, [selectedWatchlist, loadItems]);

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim() || !selectedWatchlist) return;
    try {
      setSaving(true);
      setError(null);
      if (isDemoMode) {
        setItems(prev => [...prev, {
          id: `demo-${Date.now()}`,
          watchlist_id: selectedWatchlist.id,
          instrument_id: null,
          symbol: newSymbol.trim().toUpperCase(),
          display_order: prev.length,
          created_at: new Date().toISOString(),
        }]);
      } else {
        await api.addWatchlistItem(selectedWatchlist.id, newSymbol.trim());
        await loadItems(selectedWatchlist.id);
      }
      setNewSymbol('');
      setSuccess(`Added ${newSymbol.trim().toUpperCase()}`);
      setTimeout(() => setSuccess(null), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add item');
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveItem = async (itemId: string, symbol: string) => {
    try {
      setError(null);
      if (isDemoMode) {
        setItems(prev => prev.filter(i => i.id !== itemId));
      } else {
        await api.removeWatchlistItem(selectedWatchlist!.id, itemId);
        await loadItems(selectedWatchlist!.id);
      }
      setSuccess(`Removed ${symbol}`);
      setTimeout(() => setSuccess(null), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove item');
    }
  };

  const handleCreateWatchlist = async () => {
    if (!newWatchlistName.trim()) return;
    try {
      setSaving(true);
      setError(null);
      if (isDemoMode) {
        const newWl = {
          id: `demo-${Date.now()}`,
          user_id: 'dev-user',
          name: newWatchlistName.trim(),
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setWatchlists(prev => [...prev, newWl]);
        setSelectedWatchlist(newWl);
      } else {
        const created = await api.createWatchlist(newWatchlistName.trim());
        setWatchlists(prev => [...prev, created]);
        setSelectedWatchlist(created);
      }
      setNewWatchlistName('');
      setShowWatchlistDropdown(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create watchlist');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteWatchlist = async () => {
    if (!selectedWatchlist || watchlists.length <= 1) return;
    if (!confirm(`Delete watchlist "${selectedWatchlist.name}"?`)) return;
    try {
      setError(null);
      if (!isDemoMode) {
        await api.deleteWatchlist(selectedWatchlist.id);
      }
      const remaining = watchlists.filter(w => w.id !== selectedWatchlist.id);
      setWatchlists(remaining);
      setSelectedWatchlist(remaining[0] || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete watchlist');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-card border border-border rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="flex items-center gap-3">
          <div className="bg-primary/10 p-2 rounded-lg">
            <Bookmark className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground">Watchlists</h2>
            <p className="text-xs text-muted-foreground">
              Manage your instrument watchlists
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {error && (
            <span className="text-xs text-destructive flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5" />
              <span>{error}</span>
            </span>
          )}
          {success && (
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{success}</span>
            </span>
          )}
        </div>
      </div>

      {isDemoMode && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-4 text-amber-400 text-xs">
          <strong>Demo Mode:</strong> Watchlist changes are not persisted. Connect Supabase to enable persistence.
        </div>
      )}

      {/* Watchlist Selector */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                onClick={() => setShowWatchlistDropdown(!showWatchlistDropdown)}
                className="flex items-center gap-2 bg-secondary/50 border border-border rounded-lg px-3 py-2 text-xs font-semibold text-foreground hover:bg-secondary transition-colors cursor-pointer"
              >
                <span>{selectedWatchlist?.name || 'Select Watchlist'}</span>
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
              {showWatchlistDropdown && (
                <div className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-[180px]">
                  {watchlists.map(wl => (
                    <button
                      key={wl.id}
                      onClick={() => { setSelectedWatchlist(wl); setShowWatchlistDropdown(false); }}
                      className={`w-full text-left px-3 py-2 text-xs hover:bg-secondary/50 transition-colors ${selectedWatchlist?.id === wl.id ? 'bg-primary/10 text-primary font-semibold' : 'text-foreground'}`}
                    >
                      {wl.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {watchlists.length > 1 && selectedWatchlist && (
              <button
                onClick={handleDeleteWatchlist}
                className="text-xs text-destructive hover:text-destructive/80 cursor-pointer"
              >
                Delete
              </button>
            )}
          </div>

          {/* Add Symbol Form */}
          <form onSubmit={handleAddItem} className="flex items-center gap-1.5">
            <input
              type="text"
              placeholder="Add symbol e.g. RELIANCE"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              className="bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground focus:outline-hidden w-40 uppercase font-semibold"
            />
            <button
              type="submit"
              disabled={saving}
              className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg transition-all cursor-pointer disabled:opacity-50"
              title="Add Symbol"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </form>
        </div>

        {/* Create New Watchlist */}
        <div className="flex items-center gap-1.5 pt-2 border-t border-border">
          <input
            type="text"
            placeholder="New watchlist name"
            value={newWatchlistName}
            onChange={(e) => setNewWatchlistName(e.target.value)}
            className="bg-secondary text-xs px-2.5 py-1.5 rounded-lg border border-border text-foreground focus:outline-hidden w-40 font-semibold"
          />
          <button
            onClick={handleCreateWatchlist}
            disabled={saving || !newWatchlistName.trim()}
            className="px-2.5 py-1.5 bg-secondary hover:bg-secondary/80 text-foreground rounded-lg text-xs font-semibold transition-all cursor-pointer border border-border disabled:opacity-50"
          >
            Create Watchlist
          </button>
        </div>
      </div>

      {/* Watchlist Items Table */}
      <div className="bg-card border border-border rounded-xl p-4 shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse">
            <thead>
              <tr className="border-b border-border text-muted-foreground font-semibold">
                <th className="py-2 px-2">#</th>
                <th className="py-2 px-2">Symbol</th>
                <th className="py-2 px-2 text-right">Display Order</th>
                <th className="py-2 px-2 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40 font-mono">
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-muted-foreground">
                    No items in this watchlist. Add symbols above.
                  </td>
                </tr>
              ) : (
                items.map((item, idx) => (
                  <tr key={item.id} className="hover:bg-accent/40 transition-colors">
                    <td className="py-2.5 px-2 text-muted-foreground">{idx + 1}</td>
                    <td className="py-2.5 px-2 font-sans font-bold text-foreground">
                      {item.symbol}
                    </td>
                    <td className="py-2.5 px-2 text-right text-muted-foreground">
                      {item.display_order}
                    </td>
                    <td className="py-2.5 px-2 text-center">
                      <button
                        onClick={() => handleRemoveItem(item.id, item.symbol)}
                        className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors cursor-pointer"
                        title="Remove from Watchlist"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
