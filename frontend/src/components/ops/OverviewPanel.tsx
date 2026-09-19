'use client';

/* Overview tab: dashboard summary (cards / breadth / status), live quotes,
   per-symbol dashboard lookup, instrument search. Read-only. */

import { useMemo, useState } from 'react';
import type { OpsConsole } from '@/hooks/useOpsConsole';
import { getObj, pickNum, pickStr } from '@/lib/signalsNormalize';
import { safeNum } from '@/lib/utils';
import { fmtCell, toneForSession } from '@/lib/opsDesk';
import { KvList, OpsCard, ToneBadge } from './OpsBits';

type QuoteRow = {
  symbol: string;
  name: string;
  ltp: number | null;
  change: number | null;
  changePct: number | null;
  status: string;
};

function toQuoteRow(raw: unknown): QuoteRow | null {
  const o = getObj(raw);
  if (!o) return null;
  const symbol = pickStr(o, 'symbol') ?? '—';
  return {
    symbol,
    name: pickStr(o, 'display_name') ?? symbol,
    ltp: pickNum(o, 'ltp'),
    change: pickNum(o, 'change'),
    changePct: pickNum(o, 'change_percent', 'changepct'),
    status: pickStr(o, 'status') ?? '—',
  };
}

export function OverviewPanel({ ops }: { ops: OpsConsole }) {
  const [symbolInput, setSymbolInput] = useState('NIFTY');
  const [searchInput, setSearchInput] = useState('');
  const [searchResults, setSearchResults] = useState<any[] | null>(null);
  const [searchMessage, setSearchMessage] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  const cards = useMemo(() => {
    const raw: unknown = ops.summary?.cards;
    const list = Array.isArray(raw) ? raw : [];
    return list.map(toQuoteRow).filter((row): row is QuoteRow => row !== null);
  }, [ops.summary]);

  const quoteRows = useMemo(() => {
    const raw: unknown = ops.quotes;
    const list = Array.isArray(raw) ? raw : [];
    return list.map(toQuoteRow).filter((row): row is QuoteRow => row !== null);
  }, [ops.quotes]);

  const breadth = getObj(ops.summary?.breadth);
  const errors = ops.overviewErrors;

  const handleSearch = async () => {
    setSearching(true);
    try {
      const result = await ops.searchInstruments(searchInput);
      setSearchMessage(result.message);
      setSearchResults(result.ok ? (result.results ?? []) : null);
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {Object.keys(errors).length > 0 ? (
        <p className="sg-err">{Object.values(errors).join(' · ')}</p>
      ) : null}

      <OpsCard
        title="Index cards"
        meta={ops.summary ? `generated ${fmtCell(ops.summary.generated_at)}` : undefined}
      >
        {ops.overviewLoading ? (
          <p className="sg-empty">Loading dashboard summary…</p>
        ) : cards.length === 0 ? (
          <p className="sg-empty">No index cards reported by /api/v1/dashboard/summary.</p>
        ) : (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Instrument</th>
                  <th>LTP</th>
                  <th>Chg</th>
                  <th>Chg%</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {cards.map((row) => (
                  <tr key={row.symbol}>
                    <td>
                      <span className="sg-sym">{row.name}</span>
                      <span className="sg-rownote">{row.symbol}</span>
                    </td>
                    <td className="num">{row.ltp === null ? '—' : safeNum(row.ltp)}</td>
                    <td className="num">{row.change === null ? '—' : safeNum(row.change)}</td>
                    <td className="num">{row.changePct === null ? '—' : `${safeNum(row.changePct)}%`}</td>
                    <td>
                      <ToneBadge tone={toneForSession(row.status)} label={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {breadth ? (
          <div className="stat-chips">
            <span className="stat-chip">
              advancing <b>{fmtCell(breadth.advancing)}</b>
            </span>
            <span className="stat-chip">
              declining <b>{fmtCell(breadth.declining)}</b>
            </span>
            <span className="stat-chip">
              unchanged <b>{fmtCell(breadth.unchanged)}</b>
            </span>
            <span className="stat-chip">
              sentiment <b>{fmtCell(breadth.sentiment)}</b>
            </span>
          </div>
        ) : (
          <p className="sg-note">Breadth block absent from the summary payload.</p>
        )}
      </OpsCard>

      <OpsCard title="Quotes" meta={`${quoteRows.length} tracked`}>
        {quoteRows.length === 0 ? (
          <p className="sg-empty">
            {errors.quotes ?? 'No quotes returned by /api/v1/markets/quotes.'}
          </p>
        ) : (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>LTP</th>
                  <th>Chg%</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {quoteRows.map((row) => (
                  <tr key={row.symbol}>
                    <td>
                      <span className="sg-sym">{row.symbol}</span>
                    </td>
                    <td className="num">{row.ltp === null ? '—' : safeNum(row.ltp)}</td>
                    <td className="num">{row.changePct === null ? '—' : `${safeNum(row.changePct)}%`}</td>
                    <td>
                      <ToneBadge tone={toneForSession(row.status)} label={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <KvList obj={ops.marketStatus} limit={6} />
      </OpsCard>

      <OpsCard
        title="Symbol dashboard"
        meta={ops.symbolDash ? ops.symbolDash.symbol : undefined}
        action={
          <span className="ds-filters">
            <input
              className="input mono"
              value={symbolInput}
              onChange={(event) => setSymbolInput(event.target.value.toUpperCase())}
              placeholder="NIFTY"
              aria-label="Dashboard symbol"
              style={{ maxWidth: 140 }}
            />
            <button
              type="button"
              className="btn"
              disabled={ops.symbolLoading}
              onClick={() => void ops.loadSymbol(symbolInput)}
            >
              {ops.symbolLoading ? 'Loading…' : 'Load'}
            </button>
          </span>
        }
      >
        {ops.symbolError ? <p className="sg-err">{ops.symbolError}</p> : null}
        {!ops.symbolDash && !ops.symbolError ? (
          <p className="sg-empty">Load a symbol to inspect GET /api/v1/dashboard/{`{symbol}`}.</p>
        ) : null}
        {ops.symbolDash ? <KvList obj={ops.symbolDash.data} limit={14} /> : null}
      </OpsCard>

      <OpsCard
        title="Instrument search"
        action={
          <span className="ds-filters">
            <input
              className="input"
              value={searchInput}
              onChange={(event) => setSearchInput(event.target.value)}
              placeholder="e.g. NIFTY"
              aria-label="Instrument search query"
              style={{ maxWidth: 180 }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') void handleSearch();
              }}
            />
            <button type="button" className="btn" disabled={searching} onClick={() => void handleSearch()}>
              {searching ? 'Searching…' : 'Search'}
            </button>
          </span>
        }
      >
        {searchMessage ? (
          <p className="sg-note">{searchMessage}</p>
        ) : (
          <p className="sg-note">Searches the instrument registry (GET /api/v1/instruments/search).</p>
        )}
        {searchResults !== null && searchResults.length > 0 ? (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Name</th>
                  <th>Exchange</th>
                  <th>Class</th>
                  <th>F&O</th>
                </tr>
              </thead>
              <tbody>
                {searchResults.map((raw, index) => {
                  const o = getObj(raw) ?? {};
                  return (
                    <tr key={pickStr(o, 'symbol') ?? String(index)}>
                      <td>
                        <span className="sg-sym">{pickStr(o, 'symbol') ?? '—'}</span>
                      </td>
                      <td>{pickStr(o, 'display_name') ?? '—'}</td>
                      <td>{pickStr(o, 'exchange') ?? '—'}</td>
                      <td>{pickStr(o, 'asset_class') ?? '—'}</td>
                      <td>
                        <ToneBadge
                          tone={o.fno_available === true ? 'bull' : 'neut'}
                          label={o.fno_available === true ? 'YES' : 'NO'}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </OpsCard>
    </div>
  );
}
