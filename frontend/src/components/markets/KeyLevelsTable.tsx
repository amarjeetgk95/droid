'use client';

import type { KeyLevelsModel, PivotSetModel } from '@/lib/types';
import { Card, EmptyNote, fmtINR } from '@/components/ui/desk';
import { hasKeyLevelData, posNum } from './truthful';

type PivotKey = 'r4' | 'r3' | 'r2' | 'r1' | 'p' | 's1' | 's2' | 's3' | 's4';

type PivotRow = {
  key: PivotKey;
  label: string;
  classic: number | null;
  fib: number | null;
  cam: number | null;
  isResistance?: boolean;
  isSupport?: boolean;
};

const ROW_DEFS: Array<{ key: PivotKey; label: string; field: keyof PivotSetModel; side?: 'r' | 's' }> = [
  { key: 'r4', label: 'Resistance 4', field: 'r4', side: 'r' },
  { key: 'r3', label: 'Resistance 3', field: 'r3', side: 'r' },
  { key: 'r2', label: 'Resistance 2', field: 'r2', side: 'r' },
  { key: 'r1', label: 'Resistance 1', field: 'r1', side: 'r' },
  { key: 'p', label: 'Pivot', field: 'pivot' },
  { key: 's1', label: 'Support 1', field: 's1', side: 's' },
  { key: 's2', label: 'Support 2', field: 's2', side: 's' },
  { key: 's3', label: 'Support 3', field: 's3', side: 's' },
  { key: 's4', label: 'Support 4', field: 's4', side: 's' },
];

function buildRows(
  classic: PivotSetModel | null | undefined,
  fib: PivotSetModel | null | undefined,
  cam: PivotSetModel | null | undefined,
): PivotRow[] {
  const rows: PivotRow[] = [];
  for (const def of ROW_DEFS) {
    const row: PivotRow = {
      key: def.key,
      label: def.label,
      classic: posNum(classic?.[def.field]),
      fib: posNum(fib?.[def.field]),
      cam: posNum(cam?.[def.field]),
      isResistance: def.side === 'r',
      isSupport: def.side === 's',
    };
    const optional = def.key === 'r4' || def.key === 's4';
    const hasValue = row.classic !== null || row.fib !== null || row.cam !== null;
    if (!optional || hasValue) rows.push(row);
  }
  return rows;
}

function nearestRowKey(
  rows: PivotRow[],
  side: 'r' | 's',
  spot: number | null,
  backendLevel: number | null,
): string | null {
  const wantsResistance = side === 'r';
  let best: string | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const row of rows) {
    if (wantsResistance ? !row.isResistance : !row.isSupport) continue;
    for (const value of [row.classic, row.fib, row.cam]) {
      if (value === null) continue;
      let distance: number;
      if (spot !== null) {
        if (wantsResistance && value <= spot) continue;
        if (!wantsResistance && value >= spot) continue;
        distance = Math.abs(value - spot);
      } else if (backendLevel !== null) {
        distance = Math.abs(value - backendLevel);
      } else {
        continue;
      }
      if (distance < bestDistance) {
        bestDistance = distance;
        best = row.key;
      }
    }
  }
  return best;
}

export function KeyLevelsTable({
  keyLevels,
  spotPrice,
  provenance,
  stale,
}: {
  keyLevels: KeyLevelsModel | null;
  spotPrice: number;
  provenance?: string | null;
  stale?: boolean;
}) {
  if (!keyLevels || !hasKeyLevelData(keyLevels)) {
    return (
      <Card
        title="Key Levels"
        meta={keyLevels ? 'no data' : 'unavailable'}
        action={stale ? <span className="badge b-warn">STALE</span> : undefined}
      >
        <EmptyNote>
          {keyLevels
            ? 'Provider reported only placeholder levels (zero values) — treated as unavailable.'
            : 'No key levels or pivot points available.'}
        </EmptyNote>
        {provenance ? (
          <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
            {provenance}
          </p>
        ) : null}
      </Card>
    );
  }

  const rows = buildRows(keyLevels.classic_pivots, keyLevels.fibonacci_pivots, keyLevels.camarilla_pivots);
  const spot = posNum(spotPrice);
  const nearestRKey = nearestRowKey(rows, 'r', spot, posNum(keyLevels.nearest_resistance));
  const nearestSKey = nearestRowKey(rows, 's', spot, posNum(keyLevels.nearest_support));

  const referenceRows: Array<{ label: string; value: unknown }> = [
    { label: 'POC', value: keyLevels.poc },
    { label: 'Value area high', value: keyLevels.vah },
    { label: 'Value area low', value: keyLevels.val },
    { label: 'Prior high', value: keyLevels.prior_day_high },
    { label: 'Prior low', value: keyLevels.prior_day_low },
    { label: 'Prior close', value: keyLevels.prior_day_close },
    { label: 'Day open', value: keyLevels.day_open },
  ];

  return (
    <Card
      title="Key Levels"
      meta={spot !== null ? `Spot ${fmtINR(spot)}` : undefined}
      action={stale ? <span className="badge b-warn">STALE</span> : undefined}
    >
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Level</th>
              <th className="r">Classic</th>
              <th className="r">Fib</th>
              <th className="r">Camarilla</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key}>
                <td>
                  {row.label}{' '}
                  {row.key === nearestRKey ? <span className="badge b-info">Nearest R</span> : null}
                  {row.key === nearestSKey ? <span className="badge b-info">Nearest S</span> : null}
                </td>
                <td className="r num">{fmtINR(row.classic)}</td>
                <td className="r num">{fmtINR(row.fib)}</td>
                <td className="r num">{fmtINR(row.cam)}</td>
              </tr>
            ))}
            <tr>
              <td colSpan={4} className="faint">
                Reference
              </td>
            </tr>
            {referenceRows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td className="r num">{fmtINR(row.value)}</td>
                <td className="r num">—</td>
                <td className="r num">—</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {provenance ? (
        <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
          {provenance}
        </p>
      ) : null}
    </Card>
  );
}
