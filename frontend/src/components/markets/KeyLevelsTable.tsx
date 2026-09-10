'use client';

import type { KeyLevelsModel } from '@/lib/types';
import { Card, EmptyNote, fmtINR } from '@/components/ui/desk';

type PivotRow = {
  key: string;
  label: string;
  classic: number | null | undefined;
  fib: number | null | undefined;
  cam: number | null | undefined;
  isResistance?: boolean;
  isSupport?: boolean;
};

export function KeyLevelsTable({
  keyLevels,
  spotPrice,
}: {
  keyLevels: KeyLevelsModel | null;
  spotPrice: number;
}) {
  if (!keyLevels) {
    return (
      <Card title="Key Levels" meta="unavailable">
        <EmptyNote>No key levels or pivot points available.</EmptyNote>
      </Card>
    );
  }

  const cp = keyLevels.classic_pivots;
  const fp = keyLevels.fibonacci_pivots;
  const cam = keyLevels.camarilla_pivots;

  const rows: PivotRow[] = [
    ...(cam?.r4 != null
      ? [{ key: 'r4', label: 'Resistance 4', classic: null, fib: null, cam: cam.r4, isResistance: true } as PivotRow]
      : []),
    { key: 'r3', label: 'Resistance 3', classic: cp?.r3, fib: fp?.r3, cam: cam?.r3, isResistance: true },
    { key: 'r2', label: 'Resistance 2', classic: cp?.r2, fib: fp?.r2, cam: cam?.r2, isResistance: true },
    { key: 'r1', label: 'Resistance 1', classic: cp?.r1, fib: fp?.r1, cam: cam?.r1, isResistance: true },
    { key: 'p', label: 'Pivot', classic: cp?.pivot, fib: fp?.pivot, cam: cam?.pivot },
    { key: 's1', label: 'Support 1', classic: cp?.s1, fib: fp?.s1, cam: cam?.s1, isSupport: true },
    { key: 's2', label: 'Support 2', classic: cp?.s2, fib: fp?.s2, cam: cam?.s2, isSupport: true },
    { key: 's3', label: 'Support 3', classic: cp?.s3, fib: fp?.s3, cam: cam?.s3, isSupport: true },
    ...(cam?.s4 != null
      ? [{ key: 's4', label: 'Support 4', classic: null, fib: null, cam: cam.s4, isSupport: true } as PivotRow]
      : []),
  ];

  const nearestR = keyLevels.nearest_resistance;
  const nearestS = keyLevels.nearest_support;

  const closestKey = (candidates: PivotRow[], target: unknown): string | null => {
    const t = typeof target === 'string' ? Number(target) : (target as number);
    if (typeof t !== 'number' || !Number.isFinite(t)) return null;
    let best: string | null = null;
    let bestDist = Infinity;
    for (const row of candidates) {
      const v = typeof row.classic === 'string' ? Number(row.classic) : row.classic;
      if (typeof v !== 'number' || !Number.isFinite(v)) continue;
      const d = Math.abs(v - t);
      if (d < bestDist) {
        bestDist = d;
        best = row.key;
      }
    }
    return best;
  };

  const nearestRKey = closestKey(rows.filter((r) => r.isResistance), nearestR);
  const nearestSKey = closestKey(rows.filter((r) => r.isSupport), nearestS);

  const referenceRows: Array<{ label: string; value: unknown }> = [
    { label: 'POC', value: keyLevels.poc },
    { label: 'Value area high', value: keyLevels.vah },
    { label: 'Value area low', value: keyLevels.val },
    { label: 'Prior high', value: keyLevels.prior_day_high },
    { label: 'Prior low', value: keyLevels.prior_day_low },
    { label: 'Prior close', value: keyLevels.prior_day_close },
  ];

  return (
    <Card title="Key Levels" meta={spotPrice ? `Spot ${fmtINR(spotPrice)}` : undefined}>
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
    </Card>
  );
}
