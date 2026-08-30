import { IndexCard } from '@/lib/types';
import { DataStatus } from '../common/DataStatus';

function formatNumber(num: number) {
  if (num >= 10000000) return (num / 10000000).toFixed(2) + 'Cr';
  if (num >= 100000) return (num / 100000).toFixed(2) + 'L';
  if (num >= 1000) return (num / 1000).toFixed(2) + 'K';
  return num.toString();
}

function Sparkline({ data, isPositive }: { data: number[]; isPositive: boolean }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const width = 80;
  const height = 28;

  const points = data
    .map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      const y = height - ((val - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  const strokeColor = isPositive ? '#22c55e' : '#ef4444';

  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}

export function MarketCard({ card }: { card: IndexCard }) {
  const isPos = card.change >= 0;

  return (
    <div className="bg-card rounded-lg border border-border p-4 flex flex-col justify-between hover:border-border/80 transition-colors">
      <div className="flex justify-between items-start mb-2">
        <h3 className="font-bold text-foreground">{card.display_name}</h3>
        <DataStatus status={card.status} />
      </div>
      
      <div className="my-2 flex items-center justify-between">
        <div>
          <div className="text-2xl font-black tabular-nums tracking-tight">
            {card.ltp.toFixed(2)}
          </div>
          <div className={`text-xs font-semibold flex items-center gap-1 mt-0.5 ${isPos ? 'text-success' : 'text-danger'}`}>
            <span>{isPos ? '▲' : '▼'}</span>
            <span>{Math.abs(card.change).toFixed(2)}</span>
            <span>({Math.abs(card.change_percent).toFixed(2)}%)</span>
          </div>
        </div>
        <div className="opacity-90">
          <Sparkline data={card.sparkline} isPositive={isPos} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs text-muted-foreground">
        <div className="flex justify-between"><span>O:</span><span className="text-foreground tabular-nums">{card.open.toFixed(2)}</span></div>
        <div className="flex justify-between"><span>H:</span><span className="text-foreground tabular-nums">{card.high.toFixed(2)}</span></div>
        <div className="flex justify-between"><span>L:</span><span className="text-foreground tabular-nums">{card.low.toFixed(2)}</span></div>
        <div className="flex justify-between"><span>C:</span><span className="text-foreground tabular-nums">{card.previous_close.toFixed(2)}</span></div>
        <div className="flex justify-between mt-1 pt-1 border-t border-border"><span>Vol:</span><span className="text-foreground tabular-nums">{formatNumber(card.volume)}</span></div>
        <div className="flex justify-between mt-1 pt-1 border-t border-border"><span>OI:</span><span className="text-foreground tabular-nums">{card.open_interest !== null ? formatNumber(card.open_interest) : 'N/A'}</span></div>
      </div>
    </div>
  );
}
