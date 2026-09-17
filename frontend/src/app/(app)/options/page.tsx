'use client';

import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { MaxPainResult, OptionChainResponse } from '@/lib/types';
import { OptionsHeader } from '@/components/options/OptionsHeader';
import { OptionChainTable } from '@/components/options/OptionChainTable';
import { IVSmileChart } from '@/components/options/IVSmileChart';
import { PayoffChart } from '@/components/options/PayoffChart';
import { ExpectedMoveCard, type ExpectedMoveData } from '@/components/options/ExpectedMoveCard';
import { InstitutionalFlowTracker } from '@/components/options/InstitutionalFlowTracker';
import { OptionChainSkeleton } from '@/components/options/OptionChainSkeleton';
import { ErrorCard } from '@/components/ui/ErrorCard';
import { useMarketSession } from '@/hooks/useMarketSession';

type ViewMode = 'standard' | 'greeks';
type ForecastDirection = 'BULLISH' | 'BEARISH';

/** Intelligence endpoints may return the model directly or wrapped in {data,meta}. */
function unwrapModel<T>(raw: unknown): T {
  if (raw && typeof raw === 'object' && 'data' in raw && 'meta' in raw) {
    return (raw as { data: T }).data;
  }
  return raw as T;
}

export default function OptionsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState('NIFTY');
  const [selectedExpiry, setSelectedExpiry] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('standard');
  const [forecastDirection, setForecastDirection] = useState<ForecastDirection>('BULLISH');

  const [chainData, setChainData] = useState<OptionChainResponse | null>(null);
  const [chainAsOf, setChainAsOf] = useState<string | null>(null);
  const [chainKey, setChainKey] = useState<string | null>(null);
  const [maxPainData, setMaxPainData] = useState<MaxPainResult | null>(null);
  const [expectedMove, setExpectedMove] = useState<ExpectedMoveData | null>(null);
  const [expectedMoveLoading, setExpectedMoveLoading] = useState(false);
  const [expectedMoveError, setExpectedMoveError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const { isOpen } = useMarketSession();
  const marketClosed = !isOpen;

  useEffect(() => {
    let active = true;
    setLoading(true);

    const run = async () => {
      try {
        const [chainRes, mpRes] = await Promise.all([
          api.getOptionChain(selectedSymbol, selectedExpiry || undefined),
          api.getMaxPain(selectedSymbol, selectedExpiry || undefined),
        ]);
        if (!active) return;
        setChainData(chainRes.data);
        setMaxPainData(mpRes.data);
        setChainAsOf(chainRes.meta?.timestamp ?? null);
        setChainKey(`${selectedSymbol}|${chainRes.data?.expiry ?? selectedExpiry}`);
        // The ladder's date is whatever the broker actually priced; adopt it so
        // the selector, freshness badge and forecast all reference one expiry.
        if (chainRes.data?.expiry && chainRes.data.expiry !== selectedExpiry) {
          setSelectedExpiry(chainRes.data.expiry);
        }
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to fetch options data');
      } finally {
        if (active) setLoading(false);
      }
    };

    void run();
    return () => {
      active = false;
    };
  }, [selectedSymbol, selectedExpiry, reloadToken]);

  const spotPrice = chainData?.spot_price ?? 0;
  const atmIv = chainData?.analytics?.atm_iv ?? null;
  // `current_iv` is a FRACTION in the API (0.15 = 15%); `atm_iv` arrives as a
  // percent (15.0), so convert before projecting.
  const currentIv = typeof atmIv === 'number' && atmIv > 0 ? atmIv / 100 : null;
  const chainAligned = chainKey === `${selectedSymbol}|${selectedExpiry}`;

  useEffect(() => {
    let active = true;

    if (!chainAligned || spotPrice <= 0 || currentIv === null) {
      setExpectedMove(null);
      setExpectedMoveError(null);
      setExpectedMoveLoading(false);
      return () => {
        active = false;
      };
    }

    setExpectedMoveLoading(true);
    const run = async () => {
      try {
        const res = await api.projectExpectedMove({
          underlying: selectedSymbol,
          spot: spotPrice,
          direction: forecastDirection,
          horizon: 'INTRADAY',
          current_iv: currentIv,
        });
        if (!active) return;
        setExpectedMove(unwrapModel<ExpectedMoveData>(res));
        setExpectedMoveError(null);
      } catch (err) {
        if (!active) return;
        setExpectedMove(null);
        setExpectedMoveError(err instanceof Error ? err.message : 'Expected move projection unavailable');
      } finally {
        if (active) setExpectedMoveLoading(false);
      }
    };

    void run();
    return () => {
      active = false;
    };
  }, [selectedSymbol, chainAligned, spotPrice, currentIv, forecastDirection]);

  const { callWall, putWall } = useMemo(() => {
    let cw: number | null = null;
    let pw: number | null = null;
    let maxCallOi = 0;
    let maxPutOi = 0;
    for (const row of chainData?.strikes ?? []) {
      const cOi = row.call?.open_interest ?? 0;
      const pOi = row.put?.open_interest ?? 0;
      if (cOi > maxCallOi) {
        maxCallOi = cOi;
        cw = row.strike;
      }
      if (pOi > maxPutOi) {
        maxPutOi = pOi;
        pw = row.strike;
      }
    }
    return { callWall: cw, putWall: pw };
  }, [chainData]);

  const hasChain = chainData !== null;

  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>Derivatives — Options</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>{selectedSymbol}</span>
            </div>
            <p className="num">
              {selectedExpiry || chainData?.expiry
                ? `Expiry ${selectedExpiry || chainData?.expiry}`
                : 'Loading chain…'}{' '}
              · chain, max pain, IV smile &amp; 1h expected move
            </p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Expected move direction">
            {(['BULLISH', 'BEARISH'] as const).map((dir) => (
              <button
                key={dir}
                type="button"
                className="seg-btn"
                data-active={forecastDirection === dir}
                aria-pressed={forecastDirection === dir}
                onClick={() => setForecastDirection(dir)}
              >
                {dir === 'BULLISH' ? 'Call · Bullish' : 'Put · Bearish'}
              </button>
            ))}
          </div>
        </div>
      </header>

      <OptionsHeader
        analytics={chainData?.analytics ?? null}
        selectedSymbol={selectedSymbol}
        onSelectSymbol={(sym) => {
          setSelectedSymbol(sym);
          setSelectedExpiry('');
        }}
        selectedExpiry={selectedExpiry || chainData?.expiry || ''}
        expiries={chainData?.expiries ?? []}
        onSelectExpiry={(exp) => setSelectedExpiry(exp)}
        viewMode={viewMode}
        onToggleViewMode={setViewMode}
        callWall={callWall}
        putWall={putWall}
      />

      {error ? (
        <ErrorCard
          title="Error loading option chain"
          message={error}
          mode="full-page"
          onRetry={() => {
            setError(null);
            setReloadToken((v) => v + 1);
          }}
          isRetrying={loading}
        />
      ) : loading && !hasChain ? (
        <OptionChainSkeleton rows={12} />
      ) : (
        <>
          <OptionChainTable
            strikes={chainData?.strikes ?? []}
            viewMode={viewMode}
            spotPrice={spotPrice}
            asOf={chainAsOf}
            marketClosed={marketClosed}
            fetching={loading}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <PayoffChart data={maxPainData} spotPrice={spotPrice} />
            <IVSmileChart
              strikes={chainData?.strikes ?? []}
              atmStrike={chainData?.analytics?.atm_strike ?? 0}
            />
          </div>

          <ExpectedMoveCard
            data={expectedMove}
            loading={expectedMoveLoading || (loading && !chainAligned)}
            error={expectedMoveError}
          />

          <InstitutionalFlowTracker
            symbol={selectedSymbol}
            expiry={selectedExpiry || chainData?.expiry || undefined}
            marketClosed={marketClosed}
          />
        </>
      )}
    </div>
  );
}
