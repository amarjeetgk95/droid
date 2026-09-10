'use client';

import type { VixRegimeInfo } from '@/lib/types';
import { Card, EmptyNote, Meter, Stat, fmtNum, fmtSigned } from '@/components/ui/desk';

function badgeClass(category: string): 'b-bull' | 'b-bear' | 'b-neut' {
  if (category === 'ELEVATED_VOLATILITY' || category === 'EXTREME_VOLATILITY') return 'b-bear';
  if (category === 'LOW_VOLATILITY') return 'b-bull';
  return 'b-neut';
}

export function VixRegimeCard({
  vixInfo,
}: {
  vixInfo: VixRegimeInfo | null;
}) {
  if (!vixInfo) {
    return (
      <Card title="Volatility" meta="unavailable">
        <EmptyNote>No India VIX volatility regime data available.</EmptyNote>
      </Card>
    );
  }

  const category = vixInfo.regime_category || 'NORMAL_VOLATILITY';
  const label = String(category).replace(/_/g, ' ');
  const changeTone =
    vixInfo.change > 0 ? ('bear' as const) : vixInfo.change < 0 ? ('bull' as const) : ('neut' as const);
  const pct =
    typeof vixInfo.historical_percentile === 'number' && Number.isFinite(vixInfo.historical_percentile)
      ? vixInfo.historical_percentile
      : null;

  return (
    <Card
      title="Volatility"
      meta={<span className={`badge ${badgeClass(String(category))}`}>{label}</span>}
    >
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
        <Stat label="India VIX" value={fmtNum(vixInfo.vix_value, 2)} />
        <Stat
          label="Day change"
          value={`${fmtSigned(vixInfo.change, 2)} (${fmtSigned(vixInfo.change_percent, 2)}%)`}
          tone={changeTone}
        />
        <Stat
          label="Percentile"
          value={pct === null ? '—' : `${Math.round(pct)}%`}
          sub={pct === null ? undefined : <Meter value={pct / 100} />}
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
    </Card>
  );
}
