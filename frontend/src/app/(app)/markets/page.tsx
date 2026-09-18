'use client';

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { ApiMeta, MarketRegimeOverview } from '@/lib/types';
import { usePolling } from '@/hooks/usePolling';
import { useMarketSession } from '@/hooks/useMarketSession';
import { useOptionalMarketDataContext } from '@/context/MarketDataContext';
import { regimeFromSummary } from '@/lib/regime';
import {
  RegimeBanner,
  type RegimeBannerStatus,
} from '@/components/markets/RegimeBanner';
import { KeyLevelsTable } from '@/components/markets/KeyLevelsTable';
import { IndicatorsGrid } from '@/components/markets/IndicatorsGrid';
import { VixRegimeCard } from '@/components/markets/VixRegimeCard';
import { MarketSessionBanner } from '@/components/markets/MarketSessionBanner';
import { isStale, isUsableRegimeOverview, provenanceLabel, symbolsMatch } from '@/components/markets/truthful';

const SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX'] as const;
type SymbolId = (typeof SYMBOLS)[number];

const POLL_MS = 15_000;

export default function MarketsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolId>('NIFTY');

  return (
    <div className="ds-page">
      <header className="page-hero">
        <div className="toolbar">
          <div>
            <div className="flex items-center gap-2.5">
              <h1>Market Context</h1>
              <span className="badge b-info" style={{ fontSize: 11 }}>{selectedSymbol}</span>
            </div>
            <p className="num">
              Regime diagnosis · pivot ladder · technical indicators · India VIX
            </p>
          </div>
          <span className="spacer" />
          <div className="seg" role="group" aria-label="Underlying">
            {SYMBOLS.map((sym) => (
              <button
                key={sym}
                type="button"
                className="seg-btn"
                data-active={selectedSymbol === sym}
                aria-pressed={selectedSymbol === sym}
                onClick={() => setSelectedSymbol(sym)}
              >
                {sym}
              </button>
            ))}
          </div>
        </div>
      </header>

      <MarketsPane key={selectedSymbol} symbol={selectedSymbol} />
    </div>
  );
}

export function MarketsPane({ symbol }: { symbol: SymbolId }) {
  const [overview, setOverview] = useState<MarketRegimeOverview | null>(null);
  const [meta, setMeta] = useState<ApiMeta | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [now, setNow] = useState<number>(() => Date.now());

  const { phase, isOpen, sessionTimeIST, nextSessionChange } = useMarketSession();
  // The summary's regime leg is the NIFTY diagnosis. When it covers the
  // selected symbol, that shared owner is the only fetch on this route.
  const market = useOptionalMarketDataContext();
  const sharedRegime = regimeFromSummary(market?.regimeOverview, symbol);
  const contextOverview = sharedRegime && isUsableRegimeOverview(sharedRegime, symbol) ? sharedRegime : null;
  const contextFetchedAt = market?.lastFetch ?? null;

  useEffect(() => {
    if (!contextOverview) return;
    setOverview(contextOverview);
    setMeta(null);
    setError(null);
    setLastUpdated(contextFetchedAt ?? new Date());
    setFetching(false);
    setLoading(false);
  }, [contextOverview, contextFetchedAt]);

  const fetchRegime = useCallback(async () => {
    setFetching(true);
    setNow(Date.now());
    try {
      const res = await api.getRegimeOverview(symbol);
      setMeta(res.meta ?? null);
      if (!res.data) {
        setError(res.error || `No market regime data returned for ${symbol}.`);
        return;
      }
      if (!symbolsMatch(res.data.symbol, symbol)) {
        setOverview(null);
        setError(
          `Regime feed returned ${res.data.symbol || 'an unknown symbol'} while ${symbol} is selected — response discarded.`,
        );
        return;
      }
      setOverview(res.data);
      setError(res.error ?? null);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to fetch market regime data for ${symbol}.`);
    } finally {
      setFetching(false);
      setLoading(false);
    }
  }, [symbol]);

  // One owner per route: the shared summary leg when it covers the symbol,
  // otherwise this panel's direct poll.
  usePolling(fetchRegime, POLL_MS, !contextOverview);

  const usable = isUsableRegimeOverview(overview, symbol);
  const status: RegimeBannerStatus = usable
    ? 'ready'
    : error
      ? 'error'
      : loading
        ? 'loading'
        : isOpen
          ? 'empty'
          : 'closed';

  const stale = isOpen && isStale(lastUpdated, now);
  const provider = typeof meta?.provider === 'string' && meta.provider.trim() !== '' ? meta.provider : null;
  const provenance =
    provenanceLabel(meta?.provider, meta?.timestamp) ??
    (lastUpdated !== null
      ? `last fetched ${lastUpdated.toLocaleTimeString('en-IN', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })}`
      : null);

  return (
    <>
      <MarketSessionBanner
        phase={phase}
        sessionTimeIST={sessionTimeIST}
        nextSessionChange={nextSessionChange}
        lastAt={lastUpdated}
        fetching={fetching}
        marketClosed={!isOpen}
        provider={provider}
      />

      <RegimeBanner
        overview={overview}
        selectedSymbol={symbol}
        status={status}
        errorMessage={error}
        sessionNote={nextSessionChange}
      />

      {error && overview ? (
        <div role="note" className="notice notice--warn" style={{ fontSize: 12 }}>
          <span>
            Showing last known data for {symbol} — {error}
          </span>
        </div>
      ) : null}

      {loading && !overview ? (
        <div className="card card-pad" style={{ display: 'grid', gap: 8 }}>
          <div className="skel" style={{ height: 14, width: '55%' }}>.</div>
          <div className="skel" style={{ height: 140, width: '100%' }}>.</div>
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            Diagnosing market regime and computing support / resistance pivots…
          </p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <KeyLevelsTable
              keyLevels={overview?.key_levels ?? null}
              spotPrice={overview?.spot_price ?? 0}
              provenance={provenance}
              stale={stale}
            />
            <IndicatorsGrid
              indicators={overview?.indicators ?? null}
              spotPrice={overview?.spot_price ?? 0}
              provenance={provenance}
              stale={stale}
            />
          </div>
          <VixRegimeCard vixInfo={overview?.vix_regime ?? null} provenance={provenance} stale={stale} />
        </>
      )}
    </>
  );
}
