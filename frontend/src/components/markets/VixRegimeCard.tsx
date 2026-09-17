'use client';

import type { VixRegimeInfo } from '@/lib/types';
import { Card, EmptyNote, Meter, Stat, fmtNum, fmtSigned } from '@/components/ui/desk';
import { finiteNum, posNum } from './truthful';

function badgeClass(category: string): 'b-bull' | 'b-bear' | 'b-neut' {
  if (category === 'ELEVATED_VOLATILITY' || category === 'EXTREME_VOLATILITY') return 'b-bear';
  if (category === 'LOW_VOLATILITY') return 'b-bull';
  return 'b-neut';
}

export function VixRegimeCard({
  vixInfo,
  provenance,
  stale,
}: {
  vixInfo: VixRegimeInfo | null;
  provenance?: string | null;
  stale?: boolean;
}) {
  const vixValue = posNum(vixInfo?.vix_value);

  if (!vixInfo || vixValue === null) {
    return (
      <Card
        title="Volatility"
        meta={vixInfo ? 'no data' : 'unavailable'}
        action={stale ? <span className="badge b-warn">STALE</span> : undefined}
      >
        <EmptyNote>
          {vixInfo
            ? 'India VIX returned a placeholder value (0) — no volatility regime is inferred.'
            : 'No India VIX volatility regime data available.'}
        </EmptyNote>
        {provenance ? (
          <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
            {provenance}
          </p>
        ) : null}
      </Card>
    );
  }

  const category =
    typeof vixInfo.regime_category === 'string' && vixInfo.regime_category.trim() !== ''
      ? vixInfo.regime_category
      : 'UNCLASSIFIED';
  const label = String(category).replace(/_/g, ' ');
  const change = finiteNum(vixInfo.change);
  const changePercent = finiteNum(vixInfo.change_percent);
  const changeTone = change === null ? ('neut' as const) : change > 0 ? ('bear' as const) : change < 0 ? ('bull' as const) : ('neut' as const);
  const pct = finiteNum(vixInfo.historical_percentile);
  const percentile = pct !== null && pct >= 0 && pct <= 100 ? pct : null;

  return (
    <Card
      title="Volatility"
      meta={<span className={`badge ${badgeClass(String(category))}`}>{label}</span>}
      action={stale ? <span className="badge b-warn">STALE</span> : undefined}
    >
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Stat label="India VIX" value={fmtNum(vixValue, 2)} />
        <Stat
          label="Day change"
          value={
            change !== null || changePercent !== null
              ? `${fmtSigned(change, 2)} (${fmtSigned(changePercent, 2)}%)`
              : '—'
          }
          tone={changeTone}
        />
        <Stat
          label="Percentile"
          value={percentile === null ? '—' : `${Math.round(percentile)}%`}
          sub={percentile === null ? undefined : <Meter value={percentile / 100} />}
        />
      </div>
      {vixInfo.recommended_option_strategy ? (
        <p className="muted" style={{ margin: '12px 0 0' }}>
          Playbook: {vixInfo.recommended_option_strategy}
        </p>
      ) : null}
      {vixInfo.interpretation ? (
        <p className="muted" style={{ margin: '6px 0 0' }}>
          {vixInfo.interpretation}
        </p>
      ) : null}
      {provenance ? (
        <p className="faint num" style={{ margin: '8px 0 0', fontSize: 11 }}>
          {provenance}
        </p>
      ) : null}
    </Card>
  );
}
