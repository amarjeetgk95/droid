import { IndexCard } from '@/lib/types';
import { safeNum, safeInt } from '@/lib/utils';

export function MarketTicker({ cards, loading }: { cards: IndexCard[]; loading: boolean }) {
  if (loading) {
    return (
      <div className="h-8 border-b border-border bg-card overflow-hidden flex items-center px-4 gap-6">
        <div className="flex items-center gap-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2 animate-pulse">
              <div className="h-3 w-16 bg-muted rounded" />
              <div className="h-3 w-12 bg-muted rounded" />
              <div className="h-3 w-10 bg-muted rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!cards || cards.length === 0) return null;

  // Duplicate for seamless loop
  const loopCards = [...cards, ...cards];

  return (
    <div className="group relative h-8 border-b border-border bg-card overflow-hidden flex items-center">
      {/* edge fades */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-card to-transparent z-10" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-card to-transparent z-10" />

      <div className="flex items-center gap-8 whitespace-nowrap animate-marquee group-hover:[animation-play-state:paused] will-change-transform">
        {loopCards.map((card, idx) => {
          const changeVal = Number(card.change) || 0;
          const isPos = changeVal > 0;
          const isNeutral = changeVal === 0;
          const changePct = Number(card.change_percent) || 0;
          return (
            <div
              key={`${card.symbol}-${idx}`}
              className="flex items-center gap-2 text-xs shrink-0"
              title={`${card.display_name || card.symbol} • Vol ${safeInt(card.volume)} • OI ${card.open_interest != null ? safeInt(card.open_interest) : '—'}`}
            >
              <span className="font-semibold text-foreground tracking-tight">{card.display_name || card.symbol}</span>
              <span className="tabular-nums font-medium text-foreground">{safeNum(card.ltp)}</span>
              <span
                className={`tabular-nums inline-flex items-center gap-0.5 font-semibold px-1.5 py-0.5 rounded text-[11px] leading-none border ${
                  isNeutral
                    ? 'text-muted-foreground bg-muted border-border'
                    : isPos
                      ? 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20'
                      : 'text-red-500 bg-red-500/10 border-red-500/20'
                }`}
              >
                <span className="text-[9px] leading-none">{isNeutral ? '—' : isPos ? '▲' : '▼'}</span>
                {Math.abs(changePct).toFixed(2)}%
              </span>
              <span className="hidden sm:inline text-[11px] text-muted-foreground tabular-nums">
                {changeVal > 0 ? '+' : ''}
                {safeNum(card.change)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
