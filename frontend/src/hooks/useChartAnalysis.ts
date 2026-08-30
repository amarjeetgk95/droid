'use client';
import { useState, useCallback } from 'react';

export function useChartAnalysis() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalysis = useCallback(async (symbol: string, timeframe?: string) => {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    try {
      const base = (process.env.NEXT_PUBLIC_API_URL || 'https://droid-backend-emeq.onrender.com').replace(/\/+$/, '');
      const tfQuery = timeframe ? `?timeframe=${timeframe}` : '';
      const res = await fetch(`${base}/api/v1/chart-analysis/${encodeURIComponent(symbol)}${tfQuery}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `Failed to fetch analysis`);
      }
      const json = await res.json();
      setData(json.data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, fetchAnalysis };
}
