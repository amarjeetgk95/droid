'use client';

import { FreshnessClock } from '@/components/common/FreshnessClock';
import type { MarketSessionPhase } from '@/context/MarketSessionContext';

const PHASE_LABEL: Record<MarketSessionPhase, string> = {
  PRE_OPEN: 'PRE-OPEN',
  OPEN: 'OPEN',
  POST_CLOSE: 'POST-CLOSE',
  CLOSED: 'CLOSED',
};

const PHASE_BADGE: Record<MarketSessionPhase, string> = {
  PRE_OPEN: 'b-warn',
  OPEN: 'b-bull',
  POST_CLOSE: 'b-neut',
  CLOSED: 'b-neut',
};

const PHASE_TONE: Record<MarketSessionPhase, 'bull' | 'bear' | 'neut'> = {
  PRE_OPEN: 'neut',
  OPEN: 'bull',
  POST_CLOSE: 'neut',
  CLOSED: 'neut',
};

export function MarketSessionBanner({
  phase,
  sessionTimeIST,
  nextSessionChange,
  lastAt,
  fetching,
  marketClosed,
  provider,
}: {
  phase: MarketSessionPhase;
  sessionTimeIST: string;
  nextSessionChange: string;
  lastAt: Date | string | number | null;
  fetching?: boolean;
  marketClosed?: boolean;
  provider?: string | null;
}) {
  return (
    <aside className="compact-banner" data-tone={PHASE_TONE[phase]} aria-label="Market session">
      <span className={`badge ${PHASE_BADGE[phase]}`}>{PHASE_LABEL[phase]}</span>
      <span className="muted" style={{ fontSize: 12 }}>
        {sessionTimeIST} · {nextSessionChange}
      </span>
      <span style={{ marginLeft: 'auto' }}>
        <FreshnessClock
          lastAt={lastAt}
          fetching={fetching}
          marketClosed={marketClosed ?? phase !== 'OPEN'}
          sourceLabel={provider ?? undefined}
        />
      </span>
    </aside>
  );
}
