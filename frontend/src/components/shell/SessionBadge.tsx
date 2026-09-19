'use client';

import { useMarketSession } from '@/context/MarketSessionContext';
import { SESSION_PHASE_LABELS } from './status';

export function SessionBadge() {
  const { phase, isOpen, sessionTimeIST, nextSessionChange } = useMarketSession();
  const tone = isOpen ? 'on' : phase === 'PRE_OPEN' || phase === 'POST_CLOSE' ? 'warn' : 'idle';

  return (
    <span
      className={`feed-pill feed-pill--${tone} feed-pill--session`}
      title={`${SESSION_PHASE_LABELS[phase]} · Next: ${nextSessionChange}`}
    >
      <i />
      {SESSION_PHASE_LABELS[phase]}
      <span className="feed-pill__meta">{sessionTimeIST}</span>
    </span>
  );
}
