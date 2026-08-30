'use client';
import { useState, useCallback } from 'react';
import { api } from '@/lib/api';

export interface InstrumentSearchResult {
  display_name: string;
  symbol: string;
  asset_class: string;
  exchange: string;
  instrument_type: string;
  fno_available: boolean;
  supported_timeframes: string[];
  data_provider_symbol?: string;
  current_status: string;
}

export function useInstrumentSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<InstrumentSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (q: string, filters?: { asset_class?: string; fno_only?: boolean }) => {
    const trimmed = q.trim();
    setQuery(q);
    if (!trimmed) {
      setResults([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ q: trimmed });
      if (filters?.asset_class) params.set('asset_class', filters.asset_class);
      if (filters?.fno_only) params.set('fno_only', 'true');
      const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
      const res = await fetch(`${base}/api/v1/instruments/search?${params.toString()}`);
      const json = await res.json();
      const data = json.data?.results ?? json.results ?? [];
      setResults(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return { query, setQuery, results, loading, error, search };
}
