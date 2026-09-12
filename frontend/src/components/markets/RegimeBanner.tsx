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
      <section className="card" aria-label="Regime">
        <div className="card-hd">
          <h2 className="card-title">Regime</h2>
          <span className="card-meta">computing…</span>
        </div>
        <div className="card-bd">
          <EmptyNote>Diagnosing market regime…</EmptyNote>
        </div>
      </section>
    );
  }

  const dir = directionForRegime(overview.regime_state);
  const tone = dir === 'BULLISH' ? 'bull' : dir === 'BEARISH' ? 'bear' : 'neut';

  return (
    <section className="forecast-hero" data-tone={tone} aria-label="Regime">
      <div className="forecast-hero-glow" aria-hidden />
      <div style={{ position: 'relative', padding: '14px 16px' }}>
        <div className="toolbar" style={{ marginBottom: 8 }}>
          <DirectionBadge direction={dir} />
          <span style={{ fontWeight: 650, fontSize: 14.5, letterSpacing: '-0.01em', color: 'var(--ds-ink)' }}>
            {overview.summary_headline || 'Market State Diagnosis'}
          </span>
          <span className="spacer" />
          <span className="card-meta num">{selectedSymbol} · confidence {overview.confidence_score}%</span>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: 12.5, maxWidth: 900 }}>
          {overview.institutional_rationale || 'No rationale published for this snapshot.'}
        </p>
      </div>
    </section>
  );
}
