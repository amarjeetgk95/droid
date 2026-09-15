'use client';

import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import type { OptionChainResponse, OptionChainStrikeRow } from '@/lib/types';
import { fmtNum } from '@/components/ui/desk';
import { X, RefreshCw, ExternalLink } from 'lucide-react';

interface OptionsChainDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  instrument: string;
}

export const OptionsChainDrawer = memo(function OptionsChainDrawer({
  isOpen,
  onClose,
  instrument,
}: OptionsChainDrawerProps) {
  const [chain, setChain] = useState<OptionChainResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedExpiry, setSelectedExpiry] = useState<string>('');
  const requestIdRef = useRef(0);

  const loadChain = useCallback(
    async (expiryOverride?: string) => {
      if (!instrument) return;
      const requestId = ++requestIdRef.current;
      // '' must become undefined so api omits ?expiry= (api encodes when present)
      const expiryParam = expiryOverride ? expiryOverride : undefined;
      setLoading(true);
      try {
        const res = await api.getOptionChain(instrument, expiryParam);
        // Guard race: ignore late response from old instrument/expiry
        if (requestIdRef.current !== requestId) return;
        if (res?.data) {
          setChain(res.data);
          // Only adopt server expiry on default load (no explicit override)
          if (expiryOverride === undefined && res.data.expiry) {
            setSelectedExpiry((prev) => prev || res.data.expiry);
          }
        }
      } catch (e) {
        console.error('Failed to load option chain', e);
      } finally {
        if (requestIdRef.current === requestId) setLoading(false);
      }
    },
    [instrument],
  );

  // Reset stale expiry when instrument changes; don't reuse old instrument's expiry.
  useEffect(() => {
    setSelectedExpiry('');
  }, [instrument]);

  // Open / instrument change: clear stale chain and load default expiry (single fetch).
  useEffect(() => {
    if (!isOpen || !instrument) return;
    setChain(null);
    void loadChain();
  }, [isOpen, instrument, loadChain]);

  // Handle ESC key to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const analytics = chain?.analytics;
  const strikes: OptionChainStrikeRow[] = chain?.strikes ?? [];
  const spotPrice = chain?.spot_price ?? analytics?.spot_price ?? 0;

  // Filter ~15 strikes centered around ATM for instant glance without lag
  const atmIndex = strikes.findIndex((s) => s.is_atm);
  const startIndex = atmIndex >= 0 ? Math.max(0, atmIndex - 8) : 0;
  const visibleStrikes = strikes.slice(startIndex, startIndex + 17);

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40 backdrop-blur-2xs transition-opacity animate-in fade-in">
      <div className="w-full max-w-4xl h-full bg-white border-l border-slate-300 flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="p-3.5 border-b border-slate-200 flex items-center justify-between gap-3 bg-slate-50">
          <div className="flex items-center gap-2.5">
            <h2 className="text-sm font-bold tracking-tight uppercase text-slate-900">OPTIONS CHAIN & DERIVATIVES MATRIX</h2>
            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
              {instrument}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Expiry selector */}
            {chain?.expiries && chain.expiries.length > 0 && (
              <select
                aria-label="Select Expiry"
                value={selectedExpiry}
                onChange={(e) => {
                  const next = e.target.value;
                  setSelectedExpiry(next);
                  void loadChain(next);
                }}
                className="text-xs font-mono py-1 px-2.5 rounded border border-slate-300 bg-white text-slate-900 font-semibold cursor-pointer shadow-2xs"
              >
                {chain.expiries.map((exp) => (
                  <option key={exp} value={exp}>
                    {exp}
                  </option>
                ))}
              </select>
            )}

            <button
              type="button"
              onClick={() => void loadChain(selectedExpiry)}
              disabled={loading}
              title="Refresh Options Chain"
              className="p-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>

            <button
              type="button"
              onClick={onClose}
              title="Close (Esc)"
              className="p-1.5 rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 shadow-2xs cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Key Metrics Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 p-3.5 border-b border-slate-200 bg-slate-50/60 font-mono text-xs">
          <div className="p-2.5 rounded-md bg-white border border-slate-200 shadow-2xs">
            <span className="text-[10px] text-slate-500 block font-sans font-bold uppercase">Spot Price</span>
            <span className="font-bold text-sm text-slate-900">{spotPrice ? fmtNum(spotPrice, 1) : '—'}</span>
          </div>
          <div className="p-2.5 rounded-md bg-white border border-slate-200 shadow-2xs">
            <span className="text-[10px] text-slate-500 block font-sans font-bold uppercase">Max Pain Strike</span>
            <span className="font-bold text-sm text-blue-700">
              {analytics?.max_pain_strike ? Math.round(analytics.max_pain_strike) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-white border border-slate-200 shadow-2xs">
            <span className="text-[10px] text-slate-500 block font-sans font-bold uppercase">PCR (OI)</span>
            <span
              className={`font-bold text-sm ${
                (analytics?.pcr_oi ?? 1) >= 1 ? 'text-emerald-700' : 'text-rose-700'
              }`}
            >
              {analytics?.pcr_oi ? fmtNum(analytics.pcr_oi, 2) : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-white border border-slate-200 shadow-2xs">
            <span className="text-[10px] text-slate-500 block font-sans font-bold uppercase">ATM Implied Vol (IV)</span>
            <span className="font-bold text-sm text-slate-900">
              {analytics?.atm_iv ? `${fmtNum(analytics.atm_iv * 100, 1)}%` : '—'}
            </span>
          </div>
          <div className="p-2.5 rounded-md bg-white border border-slate-200 shadow-2xs col-span-2 sm:col-span-1">
            <span className="text-[10px] text-slate-500 block font-sans font-bold uppercase">Total CE / PE OI</span>
            <span className="font-bold text-xs text-slate-900">
              {analytics?.total_call_oi ? `${Math.round(analytics.total_call_oi / 100000)}L / ` : ''}
              {analytics?.total_put_oi ? `${Math.round(analytics.total_put_oi / 100000)}L` : '—'}
            </span>
          </div>
        </div>

        {/* Table Matrix */}
        <div className="flex-1 overflow-y-auto p-2">
          {loading && !chain ? (
            <div className="space-y-2 p-2" aria-label="Loading options chain">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-8 rounded bg-slate-100 animate-pulse" />
              ))}
            </div>
          ) : strikes.length === 0 ? (
            <div className="flex h-full items-center justify-center p-8 text-center text-sm text-slate-500">
              No options data available for {instrument}
              {selectedExpiry ? ` (${selectedExpiry})` : ''}. Try another expiry or refresh.
            </div>
          ) : (
          <table className="w-full text-xs font-mono border-collapse">
            <thead className="sticky top-0 bg-white shadow-xs z-10 text-[11px]">
              <tr className="border-b border-slate-200">
                <th colSpan={4} className="py-1.5 px-2 text-center text-emerald-800 bg-emerald-50 font-bold uppercase border-r border-slate-200">
                  CALLS (CE)
                </th>
                <th className="py-1.5 px-3 text-center text-slate-900 bg-slate-100 font-black uppercase border-r border-slate-200">
                  STRIKE
                </th>
                <th colSpan={4} className="py-1.5 px-2 text-center text-rose-800 bg-rose-50 font-bold uppercase">
                  PUTS (PE)
                </th>
              </tr>
              <tr className="border-b border-slate-200 text-[10px] text-slate-600 uppercase bg-slate-50">
                <th className="py-1 px-2 text-right">OI</th>
                <th className="py-1 px-2 text-right">Chg OI</th>
                <th className="py-1 px-2 text-right">IV%</th>
                <th className="py-1 px-2 text-right border-r border-slate-200 font-bold">LTP</th>
                <th className="py-1 px-3 text-center text-slate-900 font-black border-r border-slate-200">ATM</th>
                <th className="py-1 px-2 text-left font-bold">LTP</th>
                <th className="py-1 px-2 text-left">IV%</th>
                <th className="py-1 px-2 text-left">Chg OI</th>
                <th className="py-1 px-2 text-left">OI</th>
              </tr>
            </thead>
            <tbody>
              {visibleStrikes.map((row) => {
                const call = row.call;
                const put = row.put;
                const isAtm = row.is_atm;

                return (
                  <tr
                    key={row.strike}
                    className={`border-b border-slate-100 hover:bg-slate-50 transition-colors ${
                      isAtm ? 'bg-amber-50 font-bold' : ''
                    }`}
                  >
                    {/* CE Side */}
                    <td className="py-1.5 px-2 text-right text-slate-600">
                      {call?.open_interest ? `${Math.round(call.open_interest / 1000)}k` : '—'}
                    </td>
                    <td
                      className={`py-1.5 px-2 text-right font-bold ${
                        (call?.oi_change ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'
                      }`}
                    >
                      {call?.oi_change ? `${(call.oi_change > 0 ? '+' : '')}${Math.round(call.oi_change / 1000)}k` : '—'}
                    </td>
                    <td className="py-1.5 px-2 text-right text-slate-500">
                      {call?.greeks?.iv ? `${fmtNum(call.greeks.iv * 100, 1)}%` : '—'}
                    </td>
                    <td className="py-1.5 px-2 text-right font-bold text-slate-900 border-r border-slate-200">
                      {call?.ltp ? fmtNum(call.ltp, 1) : '—'}
                    </td>

                    {/* Strike */}
                    <td
                      className={`py-1.5 px-3 text-center font-bold border-r border-slate-200 ${
                        isAtm
                          ? 'text-amber-950 bg-amber-200 font-black'
                          : 'text-slate-900 bg-slate-50'
                      }`}
                    >
                      {Math.round(row.strike)}
                    </td>

                    {/* PE Side */}
                    <td className="py-1.5 px-2 text-left font-bold text-slate-900">
                      {put?.ltp ? fmtNum(put.ltp, 1) : '—'}
                    </td>
                    <td className="py-1.5 px-2 text-left text-slate-500">
                      {put?.greeks?.iv ? `${fmtNum(put.greeks.iv * 100, 1)}%` : '—'}
                    </td>
                    <td
                      className={`py-1.5 px-2 text-left font-bold ${
                        (put?.oi_change ?? 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'
                      }`}
                    >
                      {put?.oi_change ? `${(put.oi_change > 0 ? '+' : '')}${Math.round(put.oi_change / 1000)}k` : '—'}
                    </td>
                    <td className="py-1.5 px-2 text-left text-slate-600">
                      {put?.open_interest ? `${Math.round(put.open_interest / 1000)}k` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between text-xs text-slate-500 font-mono">
          <span>Press ESC or click close to return to War Room</span>
          <a
            href="/options"
            className="flex items-center gap-1 text-blue-700 font-semibold hover:underline"
          >
            <span>Full Options Desk</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        </div>
      </div>
    </div>
  );
});
