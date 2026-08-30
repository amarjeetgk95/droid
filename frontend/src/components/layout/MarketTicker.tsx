import { IndexCard } from '@/lib/types';

export function MarketTicker({ cards, loading }: { cards: IndexCard[]; loading: boolean }) {
  if (loading || !cards || cards.length === 0) return null;

  return (
    <div className="h-8 border-b border-border bg-background overflow-hidden flex items-center px-4">
      <div className="flex items-center gap-8 whitespace-nowrap animate-marquee">
        {cards.map(card => {
          const isPos = card.change >= 0;
          return (
            <div key={card.symbol} className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-foreground">{card.display_name}</span>
              <span className="tabular-nums">{card.ltp.toFixed(2)}</span>
              <span className={`tabular-nums flex items-center ${isPos ? 'text-success' : 'text-danger'}`}>
                {isPos ? '▲' : '▼'} {Math.abs(card.change_percent).toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
