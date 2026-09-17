'use client';

import type { MarketRegimeOverview } from '@/lib/types';
import { DirectionBadge } from '@/components/ui/desk';
import { confidencePct, isUsableRegimeOverview, normalizeSymbol, symbolsMatch } from './truthful';

export type RegimeBannerStatus = 'loading' | 'error' | 'empty' | 'closed' | 'ready';

function directionForRegime(state: unknown): 'BULLISH' | 'BEARISH' | 'NEUTRAL' {
  const s = String(state ?? '').toUpperCase();
  if (s.includes('BULLISH')) return 'BULLISH';
  if (s.includes('BEARISH')) return 'BEARISH';
  return 'NEUTRAL';
}

export function RegimeBanner({
  overview,
  selectedSymbol,
  status,
  errorMessage,
  sessionNote,
}: {
  overview: MarketRegimeOverview | null;
  selectedSymbol: string;
  status: RegimeBannerStatus;
  errorMessage?: string | null;
  sessionNote?: string | null;
}) {
  const usable = isUsableRegimeOverview(overview, selectedSymbol);
  const echoMatches = overview !== null && symbolsMatch(overview.symbol, selectedSymbol);

  if (status === 'ready' && usable && overview) {
    const dir = directionForRegime(overview.regime_state);
    const tone = dir === 'BULLISH' ? 'bull' : dir === 'BEARISH' ? 'bear' : 'neut';
    const conf = confidencePct(overview.confidence_score);

    return (
      <aside className="compact-banner" data-tone={tone} aria-label="Regime">
        <DirectionBadge direction={dir} />
        <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: '4px 8px', flex: 1, minWidth: 0 }}>
          <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--ds-ink)', whiteSpace: 'nowrap' }}>
            {overview.summary_headline}
          </span>
          {overview.institutional_rationale ? (
            <span className="muted" style={{ fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              — {overview.institutional_rationale}
            </span>
          ) : null}
        </div>
        <span className="card-meta num" style={{ marginLeft: 'auto', flexShrink: 0 }}>
          {normalizeSymbol(overview.symbol) ?? selectedSymbol}
          {conf !== null ? ` · ${conf}% conf` : ''}
        </span>
      </aside>
    );
  }

  if (status === 'loading') {
    return (
      <aside className="compact-banner" data-tone="neut" aria-label="Regime" aria-busy="true">
        <span className="badge b-info">DIAGNOSING</span>
        <span className="muted" style={{ fontSize: 12 }}>
          Computing regime, indicators and pivots for {selectedSymbol}…
        </span>
      </aside>
    );
  }

  if (status === 'error') {
    return (
      <aside className="compact-banner" data-tone="bear" aria-label="Regime">
        <span className="badge b-bear">FEED ERROR</span>
        <span className="muted" style={{ fontSize: 12 }}>
          {errorMessage || `Regime feed unavailable for ${selectedSymbol}.`}
        </span>
      </aside>
    );
  }

  if (status === 'closed') {
    return (
      <aside className="compact-banner" data-tone="neut" aria-label="Regime">
        <span className="badge b-neut">MARKET CLOSED</span>
        <span className="muted" style={{ fontSize: 12 }}>
          {sessionNote ? `${sessionNote} — ` : ''}
          no live regime diagnosis expected outside the trading session.
        </span>
      </aside>
    );
  }

  const headline = echoMatches && overview ? overview.summary_headline : null;
  const rationale = echoMatches && overview ? overview.institutional_rationale : null;

  return (
    <aside className="compact-banner" data-tone="neut" aria-label="Regime">
      <span className="badge b-warn">NO REGIME DATA</span>
      <span className="muted" style={{ fontSize: 12 }}>
        {headline ? `${headline} — ` : ''}
        {rationale || `No usable regime diagnosis returned for ${selectedSymbol}.`}
      </span>
    </aside>
  );
}
