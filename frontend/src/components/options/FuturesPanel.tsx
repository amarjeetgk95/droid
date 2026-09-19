'use client';

import { Card } from '@/components/ui/desk';
import { fmtExpiry } from '@/lib/signalsNormalize';
import { safeNum, safeStr } from '@/lib/utils';
import type { OptionsDeskState } from '@/hooks/useOptionsDesk';
import { futuresAvailability } from '@/lib/optionsDesk';

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="sg-kv">
      <span className="l">{label}</span>
      <span className="v">{value}</span>
    </div>
  );
}

export function FuturesPanel({ desk }: { desk: OptionsDeskState }) {
  const availability = futuresAvailability(desk.futuresOverview);
  const overview = desk.futuresOverview;
  const term = desk.futuresTerm ?? overview?.term_structure ?? null;
  const buildup = desk.futuresBuildup ?? overview?.buildup ?? null;
  const rollover = desk.futuresRollover ?? overview?.rollover ?? null;
  const contracts = Array.isArray(term?.contracts) ? term?.contracts : [];
  const curveState = term?.curve_state ?? null;

  return (
    <div className="flex flex-col gap-3">
      {!availability.available ? (
        <p className="sg-note">
          {availability.reason} Spot still prints below from the live quote; every futures leg
          reports its own empty state rather than a fabricated curve.
        </p>
      ) : null}

      <Card title="Futures overview" meta={overview?.underlying ?? desk.instrument}>
        {!overview ? (
          <p className="sg-empty">Futures overview unavailable.</p>
        ) : (
          <div className="sg-kvlist">
            <KV label="Spot" value={safeNum(overview.spot_price)} />
            <KV label="Near future" value={overview.near_future_price !== null ? safeNum(overview.near_future_price) : '—'} />
            <KV label="Basis (pts)" value={overview.basis_pts !== null ? safeNum(overview.basis_pts) : '—'} />
          </div>
        )}
      </Card>

      <Card
        title="Term structure"
        meta={curveState ? curveState.replace(/_/g, ' ') : undefined}
      >
        {!term || contracts.length === 0 ? (
          <p className="sg-empty">
            No futures contracts published for {desk.instrument} — the term structure is
            UNAVAILABLE until the broker feed is wired.
          </p>
        ) : (
          <div className="tbl-scroll">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Expiry</th>
                  <th className="r">Price</th>
                  <th className="r">Open interest</th>
                  <th className="r">Volume</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((contract, index) => (
                  <tr key={`${contract.expiry ?? index}`}>
                    <td className="sg-sym">{fmtExpiry(contract.expiry)}</td>
                    <td className="r num">{contract.price !== null && contract.price !== undefined ? safeNum(contract.price) : '—'}</td>
                    <td className="r num">
                      {contract.open_interest !== null && contract.open_interest !== undefined ? safeNum(contract.open_interest, '—', 0) : '—'}
                    </td>
                    <td className="r num">
                      {contract.volume !== null && contract.volume !== undefined ? safeNum(contract.volume, '—', 0) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="OI buildup">
        {!buildup || buildup.buildup_type.toUpperCase() === 'UNAVAILABLE' ? (
          <p className="sg-empty">
            {safeStr(buildup?.interpretation, 'Authentic broker futures data offline or unavailable.')}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <div>
              <span className="sg-tag neut">{buildup.buildup_type.replace(/_/g, ' ')}</span>
            </div>
            <div className="sg-kvlist">
              <KV label="Price change %" value={safeNum(buildup.price_change_pct)} />
              <KV label="OI change %" value={safeNum(buildup.oi_change_pct)} />
            </div>
            <p className="sg-note">{safeStr(buildup.interpretation, '')}</p>
          </div>
        )}
      </Card>

      <Card title="Rollover">
        {!rollover || (rollover.rollover_percent === null && rollover.rollover_pace.toUpperCase() === 'UNAVAILABLE') ? (
          <p className="sg-empty">
            No rollover data for {desk.instrument} — expiry rollover tracking needs the broker
            futures feed.
          </p>
        ) : (
          <div className="sg-kvlist">
            <KV label="Rollover %" value={rollover.rollover_percent !== null ? `${safeNum(rollover.rollover_percent)}%` : '—'} />
            <KV label="Pace" value={rollover.rollover_pace.replace(/_/g, ' ')} />
            <KV label="Previous month" value={rollover.previous_month_rollover !== null ? `${safeNum(rollover.previous_month_rollover)}%` : '—'} />
          </div>
        )}
      </Card>
    </div>
  );
}
