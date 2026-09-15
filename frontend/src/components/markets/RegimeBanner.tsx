'use client';

import type { MarketRegimeOverview } from '@/lib/types';
import { DirectionBadge, EmptyNote } from '@/components/ui/desk';

function directionForRegime(state: unknown): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  const s = String(state ?? '').toUpperCase();
  if (s.includes('BULLISH')) return 'BULLISH';
  if (s.includes('BEARISH')) return 'BEARISH';
  return 'NEUTRAL';
}

export function RegimeBanner({
  overview,
  selectedSymbol,
  onSelectSymbol,
}: {
  overview: MarketRegimeOverview | null;
  selectedSymbol: string;
  onSelectSymbol?: (sym: string) => void;
}) {
  void onSelectSymbol;

  if (!overview) {
    return (
      <aside className="compact-banner" data-tone="neut" aria-label="Regime">
        <span className="badge b-neut">DIAGNOSING</span>
        <span className="muted" style={{ fontSize: 12 }}>Diagnosing market regime for {selectedSymbol}…</span>
      </aside>
    );
  }

  const dir = directionForRegime(overview.regime_state);
  const tone = dir === 'BULLISH' ? 'bull' : dir === 'BEARISH' ? 'bear' : 'neut';

  return (
    <aside className="compact-banner" data-tone={tone} aria-label="Regime">
      <DirectionBadge direction={dir} />
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '4px 8px', flex: 1, minWidth: 0 }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--ds-ink)', whiteSpace: 'nowrap' }}>
          {overview.summary_headline || 'Market State Diagnosis'}
        </span>
        {overview.institutional_rationale ? (
          <span className="muted" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            — {overview.institutional_rationale}
          </span>
        ) : null}
      </div>
      <span className="card-meta num" style={{ marginLeft: 'auto', flexShrink: 0 }}>
        {selectedSymbol} · {overview.confidence_score}% conf
      </span>
    </aside>
  );
}
